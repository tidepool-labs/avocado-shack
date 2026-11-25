"""Offline tests for the private-intake commerce/text drift guard (scripts/hass/npp_intake_commerce_text.py)."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_intake_commerce_text.py"
TRAILER_PASS = "PASS npp_intake_commerce_text"
TRAILER_FAIL = "FAIL npp_intake_commerce_text"
CHARACTERS = "I can't use one of the characters in that. Could you say it again in plain words?"
# The C7 lines, written out here so the tool's own EXPECTED cannot vouch for itself.
C7 = [
    "case 0 commerce={'price': '7.99', 'cost': '4.50', 'qty': 12, 'qty_unit': 'each'}",
    "case 1 commerce={'price': '7.99'}",
    "case 2 commerce={}",
    "case 3 commerce={}",
    "case 4 commerce={}",
    "case 5 commerce={}",
    "case 6 commerce={}",
    "case 7 commerce={}",
    "case 8 text=('honey', None)",
    "case 9 text=('none', None)",
    "case 10 text=('', None)",
    f"case 11 text=(None, \"{CHARACTERS}\")",
    "case 12 text=(None, 'That is a bit long for my notes. Could you shorten it?')",
    f"case 13 text=(None, \"{CHARACTERS}\")",
]
LINE_FORMS = (
    re.compile(r"case \d+ (?:commerce|text)=.*"),
    re.compile(r"FAIL unsafe-answer-read \d+"),
    re.compile(r"FAIL intake-changed \d+"),
    re.compile(r"FAIL check-error"),
    re.compile(r"(?:PASS|FAIL) npp_intake_commerce_text"),
)


def load_tool():
    spec = importlib.util.spec_from_file_location("npp_intake_commerce_text_under_test", SCRIPT)
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


class IntakeCommerceTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = load_tool()

    def run_inprocess(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.tool.main(list(argv))
        self.assertEqual(err.getvalue(), "")
        return code, out.getvalue().splitlines()

    def run_subprocess(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
                              capture_output=True, text=True, timeout=60)

    def findings(self, lines):
        return [line for line in lines if line.startswith("FAIL ") and line != TRAILER_FAIL]

    def test_c1_full_pass(self):
        # A tool that prints findings on a healthy main, or a wrong trailer/exit, breaks the unattended gate.
        result = self.run_subprocess()
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertEqual(result.stdout.splitlines()[-1], TRAILER_PASS)
        self.assertEqual(self.run_inprocess()[0], 0)

    def test_c2_findings_trailer(self):
        # A finding that exits 0 or hides the trailer would let a changed intake pass the guard.
        with mock.patch.object(self.tool.item_intake, "MAX_TEXT", 4):
            code, lines = self.run_inprocess()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], TRAILER_FAIL)
        at = next(i for i, line in enumerate(lines) if line.startswith("case 8 "))
        self.assertEqual(lines[at + 1], "FAIL intake-changed 8")

    def test_c2_1_unsafe_answer_read(self):
        # If the invisible-character screen stops matching, a note with a zero-width space is read as an answer.
        with mock.patch.object(self.tool.item_intake, "INVISIBLE_RE", re.compile(r"(?!x)x")):
            code, lines = self.run_inprocess()
        self.assertEqual(code, 1)
        self.assertEqual(self.findings(lines), ["FAIL unsafe-answer-read 11", "FAIL intake-changed 11"])
        at = [i for i, line in enumerate(lines) if line.startswith("case 11 ")]
        self.assertEqual(lines[at[0] + 1:at[0] + 3], ["FAIL unsafe-answer-read 11", "FAIL intake-changed 11"])
        self.assertEqual(lines[-1], TRAILER_FAIL)
        # A lenient commerce reader (accepts float, bool, extra key, over-range, negative, non-dict) must also be seen.
        with mock.patch.object(self.tool.item_intake, "commerce_answers", return_value={"price": "0.00"}):
            code, lines = self.run_inprocess()
        self.assertEqual(code, 1)
        self.assertEqual([line for line in lines if line.startswith("FAIL unsafe-answer-read")],
                         [f"FAIL unsafe-answer-read {i}" for i in range(2, 8)])

    def test_c2_2_intake_changed(self):
        # A changed answer (here a shorter MAX_TEXT) must be named, not silently accepted as drift.
        with mock.patch.object(self.tool.item_intake, "MAX_TEXT", 4):
            code, lines = self.run_inprocess()
        self.assertEqual(code, 1)
        self.assertEqual(self.findings(lines), ["FAIL intake-changed 8"])
        self.assertEqual(lines[-1], TRAILER_FAIL)

    def test_c2_3_check_error(self):
        # A repo call that raises must be one named FAIL with no exception text and no further cases.
        for name, shown in (("commerce_answers", 0), ("_text_value", 8)):
            with self.subTest(call=name):
                boom = mock.Mock(side_effect=RuntimeError("private-detail"))
                with mock.patch.object(self.tool.item_intake, name, boom):
                    code, lines = self.run_inprocess()
                self.assertEqual(code, 1)
                self.assertEqual(lines, C7[:shown] + ["FAIL check-error", TRAILER_FAIL])
                self.assertEqual(boom.call_count, 1)

    def test_c3_usage_exit_2(self):
        # Extra arguments must not be ignored: argparse's exit 2 with empty stdout.
        for args in (("extra",), ("--bogus",)):
            with self.subTest(args=args):
                result = self.run_subprocess(*args)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # A run that wrote a cache or state file under hass/ or storefront-mockup/ would not be a pure check.
        before = snapshot()
        result = self.run_subprocess()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot(), before)

    def test_c4_1_plain_run_leaves_no_bytecode(self):
        # The tool must be read-only when run plainly (no -B, no PYTHONDONTWRITEBYTECODE) on a writable checkout:
        # importing hass.skills.item_intake must not create __pycache__. A copy is used so a warm cache in the real
        # tree cannot hide the write; dropping sys.dont_write_bytecode from the script makes this fail.
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp)
            shutil.copytree(ROOT / "hass", copy / "hass",
                            ignore=shutil.ignore_patterns("__pycache__", "tests", "*.pyc"))
            (copy / "scripts/hass").mkdir(parents=True)
            shutil.copy(SCRIPT, copy / "scripts/hass" / SCRIPT.name)
            env = {k: v for k, v in os.environ.items()
                   if k not in ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX", "PYTHONPATH")}
            result = subprocess.run([sys.executable, str(copy / "scripts/hass" / SCRIPT.name)], cwd=copy, env=env,
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual((result.returncode, result.stderr), (0, ""))
            self.assertEqual(result.stdout.splitlines()[-1], TRAILER_PASS)
            self.assertEqual(sorted(str(p.relative_to(copy)) for p in copy.rglob("__pycache__")), [])

    def test_c5_output_shape(self):
        # Stray prints (exception text, tracebacks, extra notes) must not appear on stdout or stderr.
        result = self.run_subprocess()
        self.assertEqual(result.stderr, "")
        mutations = (("MAX_TEXT", 4), ("INVISIBLE_RE", re.compile(r"(?!x)x")))
        outputs = [result.stdout.splitlines()]
        for name, value in mutations:
            with mock.patch.object(self.tool.item_intake, name, value):
                outputs.append(self.run_inprocess()[1])
        with mock.patch.object(self.tool.item_intake, "_text_value", side_effect=RuntimeError("private-detail")):
            outputs.append(self.run_inprocess()[1])
        for lines in outputs:
            for line in lines:
                self.assertTrue(any(form.fullmatch(line) for form in LINE_FORMS), line)
                self.assertNotIn("private-detail", line)

    def test_c6_fixture(self):
        # With a 4-character cap only 'honey' (case 8) changes; 'none' still fits and the others were refused already.
        with mock.patch.object(self.tool.item_intake, "MAX_TEXT", 4):
            code, lines = self.run_inprocess()
        self.assertEqual(code, 1)
        self.assertEqual(self.findings(lines), ["FAIL intake-changed 8"])
        self.assertEqual(lines[-1], TRAILER_FAIL)
        self.assertEqual(self.tool.item_intake.MAX_TEXT, 400)

    def test_c7_live_pins(self):
        # The pinned answers come from the real item_intake functions, called once per case with that case's input.
        item_intake = self.tool.item_intake
        self.assertEqual(self.tool.EXPECTED, C7)
        self.assertEqual(self.tool.MUST_REFUSE, (2, 3, 4, 5, 6, 7, 11, 12, 13))
        self.assertEqual(len(self.tool.CASES), 14)
        self.assertEqual(self.tool.CASES[11][2], "honey\u200b and wax")
        self.assertEqual(self.tool.CASES[12][2], "x" * 401)
        commerce = mock.Mock(wraps=item_intake.commerce_answers)
        text = mock.Mock(wraps=item_intake._text_value)
        with mock.patch.object(item_intake, "commerce_answers", commerce), \
                mock.patch.object(item_intake, "_text_value", text):
            code, lines = self.run_inprocess()
        self.assertEqual((code, lines), (0, C7 + [TRAILER_PASS]))
        self.assertEqual([c.args[0] for c in commerce.call_args_list],
                         [case[2] for case in self.tool.CASES[:8]])
        self.assertEqual([c.args for c in text.call_args_list],
                         [(case[1], case[2]) for case in self.tool.CASES[8:]])


if __name__ == "__main__":
    unittest.main()
