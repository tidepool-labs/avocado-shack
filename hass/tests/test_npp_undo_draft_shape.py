"""Offline behavior of the undo draft drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_undo_draft_shape.py"
PASS = "PASS npp_undo_draft_shape"
FAIL = "FAIL npp_undo_draft_shape"
DRIFT = ["FAIL undo-changed 0", "FAIL undo-changed 1",
         "FAIL undo-changed 4", "FAIL undo-changed 5"]
LIVE_LINES = [
    "case 0 undo=yes undone=['chg-1']",
    "case 1 undo=yes undone=['chg-1', 'chg-2']",
    "case 2 undo=no undone=[]",
    "case 3 undo=no undone=[]",
    "case 4 undo=yes undone=[None]",
    "case 5 undo=yes undone=[None]",
    "case 6 undo=no undone=[]",
    "case 7 undo=no undone=[]",
    "case 8 undo=no undone=[]",
    "case 9 undo=no undone=[]",
]


def cli(*args):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                          cwd=ROOT, capture_output=True, text=True, timeout=10)


def first_op_reverts(draft):
    ops = draft.get("ops") if isinstance(draft, dict) else None
    return bool(isinstance(ops, list) and ops and isinstance(ops[0], dict)
                and ops[0].get("op") == "history.revert")


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class UndoDraftShapeTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("npp_undo_draft_shape", SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError("could not load the undo draft diagnostic")
        self.tool = importlib.util.module_from_spec(spec)
        # Keep the standalone launcher's path setup from leaking into other tests.
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(self.tool)

    def run_main(self, code, trailer):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.tool.main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual((result, lines[-1:], stderr.getvalue()), (code, [trailer], ""))
        return lines

    def policy(self):
        # Patch the CLI's view only: real undone() still uses the real is_undo().
        return patch.object(self.tool, "live_policy", wraps=self.tool.live_policy)

    def test_c1_full_pass(self):
        # A correct report can still fail its standalone exit or trailer contract.
        result = cli()
        self.assertEqual((result.returncode, result.stdout.splitlines()[-1:], result.stderr),
                         (0, [PASS], ""))

    def test_c2_findings_trailer(self):
        # Findings must stay beside their own cases, not be grouped or stop the loop.
        with self.policy() as policy:
            policy.is_undo.side_effect = lambda draft: first_op_reverts(draft) or draft == {}
            lines = self.run_main(1, FAIL)
        expected = LIVE_LINES.copy()
        expected[8] = "case 8 undo=yes undone=[]"
        expected[9:9] = ["FAIL mixed-as-undo 8", "FAIL undo-changed 8"]
        expected[2] = "case 2 undo=yes undone=[]"
        expected[3:3] = ["FAIL mixed-as-undo 2", "FAIL undo-changed 2"]
        self.assertEqual(lines, expected + [FAIL])

    def test_c2_1_mixed_as_undo(self):
        # Looking only at the leading op could let a following edit ride an undo.
        with self.policy() as policy:
            policy.is_undo.side_effect = first_op_reverts
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         ["FAIL mixed-as-undo 2", "FAIL undo-changed 2"])

    def test_c2_2_undo_changed(self):
        # Checking only refusal cases would miss legitimate reverts going unrecognized.
        with self.policy() as policy:
            policy.is_undo.return_value = False
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], DRIFT)

        # An ID-only change is drift too, even when classification is unchanged.
        real_undone = self.tool.live_policy.undone
        with self.policy() as policy:
            policy.undone.side_effect = lambda draft: (
                [] if draft is self.tool.CASES[0] else real_undone(draft)
            )
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, ["case 0 undo=yes undone=[]", "FAIL undo-changed 0",
                                 *LIVE_LINES[1:], FAIL])

    def test_c2_3_check_error(self):
        # Neither helper's exception may leak text, stop with a traceback or allow more checks.
        for helper in ("is_undo", "undone"):
            with self.subTest(helper=helper), self.policy() as policy:
                getattr(policy, helper).side_effect = RuntimeError("synthetic exception text")
                self.assertEqual(self.run_main(1, FAIL), ["FAIL check-error", FAIL])
                self.assertEqual(policy.is_undo.call_args_list, [call(self.tool.CASES[0])])
                self.assertEqual(policy.undone.call_count, int(helper == "undone"))

    def test_c3_usage_exit_2(self):
        # Even help and end-of-options tokens are arguments to this no-argument CLI.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = cli(arg)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("error: unrecognized arguments:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Persisting a report or touching a source file is outside this diagnostic.
        before = snapshot()
        result = cli()
        self.assertEqual((result.returncode, result.stdout.splitlines()[-1:], result.stderr),
                         (0, [PASS], ""))
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Banners, debug lines or extra trailers would break consumers of the report.
        row = r"case [0-9] undo=(?:yes|no) undone=\[(?:(?:None|'chg-[12]')(?:, (?:None|'chg-[12]'))*)?\]"
        finding = r"FAIL (?:(?:mixed-as-undo|undo-changed) [0-9]|check-error)"
        for patched in (False, True):
            with self.subTest(patched=patched), self.policy() as policy:
                if patched:
                    policy.is_undo.side_effect = first_op_reverts
                lines = self.run_main(1 if patched else 0, FAIL if patched else PASS)
                for line in lines[:-1]:
                    self.assertIsNotNone(re.fullmatch(f"{row}|{finding}", line), line)

    def test_c6_fixture(self):
        # The all-false mutation changes classification only; it must not erase the ID column.
        with self.policy() as policy:
            policy.is_undo.side_effect = lambda _draft: False
            lines = self.run_main(1, FAIL)
        expected = []
        for i, line in enumerate(LIVE_LINES):
            expected.append(line.replace("undo=yes", "undo=no"))
            if i in (0, 1, 4, 5):
                expected.append(f"FAIL undo-changed {i}")
        self.assertEqual(lines, expected + [FAIL])

    def test_c7_live_pins(self):
        # Detect policy drift, reordered IDs, unsafe missing args, or a hard-coded report.
        with self.policy() as policy:
            self.assertEqual(self.run_main(0, PASS), LIVE_LINES + [PASS])
            self.assertEqual(policy.is_undo.call_args_list, [call(d) for d in self.tool.CASES])
            self.assertEqual(policy.undone.call_args_list, [call(d) for d in self.tool.CASES[:-1]])
