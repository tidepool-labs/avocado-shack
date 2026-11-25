"""Fixture-only tests for scripts/hass/npp_writer_problem_list.py.

Contract protected: newitem.writer_problems keeps refusing a model-written
description for every unsaid word, claim, negation, number or hidden product's
wording. Each test names the believable bug that makes it fail.
"""

import contextlib
import importlib.util
import io
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from hass import newitem


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_writer_problem_list.py"
PASS = "PASS npp_writer_problem_list"
FAIL = "FAIL npp_writer_problem_list"

# Pinned independently of the script's own EXPECTED (measured with the repo's own words).
LIVE = [
    "case 0 problems=[]",
    "case 1 problems=['sentence 1 says more than the facts: raw']",
    "case 2 problems=['sentence 2 uses words the shop never uses: drizzle, over, ice, cream', "
    "'sentence 2 is not a serving suggestion like the others']",
    "case 3 problems=['a negation (the facts are written plainly)', "
    "'sentence 2 uses words the shop never uses: never, cold']",
    "case 4 problems=['claim word he did not affirm: harvested in', "
    "'sentence 2 states origin, ingredient or history: harvested', "
    "'sentence 2 uses words the shop never uses: harvested, spring', "
    "'sentence 2 is not a serving suggestion like the others']",
    "case 5 problems=['sentence 2 uses words the shop never uses: 2']",
    "case 6 problems=['claim word he did not affirm: organic', 'sentence 1 says more than the facts: organic']",
    "case 7 problems=[]",
    "case 8 problems=['sentence 2 uses words the shop never uses: lov', "
    "'sentence 2 is not a serving suggestion like the others']",
    "case 9 problems=[]",
]

LINE_SHAPES = (
    re.compile(r"case \d+ problems=\[.*\]"),
    re.compile(r"FAIL unchecked-description-passed \d+"),
    re.compile(r"FAIL problems-changed \d+"),
    re.compile(r"FAIL check-error"),
    re.compile(r"(PASS|FAIL) npp_writer_problem_list"),
)


def load_script():
    spec = importlib.util.spec_from_file_location("npp_writer_problem_list_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot():
    seen = {}
    for tree in ("hass", "storefront-mockup"):
        base = ROOT / tree
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            info = path.lstat()
            seen[str(path.relative_to(ROOT))] = (info.st_size, info.st_mtime_ns)
    return seen


class WriterProblemListTests(unittest.TestCase):
    def setUp(self):
        self.script = load_script()

    def run_main(self, argv=()):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.script.main(list(argv))
        self.assertEqual(err.getvalue(), "")
        return code, out.getvalue().splitlines()

    @staticmethod
    def findings(lines):
        return [l for l in lines if l.startswith("FAIL ") and l != FAIL]

    def run_subprocess(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
                              capture_output=True, text=True, timeout=60)

    def test_c1_full_pass(self):
        # A pass that exits non-zero or lacks the trailer would hide a real run.
        result = self.run_subprocess()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # Findings must end with the FAIL trailer and exit 1, never PASS.
        with mock.patch.object(newitem, "PROVENANCE", frozenset()):
            code, lines = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertNotIn(PASS, lines)
        # Each finding follows its own case line, in case order.
        finding = lines.index("FAIL problems-changed 4")
        self.assertTrue(lines[finding - 1].startswith("case 4 problems="))
        self.assertEqual(lines[finding + 1], LIVE[5])

    def test_c2_1_unchecked_description_passed(self):
        # If the word checker silently passes everything, every must-flag text is reported.
        with mock.patch.object(newitem, "_stems", lambda text: []):
            code, lines = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(self.findings(lines), [
            "FAIL unchecked-description-passed 1", "FAIL problems-changed 1",
            "FAIL unchecked-description-passed 2", "FAIL problems-changed 2",
            "FAIL problems-changed 3", "FAIL problems-changed 4",
            "FAIL unchecked-description-passed 5", "FAIL problems-changed 5",
            "FAIL problems-changed 6",
            "FAIL unchecked-description-passed 8", "FAIL problems-changed 8",
        ])
        self.assertEqual(self.script.MUST_FLAG, (1, 2, 3, 4, 5, 6, 8))
        self.assertEqual(lines[-1], FAIL)

    def test_c2_2_problems_changed(self):
        # A changed problem list for any case must be named, not tolerated.
        with mock.patch.object(newitem, "PROVENANCE", frozenset()):
            code, lines = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(self.findings(lines), ["FAIL problems-changed 4"])
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(self.script.EXPECTED, LIVE)

    def test_c2_3_check_error(self):
        # A raising repo call is one named FAIL and stops the run; no exception text leaks.
        real, calls = newitem.writer_problems, []

        def raising(*args, **kwargs):
            calls.append(args[0])
            if len(calls) == 4:
                raise RuntimeError("boom-secret")
            return real(*args, **kwargs)

        with mock.patch.object(newitem, "writer_problems", raising):
            code, lines = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 4)
        self.assertEqual(lines, LIVE[:3] + ["FAIL check-error", FAIL])
        self.assertNotIn("boom-secret", "\n".join(lines))

    def test_c3_usage_exit_2(self):
        # The tool takes no arguments; argparse's own usage exit must stay and stdout stay empty.
        for args in (("extra",), ("--bogus",)):
            with self.subTest(args=args):
                result = self.run_subprocess(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_c4_read_only(self):
        # A run that writes a file (or bytecode) into hass/ or storefront-mockup/ fails this.
        before = snapshot()
        result = self.run_subprocess()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Any stray stdout/stderr line (traceback, debug print) fails the shape check.
        result = self.run_subprocess()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        for line in result.stdout.splitlines():
            self.assertTrue(any(shape.fullmatch(line) for shape in LINE_SHAPES), line)
        with mock.patch.object(newitem, "_stems", lambda text: []):
            code, lines = self.run_main()
        for line in lines:
            self.assertTrue(any(shape.fullmatch(line) for shape in LINE_SHAPES), line)

    def test_c6_fixture(self):
        # Dropping the provenance list must change exactly case 4 (the 'harvested' provenance line).
        with mock.patch.object(newitem, "PROVENANCE", frozenset()):
            code, lines = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(self.findings(lines), ["FAIL problems-changed 4"])

    def test_c7_live_pins(self):
        # Pins every answer: a changed word list, claim rule, negation or number rule shows here.
        code, lines = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(lines, LIVE + [PASS])


if __name__ == "__main__":
    unittest.main()
