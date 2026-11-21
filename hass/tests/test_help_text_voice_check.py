"""Offline CLI contract for the registry help report."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/help_text_voice_check.py"
SPEC = importlib.util.spec_from_file_location("help_text_voice_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


class HelpTextVoiceCheckTests(unittest.TestCase):
    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = REPORT.main(list(args))
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def with_help(self, text, *args):
        with patch("hass.capabilities.help_section", return_value=text):
            return self.invoke(*args)

    def assert_report(self, result, code, *lines):
        self.assertEqual(result, (code, "\n".join(lines) + "\n", ""))

    def test_c1_full_pass(self):
        # Limits are inclusive and count characters, not UTF-8 bytes.
        result = self.with_help("Café.\nTea.", "--max-lines", "2", "--max-chars", "10")
        self.assert_report(result, 0, "lines 2", "chars 10", "broken 0",
                           "PASS help_text_voice_check")

    def test_c2_findings_trailer(self):
        # A first-failure return would hide the two independent size findings.
        result = self.with_help("Tea.\nQueued.", "--max-lines", "1", "--max-chars", "1")
        self.assert_report(result, 1, "lines 2", "chars 12", "broken 1",
                           "FAIL voice 1", "FAIL too-long lines 2", "FAIL too-long chars 12",
                           "FAIL help_text_voice_check")

    def test_c2_1_help_error(self):
        # A source failure must not escape as a traceback or disclose its details.
        with patch("hass.capabilities.help_section", side_effect=ValueError("Synthetic detail.")):
            result = self.invoke()
        self.assert_report(result, 1, "FAIL help-error", "FAIL help_text_voice_check")

    def test_c2_2_voice(self):
        # An in-bounds reply can still fail the voice check.
        self.assert_report(self.with_help("Queued."), 1, "lines 1", "chars 7", "broken 1",
                           "FAIL voice 1", "FAIL help_text_voice_check")

    def test_c2_3_too_long_lines(self):
        # A compliant reply can cross the default line budget alone.
        self.assert_report(self.with_help("Tea.\n" * 81), 1, "lines 81", "chars 405", "broken 0",
                           "FAIL too-long lines 81", "FAIL help_text_voice_check")

    def test_c2_4_too_long_chars(self):
        # A single compliant line can cross the default character budget alone.
        self.assert_report(self.with_help("a" * 6001), 1, "lines 1", "chars 6001", "broken 0",
                           "FAIL too-long chars 6001", "FAIL help_text_voice_check")

    def test_c3_usage_exit_2(self):
        # Bad syntax must stay an argparse usage error, not a report finding.
        for args in (("--unknown",), ("--max-lines",), ("--max-chars",)):
            with self.subTest(args=args):
                code, out, err = self.invoke(*args)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("usage:", err)
        for flag in ("--max-lines", "--max-chars"):
            for value in ("0", "-1", "1.5", "no"):
                with self.subTest(flag=flag, value=value):
                    code, out, err = self.invoke(flag, value)
                    self.assertEqual((code, out), (2, ""))
                    self.assertIn("usage:", err)

    def test_c4_read_only(self):
        # A generated sidecar in the caller's directory would violate read-only use.
        with tempfile.TemporaryDirectory(dir=ROOT) as cwd:
            result = subprocess.run([sys.executable, "-B", str(SCRIPT)], cwd=cwd,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.splitlines()[-1], "PASS help_text_voice_check")
            self.assertEqual(result.stderr, "")
            self.assertEqual(list(Path(cwd).iterdir()), [])

    def test_c5_no_private_values(self):
        # Failure diagnostics must not quote the sentence or the broken rule.
        result = self.with_help("The pretend teapot is queued.")
        self.assert_report(result, 1, "lines 1", "chars 29", "broken 1",
                           "FAIL voice 1", "FAIL help_text_voice_check")

    def test_c6_merged_help(self):
        # Registry changes can move the counts or break Hass's voice.
        self.assert_report(self.invoke(), 0, "lines 49", "chars 4411", "broken 0",
                           "PASS help_text_voice_check")

    def test_c7_patched_words(self):
        # Counting just the first rule hit would miss the second banned word.
        result = self.with_help("Say help. The interpreter is queued.")
        self.assert_report(result, 1, "lines 1", "chars 36", "broken 2",
                           "FAIL voice 2", "FAIL help_text_voice_check")
