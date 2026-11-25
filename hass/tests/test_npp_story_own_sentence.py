"""Behavioural tests for the offline maker-story own-sentence check.

Each test method starts with the CONTRACT item it pins. Every repo call is made
for real; the only patches are in-process, scoped to a `with` block, and undone.
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

from hass import newitem


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_story_own_sentence.py"
TRAILER_PASS = "PASS npp_story_own_sentence"
TRAILER_FAIL = "FAIL npp_story_own_sentence"
NEVER = re.compile(r"(?!x)x")
# Independent literal copy of the C7 pins (not read from the script's EXPECTED).
LIVE = [f"case {i} kept={v}" for i, v in enumerate(
    "yes no yes no no no no no yes no no yes".split())]
SHAPE = re.compile(
    r"case \d+ kept=(yes|no)|PASS npp_story_own_sentence|FAIL npp_story_own_sentence"
    r"|FAIL (unsaid-story-kept \d+|story-changed \d+|check-error)")


def load_script():
    spec = importlib.util.spec_from_file_location("npp_story_own_sentence_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_main(*patches):
    """Run main() in-process with the given context-manager patches; return (code, lines)."""
    module = load_script()
    out = io.StringIO()
    with contextlib.ExitStack() as stack:
        for patch in patches:
            stack.enter_context(patch)
        with contextlib.redirect_stdout(out):
            code = module.main([])
    return code, out.getvalue().splitlines()


def snapshot():
    state = {}
    for tree in ("hass", "storefront-mockup"):
        for path in sorted((ROOT / tree).rglob("*")):
            st = path.stat()
            state[str(path.relative_to(ROOT))] = (st.st_size, st.st_mtime_ns)
    return state


def run_script(*args):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=60)


class StoryOwnSentenceTests(unittest.TestCase):
    def test_c1_full_pass(self):
        # A drifted _story_ok answer would turn the run red instead of exit 0.
        result = run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], TRAILER_PASS)

    def test_c2_findings_trailer(self):
        # Any finding must flip the exit code and the last line; a run that
        # printed FAIL lines yet exited 0 or ended on PASS would hide the drift.
        code, lines = run_main(mock.patch.object(newitem, "PRONOUN_START", NEVER))
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)
        self.assertEqual(sum(line.startswith("FAIL ") for line in lines), 3)

    def test_c2_1_unsaid_story_kept(self):
        # With no joiner pattern a sentence with "that" is rewritten and kept:
        # words Mike did not say. Proves the check calls the real _story_ok.
        code, lines = run_main(mock.patch.object(newitem, "JOINERS", NEVER))
        self.assertEqual(code, 1)
        self.assertEqual([x for x in lines if x.startswith("FAIL ") and x != TRAILER_FAIL],
                         ["FAIL unsaid-story-kept 10", "FAIL story-changed 10"])
        self.assertEqual(lines[-1], TRAILER_FAIL)
        # The finding prints right after its own case line.
        at = lines.index("case 10 kept=yes")
        self.assertEqual(lines[at + 1:at + 3], ["FAIL unsaid-story-kept 10", "FAIL story-changed 10"])

    def test_c2_2_story_changed(self):
        # A kept/dropped answer that differs from the pinned EXPECTED line must be
        # named story-changed, and EXPECTED must be exactly the C7 lines.
        module = load_script()
        self.assertEqual(tuple(module.EXPECTED), tuple(LIVE))
        code, lines = run_main(mock.patch.object(newitem, "PRONOUN_START", NEVER))
        self.assertIn("FAIL story-changed 3", lines)
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c2_3_check_error(self):
        # A repo call that raises must be a named FAIL, once, with no further
        # case checked and no exception text; never a traceback or a silent pass.
        boom = mock.patch.object(newitem, "_story_ok", side_effect=RuntimeError("secret detail"))
        module = load_script()
        out = io.StringIO()
        with boom as patched, contextlib.redirect_stdout(out):
            code = module.main([])
        self.assertEqual(patched.call_count, 1)
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue().splitlines(), ["FAIL check-error", TRAILER_FAIL])
        self.assertNotIn("secret", out.getvalue())

    def test_c3_usage_exit_2(self):
        # Positional arguments and unknown flags must keep argparse's exit 2
        # and print nothing on stdout.
        for args in (("extra",), ("--nope",)):
            with self.subTest(args=args):
                result = run_script(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # A tool that cached results or wrote a file under hass/ or
        # storefront-mockup/ would change this snapshot.
        before = snapshot()
        result = run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Only the named line forms may appear, and nothing on stderr.
        result = run_script()
        self.assertEqual(result.stderr, "")
        self.assertTrue(result.stdout.endswith("\n"))
        for line in result.stdout.splitlines():
            self.assertRegex(line, r"\A(?:%s)\Z" % SHAPE.pattern)
        _code, lines = run_main(mock.patch.object(newitem, "JOINERS", NEVER))
        for line in lines:
            self.assertRegex(line, r"\A(?:%s)\Z" % SHAPE.pattern)

    def test_c6_fixture(self):
        # Pronoun-subject story kept as "his own sentence" when PRONOUN_START
        # never matches: exactly these two findings, in this order, exit 1.
        code, lines = run_main(mock.patch.object(newitem, "PRONOUN_START", NEVER))
        self.assertEqual(code, 1)
        self.assertEqual([x for x in lines if x.startswith("FAIL ") and x != TRAILER_FAIL],
                         ["FAIL unsaid-story-kept 3", "FAIL story-changed 3"])
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c7_live_pins(self):
        # Re-measured on the base (086aa24f, after c8cdcc95): case 9 stays
        # dropped because _third_person turns "He keeps" into "keepses".
        code, lines = run_main()
        self.assertEqual(code, 0)
        self.assertEqual(lines, LIVE + [TRAILER_PASS])
        self.assertEqual(newitem._third_person("He keeps bees on the hill.", "Cedar Row Apiary"),
                         "Cedar Row Apiary keepses bees on the hill.")


if __name__ == "__main__":
    unittest.main()
