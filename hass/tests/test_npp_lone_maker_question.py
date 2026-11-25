"""Offline tests for the lone-maker / unsaid-question drift guard.

Contract protected: a maker.add never goes live without a product.add naming it,
and the unsaid-value question names at most two values. Each in-process patch
below proves the script calls the repo function itself: a constant in place of
the call would not move the output.
"""

import contextlib
import io
from importlib import util
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock

from hass import live_policy

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_lone_maker_question.py"
TRAILER_FAIL = "FAIL npp_lone_maker_question"
TRAILER_PASS = "PASS npp_lone_maker_question"
LONE = "['not live: maker.add without a new product']"
TAIL = (" in your message, and a brand, a maker or a town only goes on the website in your own words. "
        "Send the change again with it in your own words, or without it.'")
# Pinned independently of the script's own EXPECTED (measured at c8cdcc95, re-measured at 086aa24f).
LIVE_LINES = [
    "case 0 lone=[]",
    "case 1 lone=" + LONE,
    "case 2 lone=" + LONE,
    "case 3 lone=" + LONE,
    "case 4 lone=" + LONE,
    "case 5 lone=[]",
    "case 6 lone=[]",
    "case 7 question='You didn\\'t say \\ue000\"Cedar Row Apiary\"\\ue001" + TAIL,
    "case 8 question='You didn\\'t say \\ue000\"Cedar Row Apiary\"\\ue001 and \\ue000\"Fillmore\"\\ue001"
    " (and a few more)" + TAIL,
    "case 9 question='You didn\\'t say \\ue000\"Cedar Row Apiary\"\\ue001 and \\ue000\"Fillmore\"\\ue001" + TAIL,
]
LINE_FORMS = re.compile(
    r"case \d lone=\[.*\]|case \d question='.*'|FAIL lone-maker-allowed \d|FAIL lone-changed \d"
    r"|FAIL check-error|PASS npp_lone_maker_question|FAIL npp_lone_maker_question")


def load_script():
    spec = util.spec_from_file_location("npp_lone_maker_question_under_test", SCRIPT)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot():
    state = {}
    for tree in ("hass", "storefront-mockup"):
        for path in sorted((ROOT / tree).rglob("*")):
            info = path.lstat()
            state[str(path)] = (info.st_size, info.st_mtime_ns)
    return state


class LoneMakerQuestionTests(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              cwd=ROOT, capture_output=True, text=True, timeout=30)

    def run_in_process(self, *patches):
        """Run main() with the given mock patches active; each is undone on exit."""
        module = load_script()
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            with contextlib.redirect_stdout(out):
                code = module.main([])
        return code, out.getvalue().splitlines()

    def test_c1_full_pass(self):
        # Believable bug: the tool prints a finding or the wrong trailer on an untouched repo.
        result = self.run_script()
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertEqual(result.stdout.splitlines()[-1], TRAILER_PASS)

    def test_c2_findings_trailer(self):
        # Believable bug: a finding is printed but the exit code stays 0 or the trailer is PASS.
        code, lines = self.run_in_process(mock.patch.object(live_policy, "LONE_MAKER", "x"))
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)
        self.assertIn("FAIL lone-changed 1", lines)

    def test_c2_1_lone_maker_allowed(self):
        # Believable bug: a later change lets a lone maker through. Proves the call is real.
        code, lines = self.run_in_process(mock.patch.object(live_policy, "_lone_makers", lambda ops: []))
        self.assertEqual(code, 1)
        self.assertEqual([line for line in lines if line.startswith("FAIL")], [
            "FAIL lone-maker-allowed 1", "FAIL lone-changed 1",
            "FAIL lone-maker-allowed 2", "FAIL lone-changed 2",
            "FAIL lone-maker-allowed 3", "FAIL lone-changed 3",
            "FAIL lone-maker-allowed 4", "FAIL lone-changed 4",
            TRAILER_FAIL])
        self.assertEqual(lines[-1], TRAILER_FAIL)
        # Findings sit right after their own case line.
        self.assertEqual(lines[lines.index("case 1 lone=[]") + 1], "FAIL lone-maker-allowed 1")

    def test_c2_2_lone_changed(self):
        # Believable bug: the refusal wording drifts; the pinned line no longer matches.
        code, lines = self.run_in_process(mock.patch.object(live_policy, "LONE_MAKER", "maker on its own"))
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL lone-changed")],
                         [f"FAIL lone-changed {i}" for i in (1, 2, 3, 4)])

    def test_c2_3_check_error(self):
        # Believable bug: a raising repo call is swallowed (silent skip) or leaks its text.
        def boom(*_args):
            raise RuntimeError("secret detail")

        code, lines = self.run_in_process(mock.patch.object(live_policy, "_lone_makers", boom))
        self.assertEqual((code, lines), (1, ["FAIL check-error", TRAILER_FAIL]))
        code, lines = self.run_in_process(mock.patch.object(live_policy, "unsaid_question", boom))
        self.assertEqual(code, 1)
        self.assertEqual(lines[-2:], ["FAIL check-error", TRAILER_FAIL])
        self.assertEqual(lines.count("FAIL check-error"), 1)
        self.assertEqual(lines[:7], LIVE_LINES[:7])
        self.assertFalse([line for line in lines if line.startswith(("case 7", "case 8", "case 9"))])
        self.assertNotIn("secret detail", "\n".join(lines))

    def test_c3_usage_exit_2(self):
        # Believable bug: extra arguments are ignored and the check runs anyway.
        for args in (("extra",), ("--bogus",)):
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_c4_read_only(self):
        # Believable bug: the tool writes a file or a .pyc into hass/ or storefront-mockup/.
        before = snapshot()
        result = self.run_script()
        after = snapshot()
        self.assertEqual((result.returncode, result.stdout.splitlines()[-1]), (0, TRAILER_PASS))
        self.assertEqual(before, after)

    def test_c5_output_shape(self):
        # Believable bug: a debug line or traceback appears on stdout or stderr.
        result = self.run_script()
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], TRAILER_PASS)
        _code, failing = self.run_in_process(mock.patch.object(live_policy, "_lone_makers", lambda ops: []))
        for line in lines + failing:
            self.assertRegex(line, LINE_FORMS)
            self.assertIsNotNone(LINE_FORMS.fullmatch(line), line)

    def test_c6_fixture(self):
        # Believable bug: the lone-maker reason text drifts without anyone noticing.
        code, lines = self.run_in_process(mock.patch.object(live_policy, "LONE_MAKER", "maker on its own"))
        self.assertEqual(code, 1)
        self.assertEqual([line for line in lines if line.startswith("FAIL")],
                         [f"FAIL lone-changed {i}" for i in (1, 2, 3, 4)] + [TRAILER_FAIL])
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c7_live_pins(self):
        # Believable bug: unsaid_question names three values, or loses the "(and a few more)" tail.
        result = self.run_script()
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertEqual(result.stdout.splitlines(), LIVE_LINES + [TRAILER_PASS])


if __name__ == "__main__":
    unittest.main()
