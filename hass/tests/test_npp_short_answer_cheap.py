"""Offline tests for scripts/hass/npp_short_answer_cheap.py (fixtures and in-process patches only).

Contract protected: openreq.cheap_answer reads a short reply without the model only
when it is just the asked value. Believable bugs that fail these tests: EXTRA
loses a word so "pantry and call it Honey Pot" is read as just "pantry", CHEAP_WORDS
or a resolver changes a pinned answer, or the tool stops calling cheap_answer.
"""

import contextlib
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock

from hass.skills import openreq


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_short_answer_cheap.py"
TRAILER_PASS = "PASS npp_short_answer_cheap"
TRAILER_FAIL = "FAIL npp_short_answer_cheap"
LIVE = [
    "case 0 cheap=(True, 'pantry')",
    "case 1 cheap=(True, 'pantry')",
    "case 2 cheap=(False, None)",
    "case 3 cheap=(False, None)",
    "case 4 cheap=(True, 'no')",
    "case 5 cheap=(True, 'limited')",
    "case 6 cheap=(True, '09:00')",
    "case 7 cheap=(False, None)",
    "case 8 cheap=(False, None)",
    "case 9 cheap=(False, None)",
    "case 10 cheap=(False, None)",
    "case 11 cheap=(False, None)",
    "case 12 cheap=(False, None)",
    "case 13 cheap=(False, None)",
]


def load_tool():
    spec = importlib.util.spec_from_file_location("npp_short_answer_cheap_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_main(*patches):
    """Run main() in-process with the given patches active; every patch is undone on exit."""
    tool = load_tool()
    out = io.StringIO()
    with contextlib.ExitStack() as stack:
        for patch in patches:
            stack.enter_context(patch)
        with contextlib.redirect_stdout(out):
            code = tool.main([])
    return code, out.getvalue().splitlines()


def run_script(*args):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=60)


def snapshot():
    seen = {}
    for top in ("hass", "storefront-mockup"):
        for path in sorted((ROOT / top).rglob("*")):
            info = path.stat()
            seen[str(path.relative_to(ROOT))] = (info.st_size, info.st_mtime_ns)
    return seen


def findings(lines):
    return [line for line in lines if line.startswith("FAIL ") and line != TRAILER_FAIL]


class ShortAnswerCheapTests(unittest.TestCase):
    def test_c1_full_pass(self):
        result = run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], TRAILER_PASS)

    def test_c2_findings_trailer(self):
        # Findings follow their case line, long-answer-read before cheap-changed, then the trailer.
        code, lines = run_main(mock.patch.object(openreq, "EXTRA", set()))
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)
        at = lines.index("case 2 cheap=(True, 'pantry')")
        self.assertEqual(lines[at + 1:at + 3], ["FAIL long-answer-read 2", "FAIL cheap-changed 2"])
        self.assertEqual(lines[at + 3], "case 3 cheap=(True, 'pantry')")

    def test_c2_1_long_answer_read(self):
        code, lines = run_main(mock.patch.object(openreq, "EXTRA", set()))
        self.assertEqual(code, 1)
        self.assertEqual(findings(lines), [
            "FAIL long-answer-read 2", "FAIL cheap-changed 2",
            "FAIL long-answer-read 3", "FAIL cheap-changed 3"])
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c2_2_cheap_changed(self):
        code, lines = run_main(mock.patch.object(openreq, "CHEAP_WORDS", 1))
        self.assertEqual(code, 1)
        self.assertEqual(findings(lines), ["FAIL cheap-changed 1", "FAIL cheap-changed 4"])
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c2_3_check_error(self):
        boom = mock.patch.object(openreq, "cheap_answer", side_effect=RuntimeError("secret detail"))
        code, lines = run_main(boom)
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["FAIL check-error", TRAILER_FAIL])

    def test_c2_3_check_error_stops_after_first_case_that_raises(self):
        calls = []
        real = openreq.cheap_answer

        def second_raises(slot, text, **kwargs):
            calls.append(text)
            if len(calls) == 3:
                raise RuntimeError("x")
            return real(slot, text, **kwargs)

        code, lines = run_main(mock.patch.object(openreq, "cheap_answer", second_raises))
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 3)  # no further case is checked
        self.assertEqual(lines[:2], LIVE[:2])
        self.assertEqual(lines[2:], ["FAIL check-error", TRAILER_FAIL])

    def test_c3_usage_exit_2(self):
        # --help/-h must be usage errors too (a help request would print to stdout and exit 0).
        for args in (("extra",), ("--bogus",), ("--help",), ("-h",)):
            with self.subTest(args=args):
                result = run_script(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_c4_read_only(self):
        before = snapshot()
        result = run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        result = run_script()
        self.assertEqual(result.stderr, "")
        shape = re.compile(r"case \d+ cheap=\((True|False), .*\)|FAIL [a-z-]+( \d+)?|PASS npp_short_answer_cheap")
        for line in result.stdout.splitlines():
            self.assertRegex(line, shape)
        self.assertEqual(len(result.stdout.splitlines()), len(LIVE) + 1)

    def test_c6_fixture(self):
        code, lines = run_main(mock.patch.object(openreq, "CHEAP_WORDS", 1))
        self.assertEqual(code, 1)
        self.assertEqual(findings(lines), ["FAIL cheap-changed 1", "FAIL cheap-changed 4"])
        self.assertEqual(lines[-1], TRAILER_FAIL)
        # The patch is undone: an unpatched run passes again.
        code, lines = run_main()
        self.assertEqual((code, lines[-1]), (0, TRAILER_PASS))

    def test_c7_live_pins(self):
        result = run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines, LIVE + [TRAILER_PASS])
        # Pins come from the repo function itself, not from a copy in the tool.
        tool = load_tool()
        self.assertEqual(tool.EXPECTED, LIVE)
        self.assertEqual(tool.MUST_MODEL, (2, 3, 7, 8, 9, 10, 11, 12, 13))
        self.assertEqual(len(tool.CASES), 14)


if __name__ == "__main__":
    unittest.main()
