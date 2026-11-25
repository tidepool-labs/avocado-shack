"""Offline tests for scripts/hass/npp_shelf_stock_negation.py (the shelf/availability negation drift guard).

Each test protects one CONTRACT item of the tool and names the believable bug that makes it fail. Everything is
in-process or a read-only subprocess; no fixture file, network or state is touched.
"""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from hass import claims, newitem


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_shelf_stock_negation.py"
TRAILER_PASS = "PASS npp_shelf_stock_negation"
TRAILER_FAIL = "FAIL npp_shelf_stock_negation"

# An independent copy of the C7 pins, so editing the script's EXPECTED alone cannot hide a drift.
C7_LINES = [
    "case 0 shelf='pantry' availability=None",
    "case 1 shelf=None availability=None",
    "case 2 shelf='dairy' availability=None",
    "case 3 shelf=None availability=None",
    "case 4 shelf=None availability='no'",
    "case 5 shelf=None availability=None",
    "case 6 shelf=None availability='limited'",
    "case 7 shelf=None availability=None",
    "case 8 shelf=None availability=None",
    "case 9 shelf=None availability=None",
    "case 10 shelf=None availability=None",
    "case 11 shelf=None availability=None",
]


def load_tool():
    spec = importlib.util.spec_from_file_location("npp_shelf_stock_negation", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot():
    seen = {}
    for tree in ("hass", "storefront-mockup"):
        for path in sorted((ROOT / tree).rglob("*")):
            info = path.lstat()
            seen[str(path.relative_to(ROOT))] = (info.st_size, info.st_mtime_ns)
    return seen


class NppShelfStockNegationTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()

    def run_main(self, *patches):
        """Run main() in-process with the given mock patches active; they are undone on return."""
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            with contextlib.redirect_stdout(out):
                code = self.tool.main([])
        return code, out.getvalue().splitlines()

    @staticmethod
    def fails(lines):
        return [line for line in lines if line.startswith("FAIL ") and line != TRAILER_FAIL]

    def test_c1_full_pass(self):
        # Contract: an unpatched run exits 0 and ends on the PASS line. Bug: PASS missing or exit code wrong.
        result = subprocess.run([sys.executable, "-B", str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], TRAILER_PASS)

    def test_c2_findings_trailer(self):
        # Contract: findings follow their case line in case order and the run ends on the FAIL trailer, exit 1.
        # Bug: findings batched at the end, the PASS line printed after a finding, or exit 0.
        code, lines = self.run_main(mock.patch.object(newitem, "CATEGORIES", ()))
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)
        self.assertEqual(lines[:2], [C7_LINES[0].replace("'pantry'", "None"), "FAIL evidence-changed 0"])
        self.assertEqual(lines[3:5], [C7_LINES[2].replace("'dairy'", "None"), "FAIL evidence-changed 2"])
        self.assertNotIn(TRAILER_PASS, lines)

    def test_c2_1_negated_word_read(self):
        # Contract: a negator-blind match makes negated texts read a shelf or availability. Bug: the readers stop
        # going through claims._affirmed, so "not on the pantry shelf" sets pantry.
        ignore_negators = mock.patch.object(claims, "_affirmed", lambda rx, low: bool(rx.search(low)))
        code, lines = self.run_main(ignore_negators)
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)
        self.assertEqual(self.fails(lines), [
            "FAIL negated-word-read 1", "FAIL evidence-changed 1", "FAIL evidence-changed 3",
            "FAIL negated-word-read 5", "FAIL evidence-changed 5", "FAIL negated-word-read 7",
            "FAIL evidence-changed 7", "FAIL negated-word-read 10", "FAIL evidence-changed 10",
            "FAIL negated-word-read 11", "FAIL evidence-changed 11"])
        # Each finding sits right after its own case line (negated-word-read before evidence-changed).
        self.assertEqual(lines[lines.index("FAIL negated-word-read 5") - 1], "case 5 shelf=None availability='no'")
        self.assertNotEqual(claims._affirmed.__name__, "<lambda>")  # the patch was undone

    def test_c2_1_each_reader_is_called(self):
        # Contract: each reader is called on the input, not replaced by a constant. Bug: the check reuses a canned
        # answer, so a reader that misreads a negated text goes unnoticed.
        code, lines = self.run_main(mock.patch.object(newitem, "stated_shelf", lambda text: "pantry"))
        self.assertEqual(code, 1)
        self.assertIn("FAIL negated-word-read 1", lines)
        code, lines = self.run_main(mock.patch.object(newitem, "_availability_evidence", lambda low: "limited"))
        self.assertEqual(code, 1)
        self.assertIn("FAIL negated-word-read 5", lines)

    def test_c2_2_evidence_changed(self):
        # Contract: a case line that differs from EXPECTED is an evidence-changed finding and nothing else.
        # Bug: a pinned answer changes silently (for example a shelf word is no longer recognised).
        code, lines = self.run_main(mock.patch.object(newitem, "CATEGORIES", ()))
        self.assertEqual(code, 1)
        self.assertEqual(self.fails(lines), ["FAIL evidence-changed 0", "FAIL evidence-changed 2"])
        self.assertEqual(self.tool.EXPECTED, C7_LINES)

    def test_c2_3_check_error(self):
        # Contract: a raising repo call is the single line "FAIL check-error" (no exception text) and stops the
        # run. Bug: the traceback escapes, the text leaks, or later cases still run.
        for name in ("stated_shelf", "_availability_evidence", "_fold"):
            with self.subTest(call=name):
                boom = mock.Mock(side_effect=RuntimeError("secret-detail"))
                code, lines = self.run_main(mock.patch.object(newitem, name, boom))
                self.assertEqual(code, 1)
                self.assertEqual(lines, ["FAIL check-error", TRAILER_FAIL])
                self.assertNotIn("secret-detail", "\n".join(lines))
                self.assertEqual(boom.call_count, 1)

    def test_c3_usage_exit_2(self):
        # Contract: any argument is argparse's own exit 2 with nothing on stdout. Bug: arguments are ignored.
        for args in (["extra"], ["--nope"]):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT, capture_output=True,
                                        text=True, timeout=60)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # Contract: the run creates or changes no file under hass/ or storefront-mockup/. Bug: the tool writes a
        # cache, report or state file there.
        before = snapshot()
        result = subprocess.run([sys.executable, "-B", str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Contract: stdout holds only case lines, FAIL findings and the trailer; stderr is empty. Bug: debug
        # prints, warnings or a blank line.
        result = subprocess.run([sys.executable, "-B", str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.stderr, "")
        self.assertTrue(result.stdout.endswith("\n"))
        for line in result.stdout.splitlines():
            self.assertRegex(line, r"^(case \d+ shelf=\S+ availability=\S+|FAIL .+|PASS npp_shelf_stock_negation)$")
        code, lines = self.run_main(mock.patch.object(claims, "_affirmed", lambda rx, low: bool(rx.search(low))))
        for line in lines:
            self.assertRegex(line, r"^(case \d+ shelf=\S+ availability=\S+|FAIL (negated-word-read|evidence-changed) \d+|"
                                   r"FAIL npp_shelf_stock_negation)$")

    def test_c6_fixture(self):
        # Contract: with no categories the shelf cases fall to None and exactly cases 0 and 2 are flagged.
        # Bug: the shelf reader stops depending on CATEGORIES, or other cases move too.
        code, lines = self.run_main(mock.patch.object(newitem, "CATEGORIES", ()))
        self.assertEqual(code, 1)
        self.assertEqual(self.fails(lines), ["FAIL evidence-changed 0", "FAIL evidence-changed 2"])
        self.assertEqual(lines[-1], TRAILER_FAIL)
        self.assertTrue(newitem.CATEGORIES)  # the patch was undone

    def test_c7_live_pins(self):
        # Contract: unpatched, the informational lines are exactly the pinned answers and no finding appears.
        # Bug: a change to the shelf/availability readers or words moves a pinned answer unnoticed.
        code, lines = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(lines, C7_LINES + [TRAILER_PASS])
        self.assertEqual(self.tool.CASES, [
            'put it on the pantry shelf', 'not on the pantry shelf', 'dairy section please', 'shelf: bread',
            'sold out', 'not sold out', 'only a few left', 'it is never limited', 'plenty of jars', '',
            'no pantry shelf for this one', "it isn't sold out yet"])
        self.assertEqual(self.tool.MUST_NONE, (1, 5, 7, 10, 11))
        # The pins come from the repo readers themselves.
        for i, text in enumerate(self.tool.CASES):
            self.assertEqual(C7_LINES[i], f"case {i} shelf={newitem.stated_shelf(text)!r} "
                                          f"availability={newitem._availability_evidence(newitem._fold(text))!r}")


if __name__ == "__main__":
    unittest.main()
