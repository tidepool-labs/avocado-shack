"""Offline CLI contract for the counts-only NPP edit-form audit."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/edit_form_maker_reach.py"
SPEC = importlib.util.spec_from_file_location("edit_form_maker_reach", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
PASS = "PASS edit_form_maker_reach"
FAIL = "FAIL edit_form_maker_reach"
LIVE_LINES = [
    "makers 26",
    "FAIL form-miss supplier 2",
    "FAIL form-miss maker 2",
    "FAIL form-miss maker-town 4",
    "FAIL supplier-invalid 1",
    FAIL,
]


class EditFormMakerReachTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.makers = self.root / "makers.json"

    def write_makers(self, *names, place="Springfield, CA"):
        self.makers.write_text(json.dumps({"makers": {
            str(i): {"name": name, "place": place} for i, name in enumerate(names)
        }}), encoding="utf-8")

    def invoke(self, path=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (patch.object(AUDIT, "MAKERS", self.makers if path is None else path),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            code = AUDIT.main([])
        return code, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def grammar(**patterns):
        forms = [{"id": key, "pattern": pattern} for key, pattern in patterns.items()]
        return patch.object(AUDIT.npp, "assets", return_value=(None, {
            AUDIT.GRAMMAR: json.dumps({"forms": forms}),
        }))

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=20)

    def assert_result(self, result, code, *lines):
        self.assertEqual(result, (code, "\n".join(lines) + "\n", ""))

    def test_c1_full_pass(self):
        # Multiple reachable makers must not trigger a finding or a failing exit.
        self.write_makers("Alder Farm", "Birch Farm")
        self.assert_result(self.invoke(), 0, "makers 2", PASS)

    def test_c2_findings_trailer(self):
        # One failed form must set both the exit status and the final trailer.
        self.write_makers("Alder Farm", place="North 2, CA")
        self.assert_result(self.invoke(), 1, "makers 1", "FAIL form-miss maker-town 1", FAIL)

    def test_c2_1_input_unsafe(self):
        # Following an otherwise valid target would incorrectly pass the audit.
        self.write_makers("Alder Farm")
        link = self.root / "link.json"
        link.symlink_to(self.makers)
        for label, path in (("symlink", link), ("directory", self.root)):
            with self.subTest(kind=label):
                self.assert_result(self.invoke(path), 1, "FAIL input-unsafe makers", FAIL)

    def test_c2_2_input_too_large(self):
        # The byte limit wins even when the oversized content is not JSON.
        self.makers.write_bytes(b"xxxxx")
        with patch.object(AUDIT, "MAKERS_CAP", 4):
            self.assert_result(self.invoke(), 1, "FAIL input-too-large makers", FAIL)

    def test_c2_3_input_unreadable(self):
        # Bad input must short-circuit instead of continuing into asset checks.
        cases = {
            "missing": None,
            "utf8": b"\xff",
            "json": b"{",
            "shape": b'{"makers":[]}',
            "row": b'{"makers":{"x":{"name":"Alder Farm","place":0}}}',
            "optional": b'{"makers":{"x":{"name":"Alder Farm","place":"Springfield","url":null}}}',
        }
        for label, raw in cases.items():
            with self.subTest(case=label):
                if raw is not None:
                    self.makers.write_bytes(raw)
                with patch.object(AUDIT.npp, "assets", side_effect=AssertionError) as assets:
                    self.assert_result(self.invoke(), 1, "FAIL input-unreadable makers", FAIL)
                    assets.assert_not_called()

    def test_c2_4_assets_unreadable(self):
        # Missing or malformed grammar must not look like absent form IDs.
        self.write_makers("Alder Farm")
        for label, assets in (
            ("load failure", patch.object(AUDIT.npp, "assets", side_effect=RuntimeError("synthetic detail"))),
            ("invalid JSON", patch.object(AUDIT.npp, "assets", return_value=(None, {AUDIT.GRAMMAR: b"{"}))),
        ):
            with self.subTest(mode=label), assets:
                self.assert_result(self.invoke(), 1, "makers 1", "FAIL assets-unreadable", FAIL)

    def test_c2_5_form_missing(self):
        # Refuse both missing IDs explicitly, without inventing miss counts.
        self.write_makers("Alder Farm")
        with self.grammar(unrelated=r"(?P<value>.*)"):
            self.assert_result(self.invoke(), 1, "makers 1", "FAIL form-missing supplier",
                               "FAIL form-missing maker", FAIL)

    def test_c2_6_form_miss(self):
        # Partial captures fail even after a full match; matching is caseless.
        self.write_makers("Hill Farm", "Oak Farm")
        with self.grammar(supplier=r"FROM (?P<value>Hill|Oak) Farm",
                          maker=r"MADE BY (?P<value>Hill Farm)(?:, (?P<town>Spring)field)?"):
            self.assert_result(self.invoke(), 1, "makers 2", "FAIL form-miss supplier 2",
                               "FAIL form-miss maker 1", "FAIL form-miss maker-town 2", FAIL)

    def test_c2_7_supplier_invalid(self):
        # The forms accept this spelling, but the supplier validator does not.
        self.write_makers("Alder & Birch")
        self.assert_result(self.invoke(), 1, "makers 1", "FAIL supplier-invalid 1", FAIL)

    def test_c2_8_check_error(self):
        # Validator errors must not escape with a traceback or erase prior findings.
        self.write_makers("Alder Farm", place="North 2, CA")
        with patch.object(AUDIT.content_model, "valid_supplier", side_effect=RuntimeError("synthetic detail")):
            self.assert_result(self.invoke(), 1, "makers 1", "FAIL form-miss maker-town 1",
                               "FAIL check-error", FAIL)

    def test_c3_usage_exit_2(self):
        # No option (including default help) or positional argument is admitted.
        for arg in ("--unknown", "Hill Farm", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)
                self.assertIn("error:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # A report run must not even create a cache or touch either tree.
        def snapshot():
            result = {}
            for name in ("hass", "storefront-mockup"):
                root = ROOT / name
                for path in (root, *root.rglob("*")):
                    info = path.lstat()
                    result[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return result

        before = snapshot()
        result = self.cli()
        self.assertEqual(snapshot(), before)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual(result.stderr, "")

    def test_c5_output_shape(self):
        # Input text (including newlines) cannot inject extra report lines.
        self.write_makers("Alder\nUnexpected Detail")
        self.assert_result(self.invoke(), 1, "makers 1", "FAIL form-miss supplier 1",
                           "FAIL form-miss maker 1", "FAIL form-miss maker-town 1",
                           "FAIL supplier-invalid 1", FAIL)

    def test_c6_fixture_pass(self):
        # Use only the town before the comma, not the full place string.
        self.write_makers("Hill Farm", place="Springfield, CA")
        self.assert_result(self.invoke(), 0, "makers 1", PASS)

    def test_c7_live_pins(self):
        # Pin the catalog-wide counts and reporting order from the checkout.
        result = self.cli()
        self.assert_result((result.returncode, result.stdout, result.stderr), 1, *LIVE_LINES)


if __name__ == "__main__":
    unittest.main()
