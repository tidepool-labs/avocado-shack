"""Offline tests for scripts/hass/npp_reasoning_block_strip.py (HASS-INTERP-OPENAI-1 drift guard).

Each test protects one numbered contract item of the tool. The in-process tests patch
`interpreter_local.strip_reasoning` (undone by mock.patch) and run main(); the subprocess tests run the real script.
"""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from hass import interpreter_local


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_reasoning_block_strip.py"
TRAILER_FAIL = "FAIL npp_reasoning_block_strip"
TRAILER_PASS = "PASS npp_reasoning_block_strip"

# Independent copy of the C7 pins (a drifted EXPECTED in the script cannot hide itself).
C7_LINES = [
    """case 0 answer=ok:'{"op": "product.add"}'""",
    """case 1 answer=ok:'{"op": "product.add"}'""",
    """case 2 answer=ok:'{"op": "x"}'""",
    "case 3 answer=refused",
    "case 4 answer=refused",
    "case 5 answer=refused",
    """case 6 answer=ok:'{"op": "x"}'""",
    "case 7 answer=refused",
    "case 8 answer=refused",
    "case 9 answer=ok:''",
    "case 10 answer=refused",
]

SHAPE = re.compile(
    r"case \d+ answer=(ok:.*|refused)"
    r"|FAIL (reasoning-left-in-answer \d+|answer-changed \d+|check-error)"
    r"|(PASS|FAIL) npp_reasoning_block_strip"
)


def load():
    spec = importlib.util.spec_from_file_location("npp_reasoning_block_strip_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_main(replacement=None, argv=()):
    """(exit code, stdout lines, stderr) of main(); `replacement` patches strip_reasoning for the run only."""
    module = load()
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        if replacement is None:
            code = module.main(list(argv))
        else:
            with mock.patch.object(interpreter_local, "strip_reasoning", replacement):
                code = module.main(list(argv))
    return code, out.getvalue().splitlines(), err.getvalue()


def run_script(*args, cwd=None):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True,
                          timeout=60)


def snapshot():
    state = {}
    for tree in ("hass", "storefront-mockup"):
        for path in sorted((ROOT / tree).rglob("*")):
            info = path.lstat()
            state[str(path)] = (info.st_size, info.st_mtime_ns)
    return state


class NppReasoningBlockStripTests(unittest.TestCase):
    def test_c1_full_pass(self):
        # Contract C1. Bug: the guard fails or loses its trailer on unchanged main. Runs the real script from
        # outside the repo, which also proves it puts the repo root on sys.path itself.
        with tempfile.TemporaryDirectory() as elsewhere:
            result = run_script(cwd=elsewhere)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], TRAILER_PASS)

    def test_c2_findings_trailer(self):
        # Contract C2. Bug: a run with findings exits 0 or ends without the FAIL trailer.
        code, lines, _ = run_main(lambda text: text.strip())
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)
        self.assertEqual([x for x in lines if x.startswith("FAIL ")][-1], TRAILER_FAIL)

    def test_c2_1_reasoning_left_in_answer(self):
        # Contract C2.1. Bug: strip_reasoning trims at the last tag whatever its shape, so stray reasoning
        # (an unclosed or later block) would be read as the answer; it must be refused, not trimmed.
        spy = []

        def trim_ignoring_shape(text):
            spy.append(text)
            return text.rsplit("</think>", 1)[-1].strip()

        code, lines, _ = run_main(trim_ignoring_shape)
        self.assertEqual(code, 1)
        self.assertEqual(len(spy), len(C7_LINES))  # the repo call itself ran on every case
        self.assertEqual([x for x in lines if x.startswith("FAIL ") and x != TRAILER_FAIL], [
            "FAIL reasoning-left-in-answer 3", "FAIL answer-changed 3",
            "FAIL reasoning-left-in-answer 4", "FAIL answer-changed 4",
            "FAIL reasoning-left-in-answer 5", "FAIL answer-changed 5",
            "FAIL reasoning-left-in-answer 7", "FAIL answer-changed 7",
            "FAIL reasoning-left-in-answer 8", "FAIL answer-changed 8",
            "FAIL reasoning-left-in-answer 10", "FAIL answer-changed 10",
        ])
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c2_2_answer_changed(self):
        # Contract C2.2. Bug: a changed answer (here an answer that keeps its reasoning prefix) goes unreported.
        code, lines, _ = run_main(lambda text: text.strip())
        self.assertEqual(code, 1)
        self.assertIn("FAIL answer-changed 0", lines)
        self.assertIn("FAIL answer-changed 9", lines)
        self.assertNotIn("FAIL answer-changed 6", lines)  # a plain answer is unchanged
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c2_3_check_error(self):
        # Contract C2.3. Bug: an unexpected exception gives a traceback or lets later cases run.
        calls = []
        real = interpreter_local.strip_reasoning

        def delegate(text):
            calls.append(text)
            if len(calls) == 3:
                raise RuntimeError("private detail must not be printed")
            return real(text)

        code, lines, err = run_main(delegate)
        self.assertEqual(code, 1)
        self.assertEqual(err, "")
        self.assertEqual(lines, C7_LINES[:2] + ["FAIL check-error", TRAILER_FAIL])
        self.assertEqual(len(calls), 3)  # no further case is checked
        self.assertEqual(lines.count("FAIL check-error"), 1)

    def test_c3_usage_exit_2(self):
        # Contract C3. Bug: an argument is silently accepted, or help/usage text reaches stdout.
        for args in (("extra",), ("--nope",), ("-h",), ("--help",)):
            with self.subTest(args=args):
                result = run_script(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_c4_read_only(self):
        # Contract C4. Bug: the run writes a file (a cache, a report) under hass/ or storefront-mockup/.
        before = snapshot()
        result = run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Contract C5. Bug: stray debug output, a traceback or stderr noise leaks from the run.
        result = run_script()
        self.assertEqual(result.stderr, "")
        for line in result.stdout.splitlines():
            self.assertIsNotNone(SHAPE.fullmatch(line), line)
        _, lines, err = run_main(lambda text: text.strip())
        self.assertEqual(err, "")
        for line in lines:
            self.assertIsNotNone(SHAPE.fullmatch(line), line)

    def test_c6_fixture(self):
        # Contract C6. Bug: the check cannot tell a plain strip from the real shape-aware strip, or loses order.
        code, lines, _ = run_main(lambda text: text.strip())
        self.assertEqual(code, 1)
        self.assertEqual([x for x in lines if x.startswith("FAIL ") and x != TRAILER_FAIL], [
            "FAIL answer-changed 0", "FAIL answer-changed 1", "FAIL answer-changed 2",
            "FAIL reasoning-left-in-answer 3", "FAIL answer-changed 3",
            "FAIL reasoning-left-in-answer 4", "FAIL answer-changed 4",
            "FAIL reasoning-left-in-answer 5", "FAIL answer-changed 5",
            "FAIL reasoning-left-in-answer 7", "FAIL answer-changed 7",
            "FAIL reasoning-left-in-answer 8", "FAIL answer-changed 8",
            "FAIL answer-changed 9",
            "FAIL reasoning-left-in-answer 10", "FAIL answer-changed 10",
        ])
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c7_live_pins(self):
        # Contract C7. Bug: strip_reasoning changes an answer or stops refusing a stray tag shape (case 9, a
        # trailing `</think>`, still gives the empty string). The spy proves the repo function really runs.
        real = interpreter_local.strip_reasoning
        seen = []

        def spy(text):
            seen.append(text)
            return real(text)

        module = load()
        code, lines, err = run_main(spy)
        self.assertEqual(code, 0, lines)
        self.assertEqual(err, "")
        self.assertEqual(lines, C7_LINES + [TRAILER_PASS])
        self.assertEqual(seen, module.CASES)
        self.assertEqual(module.MUST_REFUSE, (3, 4, 5, 7, 8, 10))
        self.assertEqual(module.EXPECTED, C7_LINES)
        # Refusals come from the module's own failure type, not another exception.
        for index in module.MUST_REFUSE:
            with self.assertRaises(interpreter_local._Failed):
                real(module.CASES[index])


if __name__ == "__main__":
    unittest.main()
