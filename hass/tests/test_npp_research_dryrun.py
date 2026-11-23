"""Contract tests for the offline maker-research replay CLI."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_research_dryrun.py"
PASS = "PASS npp_research_dryrun"
FAIL = "FAIL npp_research_dryrun"
MAKER = "Quillberry"
TOWN = "Aster Hollow"
DOMAIN = "quillberry.example"
URL = f"https://{DOMAIN}/saved-home"
QUOTE = f"{MAKER} makes jam."
MARKUP = (f"<h1>{MAKER}</h1><p>{MAKER} is based in {TOWN}.</p>"
          f"<p>{QUOTE}</p><footer>Copyright {MAKER}.</footer>")


class ResearchDryrunTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        self.path = self.inputs / "tape.json"
        self.page = self.inputs / "home.html"
        self.page.write_text(MARKUP, encoding="utf-8")
        self.query = f"{MAKER} {TOWN} official site"
        self.tape = {
            "search": {self.query: [URL]},
            "pages": {URL: self.descriptor(self.page.name)},
            "extract": {"facts": [dict(slot="makes", value="jam", url=URL, quote=QUOTE)]},
            "verify": {"makes|jam": "supports"},
        }
        self.write_tape()

    @staticmethod
    def descriptor(name):
        return {"file": name, "retrieved": "2026-01-02"}

    def write_tape(self):
        self.path.write_text(json.dumps(self.tape), encoding="utf-8")

    def args(self, *extra, manifest=None):
        return ["--manifest", str(self.path if manifest is None else manifest),
                "--maker", MAKER, "--town", TOWN, *extra]

    def cli(self, args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                                cwd=self.inputs, capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout, result.stderr

    def load_cli(self):
        spec = importlib.util.spec_from_file_location("npp_research_dryrun", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        # Avoid adding a repo-root entry to the test runner's search path.
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(module)
        return module

    def run_main(self, module, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = module.main(self.args(*args))
        return code, out.getvalue(), err.getvalue()

    def assert_pass(self, result):
        code, out, err = result
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        lines = out.splitlines()
        self.assertEqual(lines[-1], PASS)
        self.assertFalse(any(line.startswith("FAIL") for line in lines))
        return lines

    def assert_fail(self, result, *reasons):
        code, out, err = result
        self.assertEqual(code, 1, err)
        self.assertEqual(err, "")
        self.assertEqual(out.splitlines(), [*(f"FAIL {reason}" for reason in reasons), FAIL])

    def test_c1_full_pass(self):
        # A replay that counts saved files, not requests, or selects the first hit gets this wrong.
        decoy = "https://decoy.example/"
        (self.inputs / "decoy.html").write_text("<h1>Unrelated</h1>", encoding="utf-8")
        self.tape["search"][self.query] = [decoy, URL, "https://untaped.example/"]
        self.tape["pages"][decoy] = self.descriptor("decoy.html")
        self.tape["pages"]["https://never-requested.example/"] = self.descriptor(self.page.name)
        self.write_tape()
        lines = self.assert_pass(self.cli(self.args()))
        self.assertEqual(lines[:4], ["queries 2", "fetched 2", "facts-kept 1", "kept makes"])
        self.assertCountEqual(lines[4:-1], [
            "receipt queries items 2", "receipt identity items 3", "receipt pages items 2",
            "receipt facts items 1", "receipt seed items 3", f"receipt chosen_domain {DOMAIN}",
            "receipt outcome story-facts",
        ])
        lines = self.assert_pass(self.cli(self.args("--owner-url", decoy)))
        self.assertEqual(lines[:3], ["queries 0", "fetched 1", "facts-kept 0"])
        self.assertIn("receipt outcome no-confirmed-site", lines)

    def test_c2_1_manifest_unreadable(self):
        # Following a symlink or reading invalid byte/JSON data must not silently pass.
        link = self.inputs / "linked.json"
        link.symlink_to(self.path)
        for path in (self.inputs / "absent.json", link):
            with self.subTest(case=path.name):
                self.assert_fail(self.cli(self.args(manifest=path)), "manifest-unreadable")
        missing_keys = [json.dumps({k: v for k, v in self.tape.items() if k != key}).encode()
                        for key in self.tape]
        for index, raw in enumerate([b"\xff", b"{invalid", *missing_keys]):
            with self.subTest(case=index):
                self.path.write_bytes(raw)
                self.assert_fail(self.cli(self.args()), "manifest-unreadable")

    def test_c2_2_page_missing(self):
        # Even unused entries must be validated; positions are in manifest order.
        (self.inputs / "linked.html").symlink_to(self.page)
        (self.inputs / "bad.html").write_bytes(b"\xff")
        outside = self.root / "outside.html"
        outside.write_text(MARKUP, encoding="utf-8")
        for name in ("absent.html", "linked.html", "../outside.html", str(outside), "bad.html"):
            with self.subTest(case=Path(name).name):
                self.tape["pages"]["https://untaped.example/"] = self.descriptor(name)
                self.write_tape()
                self.assert_fail(self.cli(self.args()), "page-missing 2")
        self.tape["pages"]["https://another.example/"] = self.descriptor("also-missing.html")
        self.write_tape()
        self.assert_fail(self.cli(self.args()), "page-missing 2", "page-missing 3")

    def test_c2_3_assets_refused(self):
        # A refused pin loader is a finding, not a traceback disclosing its exception.
        module = self.load_cli()
        with patch.object(module.npp, "assets", side_effect=RuntimeError("synthetic-private-error")):
            self.assert_fail(self.run_main(module), "assets-refused")

    def test_c3_usage_exit_2(self):
        # Usage errors are not findings and must not change argparse's status.
        for args in ([], self.args("--unknown"), self.args("--owner-url")):
            with self.subTest(case=len(args)):
                code, out, err = self.cli(args)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")  # No last stdout line for usage errors.
                self.assertTrue(err.startswith("usage: npp_research_dryrun.py "))

    def test_c4_read_only(self):
        # Catch rewrites with the same bytes and unexpected artifacts (even temporary ones).
        def snapshot():
            return {path.relative_to(self.root): (path.stat().st_mtime_ns,
                                                  path.read_bytes() if path.is_file() else None)
                    for path in [self.root, *self.root.rglob("*")]}

        before = snapshot()
        self.assert_pass(self.cli(self.args()))
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Dumping receipts, accepted facts, parser arguments or error paths leaks these markers.
        canaries = [self.query, URL, QUOTE, MARKUP, str(self.root),
                    "fixture-private-message", "fixture-private-chat", "fixture-private-sender",
                    "fixture-private-full-id", "decafbad" * 8]
        self.tape["private"] = canaries
        self.page.write_text(MARKUP + f"<p>{' '.join(canaries[5:])}</p>", encoding="utf-8")
        self.write_tape()
        success = self.cli(self.args())
        self.assertIn("kept makes", self.assert_pass(success))
        absent = self.cli(self.args(manifest=self.inputs / "missing.json"))
        self.assert_fail(absent, "manifest-unreadable")
        usage = self.cli(self.args("--unknown", *canaries))
        self.assertEqual((usage[0], usage[1]), (2, ""))
        for result in (success, absent, usage):
            for marker in canaries:
                self.assertNotIn(marker, result[1] + result[2])

    def test_c6_kept_and_dropped(self):
        # Treating the tape as already verified would keep the contradicted fact.
        self.assertIn("facts-kept 1", self.assert_pass(self.cli(self.args())))
        for verdicts in ({"makes|jam": "contradicts"}, {}):
            with self.subTest(verdicts=verdicts):
                self.tape["verify"] = verdicts
                self.write_tape()
                lines = self.assert_pass(self.cli(self.args()))
                self.assertIn("facts-kept 0", lines)
                self.assertNotIn("kept makes", lines)

    def test_c7_no_network(self):
        # Import and run under a refusing socket fence; a caught attempt still fails.
        with (patch("socket.socket.connect", side_effect=AssertionError("network forbidden")) as connect,
              patch("socket.create_connection", side_effect=AssertionError("network forbidden")) as create):
            self.assertIn("facts-kept 1", self.assert_pass(self.run_main(self.load_cli())))
        connect.assert_not_called()
        create.assert_not_called()
