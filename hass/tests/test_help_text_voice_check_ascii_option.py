"""Offline contract: the help-size limits take ASCII digits only."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "help_text_voice_check_ascii", ROOT / "scripts/hass/help_text_voice_check.py")
assert SPEC is not None and SPEC.loader is not None
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)

FLAGS = ("--max-lines", "--max-chars")
USAGE_ERROR = "argument {flag}: must be a positive integer"


class HelpTextAsciiOptionTests(unittest.TestCase):
    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with patch("hass.capabilities.help_section", return_value="Café.\nTea."):
            with redirect_stdout(out), redirect_stderr(err):
                try:
                    code = REPORT.main(list(args))
                except SystemExit as exc:
                    code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_non_ascii_digits_refused(self):
        # Contract: only ASCII digits set a limit. Bug: int() reads Arabic-Indic,
        # full-width and other Unicode digits, so a pasted number changes PASS/FAIL.
        for flag in FLAGS:
            for value in ("\u0663", "\uff13", "\u0660", "\u0668\u0660"):
                with self.subTest(flag=flag, value=value):
                    code, out, err = self.invoke(flag, value)
                    self.assertEqual((code, out), (2, ""))
                    self.assertIn(USAGE_ERROR.format(flag=flag), err)
                    self.assertNotIn(value, err)

    def test_ascii_value_unchanged(self):
        # Healthy control: valid ASCII limits give the same report and exit code as before.
        passing = "lines 2\nchars 10\nbroken 0\nPASS help_text_voice_check\n"
        self.assertEqual(self.invoke("--max-lines", "2", "--max-chars", "10"), (0, passing, ""))
        self.assertEqual(self.invoke("--max-lines", "0002", "--max-chars", "0010"),
                         (0, passing, ""))
        failing = ("lines 2\nchars 10\nbroken 0\nFAIL too-long lines 2\n"
                   "FAIL too-long chars 10\nFAIL help_text_voice_check\n")
        self.assertEqual(self.invoke("--max-lines", "1", "--max-chars", "9"), (1, failing, ""))

    def test_existing_refusals_unchanged(self):
        # Contract: zero, negative, superscript and empty values stay argument errors
        # (exit 2, no report), and the range message stays fixed.
        for flag in FLAGS:
            for value in ("0", "-1", "\u00b2", ""):
                with self.subTest(flag=flag, value=value):
                    code, out, err = self.invoke(flag, value)
                    self.assertEqual((code, out), (2, ""))
                    self.assertIn("usage:", err)
                    if value in ("0", "-1"):
                        self.assertIn(USAGE_ERROR.format(flag=flag), err)
