"""Fixture-only tests for scripts/hass/npp_sentence_cut_contact.py (live-gate sentence cuts keep contacts whole)."""

import contextlib
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_sentence_cut_contact.py"

_spec = importlib.util.spec_from_file_location("npp_sentence_cut_contact_under_test", SCRIPT)
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

from hass import claims, live_policy  # noqa: E402  (same module objects the tool calls)

TRAILER_PASS = "PASS npp_sentence_cut_contact"
TRAILER_FAIL = "FAIL npp_sentence_cut_contact"

# Written out here on purpose (not read from tool.EXPECTED): the measured live answers at c8cdcc95.
LIVE_LINES = [
    "case 0 pieces=['Fresh honey', ' Spoon it on toast']",
    "case 1 pieces=['Email ana@cedarrow.example for more']",
    "case 2 pieces=['Costs $4.50 a jar']",
    "case 3 pieces=['See www.cedarrow.example. Thanks']",
    "case 4 pieces=['Write to ana at cedarrow.com', ' Thanks']",
    "case 5 pieces=['Call 000.555.0100 now']",
    "case 6 pieces=['Size 2.5 lb', ' keep cool']",
    "case 7 pieces=['one', '{\"a\": 1}']",
    "case 8 pieces=['12']",
    "case 9 pieces=['Hidden honey', ' Next one']",
    "case 10 pieces=['Email \\u0430na@cedarrow.example now']",
    "case 11 pieces=['Visit cedarrow dot com', ' Thanks']",
]

SHAPES = (
    re.compile(r"case \d+ pieces=\[.*\]"),
    re.compile(r"FAIL (contact-or-number-split|pieces-changed) \d+"),
    re.compile(r"FAIL check-error"),
    re.compile(r"(PASS|FAIL) npp_sentence_cut_contact"),
)


def run_main(*patches):
    """Run main() in-process with the given mock patchers active; every patch is undone on exit."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.ExitStack() as stack:
        for patcher in patches:
            stack.enter_context(patcher)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = tool.main([])
    return code, out.getvalue().splitlines(), err.getvalue()


def run_script(*args):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=30)


def snapshot():
    state = {}
    for tree in ("hass", "storefront-mockup"):
        for path in sorted((ROOT / tree).rglob("*")):
            info = path.lstat()
            state[str(path.relative_to(ROOT))] = (info.st_size, info.st_mtime_ns)
    return state


def findings(lines):
    return [line for line in lines if line.startswith("FAIL ") and line != TRAILER_FAIL]


class SentenceCutContactTests(unittest.TestCase):
    # Contract C1. Bug caught: the script exits non-zero, or ends without its PASS line, on the unchanged repo.
    def test_c1_full_pass(self):
        result = run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], TRAILER_PASS)
        self.assertEqual(findings(result.stdout.splitlines()), [])

    # Contract C2 (trailer and exit). Bug caught: a finding that still exits 0 or ends in PASS.
    def test_c2_findings_trailer(self):
        code, lines, err = run_main(mock.patch.object(live_policy, "CONTACT", ()))
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)
        self.assertEqual(err, "")
        # Each case's findings sit right after that case's own line.
        for position, line in enumerate(lines):
            if line.startswith("FAIL contact-or-number-split "):
                self.assertTrue(lines[position - 1].startswith("case " + line.rsplit(" ", 1)[1] + " "), lines)

    # Contract C2.1. Bug caught: a contact cut in two (CONTACT no longer protects an email, address or spelled host)
    # would let each half pass the gate alone; this must be named, in case order, before pieces-changed.
    def test_c2_1_contact_or_number_split(self):
        code, lines, _err = run_main(mock.patch.object(live_policy, "CONTACT", ()))
        self.assertEqual(code, 1)
        self.assertEqual(findings(lines), [
            "FAIL contact-or-number-split 1", "FAIL pieces-changed 1",
            "FAIL contact-or-number-split 3", "FAIL pieces-changed 3",
            "FAIL contact-or-number-split 4", "FAIL pieces-changed 4",
            "FAIL contact-or-number-split 10", "FAIL pieces-changed 10",
        ])
        self.assertEqual(lines[-1], TRAILER_FAIL)

    # Contract C2.2. Bug caught: a changed answer is not reported unless a token also splits. The C6 mutation changes
    # case 9 text; a changed expectation on a case with no token alone must give only pieces-changed.
    def test_c2_2_pieces_changed(self):
        code, lines, _err = run_main(mock.patch.object(claims, "unhidden", lambda v: str(v)))
        self.assertEqual(code, 1)
        self.assertIn("FAIL pieces-changed 9", lines)
        self.assertNotEqual(lines[lines.index("FAIL pieces-changed 9") - 2], LIVE_LINES[9])
        self.assertEqual(lines[-1], TRAILER_FAIL)
        edited = list(tool.EXPECTED)
        edited[0] = edited[0] + " "
        code, lines, _err = run_main(mock.patch.object(tool, "EXPECTED", edited))
        self.assertEqual(code, 1)
        self.assertEqual(findings(lines), ["FAIL pieces-changed 0"])
        self.assertEqual(lines[-1], TRAILER_FAIL)

    # Contract C2.3. Bug caught: a failing repo call is swallowed as a pass, loops on, or leaks exception text.
    def test_c2_3_check_error(self):
        broken = mock.patch.object(live_policy, "_pieces", side_effect=RuntimeError("secret-detail"))
        code, lines, err = run_main(broken)
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["FAIL check-error", TRAILER_FAIL])
        self.assertNotIn("secret-detail", "\n".join(lines) + err)
        # No further case is checked after the first error: fail on the second call only.
        calls = []
        real = live_policy._pieces

        def second_call_raises(value):
            calls.append(value)
            if len(calls) == 2:
                raise RuntimeError("boom")
            return real(value)

        code, lines, _err = run_main(mock.patch.object(live_policy, "_pieces", second_call_raises))
        self.assertEqual(code, 1)
        self.assertEqual(lines, [LIVE_LINES[0], "FAIL check-error", TRAILER_FAIL])
        self.assertEqual(len(calls), 2)

    # Contract C3. Bug caught: extra arguments silently accepted, or usage text sent to stdout.
    def test_c3_usage_exit_2(self):
        for args in (("extra",), ("--unknown",)):
            with self.subTest(args=args):
                result = run_script(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)

    # Contract C4. Bug caught: the check writes a file (cache, report, fixture) under the trees it reads.
    def test_c4_read_only(self):
        before = snapshot()
        result = run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(snapshot(), before)

    # Contract C5. Bug caught: stray prints, debug text or warnings on stdout or stderr, passing or failing.
    def test_c5_output_shape(self):
        result = run_script()
        self.assertEqual(result.stderr, "")
        runs = [result.stdout.splitlines()]
        runs.append(run_main(mock.patch.object(live_policy, "CONTACT", ()))[1])
        runs.append(run_main(mock.patch.object(live_policy, "_pieces", side_effect=RuntimeError("x")))[1])
        for lines in runs:
            self.assertTrue(lines)
            for line in lines:
                self.assertTrue(any(shape.fullmatch(line) for shape in SHAPES), line)

    # Contract C6. Bug caught: the unhide step stops being applied, so a zero-width space splits a word, and the tool
    # does not notice. The tool must call the repo's own unhidden, not a constant.
    def test_c6_fixture(self):
        code, lines, _err = run_main(mock.patch.object(claims, "unhidden", lambda v: str(v)))
        self.assertEqual(code, 1)
        self.assertEqual(findings(lines), ["FAIL contact-or-number-split 9", "FAIL pieces-changed 9"])
        self.assertEqual(lines[-1], TRAILER_FAIL)

    # Contract C7. Bug caught: any later change to the cut rule moves a pinned answer unnoticed.
    def test_c7_live_pins(self):
        result = run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines(), LIVE_LINES + [TRAILER_PASS])
        self.assertEqual(tool.EXPECTED, LIVE_LINES)
        self.assertEqual(tool.MUST_WHOLE, (1, 2, 3, 4, 5, 6, 9, 10, 11))
        self.assertEqual(len(tool.CASES), 12)


if __name__ == "__main__":
    unittest.main()
