"""Offline contract tests for the S3-to-S4 maker seed diagnostic."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hass import label_reader, npp
from hass.npp import missing, research


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_research_seed_parity.py"
PASS = "PASS npp_research_seed_parity"
FAIL = "FAIL npp_research_seed_parity"
REFUSED = (1, 2, 3, 4, 5)


class ResearchSeedParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_research_seed_parity", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def cli(self, *args):
        with TemporaryDirectory() as directory:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=directory,
                capture_output=True, text=True, timeout=10,
            )

    def run_main(self, code, trailer):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.checker.main([])
        return self.assert_report(status, stdout.getvalue(), stderr.getvalue(), code, trailer)

    def assert_report(self, status, stdout, stderr, code, trailer):
        self.assertEqual(status, code)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def test_c1_full_pass(self):
        # Accepted real names must not take the refusal path or inherit a failing exit.
        with patch.object(self.checker, "NAMES", ("Etto Farm", "Farm & Co")):
            self.assertEqual(self.run_main(0, PASS), ["seed 0 s3=yes s4=yes", "seed 1 s3=yes s4=yes"])

    def test_c2_findings_trailer(self):
        # Later good rows must not clear earlier findings or terminate the scan early.
        with patch.object(self.checker, "NAMES", ("Hill/Dale Farm", "7 Sisters Farm", "Etto Farm")):
            self.assertEqual(self.run_main(1, FAIL), [
                "seed 0 s3=yes s4=no", "FAIL seed-refused 0",
                "seed 1 s3=yes s4=no", "FAIL seed-refused 1", "seed 2 s3=yes s4=yes",
            ])

    def test_c2_1_seed_refused(self):
        # A changed S4 decision for an otherwise accepted seed must drive the finding.
        name = "Etto Farm"
        with (patch.object(self.checker, "NAMES", (name,)),
              patch.object(research, "_identity_field", return_value=False) as identity):
            self.assertEqual(self.run_main(1, FAIL), ["seed 0 s3=yes s4=no", "FAIL seed-refused 0"])
        identity.assert_any_call(name)

    def test_c2_2_s3_refused(self):
        # A changed/normalized label cannot be passed to research as the original S3 name.
        name = "Etto Farm"
        with (patch.object(self.checker, "NAMES", (name,)),
              patch.object(label_reader, "identity_text", return_value="Other Farm") as normalized):
            self.assertEqual(self.run_main(1, FAIL), ["seed 0 s3=no s4=yes", "FAIL s3-refused 0"])
        normalized.assert_called_once_with("brand", name)

    def test_c2_3_seed_reached_port(self):
        # Test the two independent triggers: a wrong receipt and a caught port call.
        name = "7 Sisters Farm"
        pinned = npp.assets()

        def reply(pinned_arg, *, search, fetch, extract, verify, owner_maker, owner_town):
            nonlocal observed
            observed = (pinned_arg is pinned, owner_maker, owner_town,
                        search is fetch is extract is verify)
            if call_port:
                with self.assertRaises(AssertionError):
                    search()
            return SimpleNamespace(receipt={"outcome": outcome})

        for outcome, call_port in (("research-disabled", False), ("no-safe-identity-seed", True)):
            with self.subTest(outcome=outcome, call_port=call_port):
                observed = None
                with (patch.object(self.checker, "NAMES", (name,)),
                      patch.object(npp, "assets", return_value=pinned) as assets,
                      patch.object(research, "research", side_effect=reply) as run):
                    self.assertEqual(self.run_main(1, FAIL), [
                        "seed 0 s3=yes s4=no", "FAIL seed-refused 0", "FAIL seed-reached-port 0",
                    ])
                assets.assert_called_once_with()
                self.assertEqual(run.call_count, 1)
                self.assertEqual(observed, (True, name, "Arroyo Grande", True))

    def test_c2_4_check_error(self):
        # Any one broken dependency must be a named failure, not a skip or traceback.
        for module, method in ((label_reader, "identity_text"), (missing, "_maker"),
                               (research, "_identity_field"), (research, "research")):
            with self.subTest(method=method):
                prefix = ["seed 0 s3=yes s4=no", "FAIL seed-refused 0"] if method == "research" else []
                with (patch.object(self.checker, "NAMES", ("7 Sisters Farm",)),
                      patch.object(module, method, side_effect=RuntimeError("fixture error")) as broken):
                    self.assertEqual(self.run_main(1, FAIL), [*prefix, "FAIL check-error"])
                self.assertEqual(broken.call_count, 1)

    def test_c3_usage_exit_2(self):
        # argparse defaults for help and the end marker must not bypass no-args usage.
        for arg in ("unexpected", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertTrue(result.stderr.splitlines()[-1].endswith(f"unrecognized arguments: {arg}"))

    def test_c4_read_only(self):
        # Root-dependent writes can land in the checkout even from a disposable cwd.
        def snapshot():
            entries = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (tree, *tree.rglob("*")):
                    stat = path.lstat()
                    entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.cli()
        self.assert_report(result.returncode, result.stdout, result.stderr, 1, FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Extra diagnostics (including stderr) break the machine-readable CLI.
        result = self.cli()
        lines = self.assert_report(result.returncode, result.stdout, result.stderr, 1, FAIL)
        self.assertEqual(sum(line.startswith("seed ") for line in lines), 10)
        for line in lines:
            self.assertRegex(line, r"\A(?:seed [0-9] s3=(?:yes|no) s4=(?:yes|no)|"
                                   r"FAIL (?:(?:seed-refused|s3-refused|seed-reached-port) [0-9]|check-error))\Z")

    def test_c6_fixture(self):
        # Decouple the classifiers: neither may be derived from the other or hard-coded.
        with (patch.object(research, "_identity_field", side_effect=lambda s: isinstance(s, str) and 0 < len(s) <= 80),
              patch.object(research, "research") as run):
            self.assertEqual(self.run_main(0, PASS), [f"seed {i} s3=yes s4=yes" for i in range(10)])
        run.assert_not_called()
        with patch.object(missing.Maker, "research_allowed", False):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         [f"FAIL s3-refused {i}" for i in range(10)])

    def test_c7_live_pins(self):
        # A drift in the real S3/S4 or research assets must change this exact report.
        self.assertEqual(self.checker.NAMES, (
            "Etto Farm", "7 Sisters Farm", "Route 1 Farms", "Twenty Acres Farm",
            "Bee+Hive Honey", "Hill/Dale Farm", "St. Clair Farm", "O'Neil Ranch",
            "Café Ñandú", "Farm & Co",
        ))
        expected = []
        for i in range(10):
            expected.append(f"seed {i} s3=yes s4={'no' if i in REFUSED else 'yes'}")
            if i in REFUSED:
                expected.append(f"FAIL seed-refused {i}")
        self.assertEqual(self.run_main(1, FAIL), expected)
