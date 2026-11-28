"""Offline CLI contract tests for the NPP money-screen comparison."""

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
SCRIPT = ROOT / "scripts/hass/npp_money_screen_parity.py"
PASS = "PASS npp_money_screen_parity"
FAIL = "FAIL npp_money_screen_parity"


def tree_snapshot(*trees):
    snapshot = {}
    for tree in trees:
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            snapshot[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return snapshot


class NppMoneyScreenParityTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("npp_money_screen_parity", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)

    def in_process(self, *phrases):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(self.tool, "PHRASES", phrases), redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.tool.main([])
        self.assertEqual(stderr.getvalue(), "")
        return result, stdout.getvalue().splitlines()

    def cli(self, *args):
        with TemporaryDirectory() as cwd:
            result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(list(Path(cwd).iterdir()), [])
        return result

    def test_c1_full_pass(self):
        # Receipt evidence differs from both money screens here; it cannot veto a pass.
        code, lines = self.in_process("4 dollars")
        self.assertEqual((code, lines[-1]), (0, PASS))
        self.assertEqual(lines[:-1], ["money 01 picture=yes s7=yes evidence=no"])

    def test_c2_findings_trailer(self):
        # An agreement after a disagreement must not clear the failure state.
        code, lines = self.in_process("4,99", "$4")
        self.assertEqual((code, lines[-1]), (1, FAIL))
        self.assertEqual(lines[:-1], ["money 01 picture=yes s7=no evidence=no",
                                      "FAIL money-disagree 01",
                                      "money 02 picture=yes s7=yes evidence=yes"])

    def test_c2_1_money_disagree(self):
        # Report both directions in input order, not grouped by the screen that matched.
        code, lines = self.in_process("\u20ac4", "$4", "4,99")
        self.assertEqual((code, lines[-1]), (1, FAIL))
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         ["FAIL money-disagree 01", "FAIL money-disagree 03"])

    def test_c2_2_check_error(self):
        # A scanner exception must not leak even if a later row can be evaluated.
        with patch.object(self.tool.private_numbers, "problem",
                          side_effect=[ValueError("synthetic-private-marker"), "money"]):
            code, lines = self.in_process("4,99", "$4")
        self.assertEqual((code, lines[-1]), (1, FAIL))
        self.assertEqual(lines[:-1], ["FAIL check-error", "money 02 picture=yes s7=yes evidence=yes"])

    def test_c3_usage_exit_2(self):
        # No flag, including argparse's default help, may bypass the zero-argument contract.
        for arg in ("unexpected", "--unknown", "-h", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("usage:", result.stderr)
                self.assertIn("error:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # A cache or report written under either input tree would change the snapshot.
        trees = ROOT / "hass", ROOT / "storefront-mockup"
        before = tree_snapshot(*trees)
        result = self.cli()
        self.assertEqual((result.returncode, result.stdout.splitlines()[-1]), (1, FAIL))
        self.assertEqual(tree_snapshot(*trees), before)

    def test_c5_output_shape(self):
        # Including the raw fixture, a debug line, or a warning violates the output contract.
        result = self.cli()
        lines = result.stdout.splitlines()
        self.assertEqual((result.returncode, lines[-1]), (1, FAIL))
        self.assertEqual(result.stderr, "")
        for line in lines[:-1]:
            self.assertRegex(line, r"\A(?:money [0-9]{2} picture=(?:yes|no) s7=(?:yes|no) "
                                   r"evidence=(?:yes|no)|FAIL money-disagree [0-9]{2})\Z")

    def test_c6_fixture(self):
        # A hard-coded live corpus would ignore these three agreeing inputs.
        code, lines = self.in_process("$4", "4 dollars", "50 cents")
        self.assertEqual((code, lines[-1]), (0, PASS))
        self.assertEqual(lines[:-1], ["money 01 picture=yes s7=yes evidence=yes",
                                      "money 02 picture=yes s7=yes evidence=no",
                                      "money 03 picture=yes s7=yes evidence=no"])

    def test_c7_live_pins(self):
        # Catch dropped/reordered fixtures and changes to the screens' current disagreements.
        result = self.cli()
        lines = result.stdout.splitlines()
        self.assertEqual((result.returncode, lines[-1]), (1, FAIL))
        money = [line for line in lines if line.startswith("money ")]
        self.assertEqual([line.split()[1] for line in money], [f"{i:02d}" for i in range(1, 18)])
        self.assertEqual(money[6], "money 07 picture=yes s7=no evidence=no")
        self.assertEqual(money[8], "money 09 picture=no s7=yes evidence=no")
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         [f"FAIL money-disagree {i:02d}" for i in range(7, 14)])
