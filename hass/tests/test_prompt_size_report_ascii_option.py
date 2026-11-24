"""Fixture-only contracts for the ASCII-digit rule on prompt_size_report --max-omitted."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hass.tests import test_prompt_size_report as owner

SCRIPT = owner.SCRIPT


class MaxOmittedAsciiOptionTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.content = self.root / "synthetic-content"
        self.content.mkdir()
        # Reuse the owner suite's synthetic content writer (it only needs self.content).
        owner.PromptSizeReportTests.write_content(self, 300, "Sweet jam." * 30)

    def run_report(self, *options):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--content", str(self.content), *options],
            cwd=self.root, capture_output=True, text=True, timeout=30,
        )

    def assert_refused(self, value):
        result = self.run_report("--max-omitted", value)
        self.assertEqual(result.returncode, 2, repr(value))
        self.assertEqual(result.stdout, "")  # never reaches the PASS/FAIL report
        self.assertTrue(result.stderr.startswith("usage:"))
        self.assertTrue(result.stderr.endswith("error: invalid arguments; see --help\n"))
        if value:
            self.assertNotIn(value, result.stderr)  # the rejected value is never echoed

    def test_non_ascii_digits_refused(self):
        # Contract: a pasted Arabic-Indic or full-width number must not silently become the
        # threshold. Bug: int() reads them as 3/3/0 and the check enforces a hidden limit.
        for value in ("\u0663", "\uff13", "\u0660"):
            with self.subTest(value=value):
                self.assert_refused(value)

    def test_ascii_value_unchanged(self):
        # Healthy control: ASCII thresholds keep today's stdout and exit codes exactly.
        baseline = self.run_report()
        self.assertEqual(baseline.returncode, 0, baseline.stderr)
        omitted = int(dict(line.split(" ", 1) for line in baseline.stdout.splitlines()
                           if not line.startswith(("PASS", "FAIL")))["omitted"])
        self.assertGreater(omitted, 0)
        passing = self.run_report("--max-omitted", str(omitted))
        self.assertEqual((passing.returncode, passing.stdout, passing.stderr),
                         (0, baseline.stdout, ""))
        failing = self.run_report("--max-omitted", str(omitted - 1))
        self.assertEqual((failing.returncode, failing.stderr), (1, ""))
        self.assertEqual(failing.stdout.splitlines()[-2:],
                         [f"FAIL omitted-over {omitted}", "FAIL prompt_size_report"])

    def test_existing_refusals_unchanged(self):
        # Contract: today's refusals keep the same exit code and fixed message, and 0 stays valid.
        for value in ("-1", "\u00b2", ""):
            with self.subTest(value=value):
                self.assert_refused(value)
        zero = self.run_report("--max-omitted", "0")
        self.assertEqual((zero.returncode, zero.stderr), (1, ""))  # crowded fixture omits fields
        self.assertIn("FAIL omitted-over", zero.stdout)


if __name__ == "__main__":
    unittest.main()
