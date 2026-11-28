"""Offline contract tests for the NPP yes-target drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_yes_select_target.py"
PASS = "PASS npp_yes_select_target"
FAIL = "FAIL npp_yes_select_target"
CHANGED_CASES = (0, 1, 3, 4, 10, 11, 13)
BASELINE = [
    "case 0 ok 1",
    "case 1 ok 1",
    "case 2 not_ready -",
    "case 3 which_card -",
    "case 4 ok 2",
    "case 5 replaced -",
    "case 6 already-done -",
    "case 7 not_ready -",
    "case 8 not_ready -",
    "case 9 not_ready -",
    "case 10 ok 2",
    "case 11 replaced -",
    "case 12 not_ready -",
    "case 13 which_card -",
    "case 14 not_ready -",
    "case 15 not_ready -",
]


def snapshot(*roots):
    entries = {}
    for root in roots:
        for path in (root, *root.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class NppYesSelectTargetTests(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.scratch,
                              capture_output=True, text=True, timeout=10)

    def load(self):
        spec = importlib.util.spec_from_file_location("npp_yes_select_target", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(module)
        return module

    def run_main(self, module, code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = module.main([])
        self.assertEqual(status, code)
        self.assertEqual(stderr.getvalue(), "")
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def assert_cli_pass(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [PASS])
        return lines[:-1]

    def test_c1_full_pass(self):
        # A clean check must propagate success through the CLI process exit.
        self.assert_cli_pass(self.cli())

    def test_c2_findings_trailer(self):
        # Multiple failures must not stop enumeration or reorder a case's findings.
        module = self.load()
        with patch.object(module.job.Jobs, "turn", return_value=None), patch.object(module.job, "instant", return_value=None):
            lines = self.run_main(module, 1, FAIL)
        expected = []
        for i in range(16):
            expected.append(f"FAIL no-turn {i}")
            if i in CHANGED_CASES:
                expected.append(f"FAIL target-changed {i}")
        self.assertEqual([line for line in lines if line.startswith("FAIL")], expected)

    def test_c2_1_no_turn(self):
        # Correct target answers alone must not hide a dropped yes turn.
        module = self.load()
        with patch.object(module.job.Jobs, "turn", return_value=None):
            lines = self.run_main(module, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL")],
                         [f"FAIL no-turn {i}" for i in range(16)])

    def test_c2_2_target_changed(self):
        # A receipt-time regression must be reported as target drift, not a missing turn.
        module = self.load()
        with patch.object(module.job, "instant", return_value=None):
            lines = self.run_main(module, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL")],
                         [f"FAIL target-changed {i}" for i in CHANGED_CASES])

    def test_c2_3_check_error(self):
        # An unexpected repo error must fail closed without echoing its details.
        module = self.load()
        with patch.object(module.job.Jobs, "select", side_effect=RuntimeError("synthetic internal detail")):
            self.assertEqual(self.run_main(module, 1, FAIL), ["FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # Silently accepting a token would run a fixture when the CLI should refuse.
        for arg in ("unexpected", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "), result.stderr)
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"npp_yes_select_target.py: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # Repo writes (including new files) or stray artifacts in cwd are regressions.
        roots = (ROOT / "hass", ROOT / "storefront-mockup")
        before = snapshot(*roots)
        self.assert_cli_pass(self.cli())
        self.assertEqual(snapshot(*roots), before)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_c5_output_shape(self):
        # Debug prints or extra fields would break the script's line protocol.
        lines = self.assert_cli_pass(self.cli())
        self.assertEqual(len(lines), 16)
        for i, line in enumerate(lines):
            self.assertRegex(line, rf"\Acase {i} (ok|not_ready|which_card|replaced|already-done) (-|[1-9][0-9]*)\Z")

    def test_c6_fixture(self):
        # A hard-coded oracle or a dead receipt dependency would miss this mutation.
        module = self.load()
        with patch.object(module.job, "instant", return_value=None):
            lines = self.run_main(module, 1, FAIL)
        cases = [line for line in lines if line.startswith("case ")]
        self.assertEqual(len(cases), len(BASELINE))
        self.assertEqual(tuple(i for i, line in enumerate(cases) if line != BASELINE[i]), CHANGED_CASES)
        self.assertEqual([line for line in lines if line.startswith("FAIL")],
                         [f"FAIL target-changed {i}" for i in CHANGED_CASES])

    def test_c7_live_pins(self):
        # Independently pin delivered-card selection, especially stale and late receipts.
        self.assertEqual(self.assert_cli_pass(self.cli()), BASELINE)
