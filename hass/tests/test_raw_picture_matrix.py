"""Behavioral contract for the fixture-only S6 raw-photo audit."""

import builtins
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass import live_policy, publish_live
from hass.npp import picture

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/raw_picture_matrix.py"


def snapshot(root):
    entries = {}
    for path in (root, *root.rglob("*")):
        info = path.lstat()
        entries[path.relative_to(root)] = (info.st_size, info.st_mtime_ns)
    return entries


class RawPictureMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PIL import Image, ImageFilter  # noqa: F401
        except ImportError as exc:
            raise unittest.SkipTest("Pillow is required for the synthetic raw-photo matrix") from exc
        spec = importlib.util.spec_from_file_location("raw_picture_matrix", SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError("Could not load the raw-photo matrix script")
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def run_main(self):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        return code, stdout.getvalue().splitlines(), stderr.getvalue()

    def run_patched_pass(self):
        with patch.dict(publish_live.PATTERNS, email=live_policy.EMAIL):
            return self.run_main()

    def run_cli(self, cwd, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                              capture_output=True, text=True, timeout=30)

    def assert_outcome(self, code, lines, expected_code, trailer):
        self.assertEqual(code, expected_code)
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)

    def assert_findings(self, code, lines, *findings):
        self.assert_outcome(code, lines, 1, "FAIL raw_picture_matrix")
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(findings))

    def test_c1_full_pass(self):
        # A finding-free run must not still exit nonzero or use the FAIL trailer.
        code, lines, _ = self.run_patched_pass()
        self.assert_outcome(code, lines, 0, "PASS raw_picture_matrix")
        self.assertFalse(any(line.startswith("FAIL ") for line in lines))

    def test_c2_findings_trailer(self):
        # Mixed failures must not short-circuit or reorder the findings.
        outcomes = ["style", None, RuntimeError(), None] + ["style"] * 104
        with patch.object(picture, "_raw_problem", side_effect=outcomes):
            code, lines, _ = self.run_main()
        self.assert_findings(code, lines,
                             "FAIL safe-cell-refused",
                             "FAIL raw-allowed-unsafe sharp-false-clean-false",
                             "FAIL check-error",
                             "FAIL raw-allowed-unsafe sharp-false-none-true")

    def test_c2_1_pillow_missing(self):
        # A missing optional dependency must be a named failure, not a traceback.
        original_import = builtins.__import__

        def without_pillow(name, *args, **kwargs):
            if name == "PIL" or name.startswith("PIL."):
                raise ImportError("fixture import refusal")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=without_pillow):
            code, lines, stderr = self.run_main()
        self.assert_findings(code, lines, "FAIL pillow-missing")
        self.assertEqual(stderr, "")

    def test_c2_2_check_error(self):
        # Repeated exceptions must yield one finding and never print exception text.
        with patch.object(picture, "_raw_problem", side_effect=RuntimeError("fixture diagnostic")):
            code, lines, stderr = self.run_main()
        self.assert_findings(code, lines, "FAIL check-error")
        self.assertNotIn("fixture diagnostic", "\n".join(lines) + stderr)
        self.assertEqual(stderr, "")

    def test_c2_3_safe_cell_refused(self):
        # An all-refusing decision is also wrong, even with no unsafe allowance.
        with patch.object(picture, "_raw_problem", return_value="style"):
            code, lines, _ = self.run_main()
        self.assert_findings(code, lines, "FAIL safe-cell-refused")

    def test_c2_4_raw_allowed_unsafe(self):
        # Report each unexpected allowance, including one at the very last cell.
        outcomes = [None, None] + ["style"] * 105 + [None]
        with patch.object(picture, "_raw_problem", side_effect=outcomes):
            code, lines, _ = self.run_main()
        self.assert_findings(code, lines,
                             "FAIL raw-allowed-unsafe sharp-false-clean-false",
                             "FAIL raw-allowed-unsafe blurry-none-path-none")

    def test_c3_usage_exit_2(self):
        # Neither help, unknown options, a delimiter nor positional values are accepted.
        with tempfile.TemporaryDirectory() as cwd:
            for arg in ("--unknown", "--help", "-h", "--", "unexpected-value"):
                with self.subTest(arg=arg):
                    result = self.run_cli(cwd, arg)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")  # There is no stdout trailer.
                    self.assertTrue(result.stderr.startswith("usage: "))

    def test_c4_read_only(self):
        # An on-disk blur, cache or report could leave output or touch an existing file.
        with tempfile.TemporaryDirectory() as cwd:
            work = Path(cwd)
            (work / "fixture.txt").write_text("fixture", encoding="utf-8")
            roots = (work, ROOT / "hass")
            before = [snapshot(root) for root in roots]
            result = self.run_cli(cwd)
            self.assert_outcome(result.returncode, result.stdout.splitlines(), 1, "FAIL raw_picture_matrix")
            self.assertEqual([snapshot(root) for root in roots], before)

    def test_c5_output_shape(self):
        # Reject stray debug output or disclosure of any read, even on stderr.
        code, lines, stderr = self.run_main()
        self.assert_outcome(code, lines, 1, "FAIL raw_picture_matrix")
        self.assertEqual(stderr, "")
        shape = (
            r"(?:cells 108|allowed [0-9]+|reason (?:style|blurry|other) [0-9]+"
            r"|FAIL (?:pillow-missing|check-error|safe-cell-refused)"
            r"|FAIL raw-allowed-unsafe (?:sharp|blurry)-(?:false|true|none)"
            r"-(?:clean|none|money|contact|contact-short|path)-(?:true|false|none)"
            r"|(?:PASS|FAIL) raw_picture_matrix)"
        )
        for line in lines:
            self.assertIsNotNone(re.fullmatch(shape, line), line)
        output = "\n".join(lines) + stderr
        for read in ("Raspberry jam", "only " + "$4.99", "write ab" + "@" + "example.com",
                     "write a" + "@" + "example.com", "/home/" + "someone"):
            self.assertNotIn(read, output)

    def test_c6_patched_pass(self):
        # A stricter email check must remove only the unsafe allowance, not the safe cell.
        code, lines, _ = self.run_patched_pass()
        self.assert_outcome(code, lines, 0, "PASS raw_picture_matrix")
        self.assertEqual([line for line in lines if line.startswith("allowed ")], ["allowed 1"])

    def test_c7_live_matrix(self):
        # Pin the measured unpatched matrix, including the lone known gap.
        code, lines, stderr = self.run_main()
        self.assert_findings(code, lines, "FAIL raw-allowed-unsafe sharp-false-contact-short-true")
        self.assertEqual(lines[:5], ["cells 108", "allowed 2", "reason style 88",
                                     "reason blurry 18", "reason other 0"])
        self.assertEqual(len(lines), 7)
        self.assertEqual(stderr, "")
