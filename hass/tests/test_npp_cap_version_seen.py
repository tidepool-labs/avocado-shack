"""Offline contract for the cap-born version checker."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass.npp import reply, stages
from hass.npp.job import Plan

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_cap_version_seen.py"
SPEC = importlib.util.spec_from_file_location("npp_cap_version_seen", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)

PASS = "PASS npp_cap_version_seen"
FAIL = "FAIL npp_cap_version_seen"


class NppCapVersionSeenTests(unittest.TestCase):
    def setUp(self):
        self.cwd = self.enterContext(TemporaryDirectory(dir=ROOT))

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.cwd,
                              capture_output=True, text=True, timeout=15, check=False)

    def run_main(self, code, trailer):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = checker.main([])
        self.assertEqual(result, code)
        self.assertEqual(stderr.getvalue(), "")
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def assert_cli_failure(self, result):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [FAIL])
        return lines[:-1]

    def test_c1_full_pass(self):
        # A clean cap presented as a bare Plan must not report a false failure.
        plan = Plan(listing={**checker.LISTING, reply.SEEN: 2}, identified=True)
        with patch.object(stages.ProductionStages, "cap", return_value=plan):
            lines = self.run_main(0, PASS)
        self.assertFalse(any(line.startswith("FAIL ") for line in lines))

    def test_c2_findings_trailer(self):
        # A multi-finding report must not stop at the first reason or exit 0.
        plan = Plan(listing=checker.LISTING, identified=True)
        with patch.object(stages.ProductionStages, "cap", return_value=(plan, "card")):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines[-2:], ["FAIL seen-missing", "FAIL edit-diverges"])

    def test_c2_1_seen_missing(self):
        # Matching edit outcomes must not hide an absent stamp.
        plan = Plan(listing=checker.LISTING, identified=True)
        with (patch.object(stages.ProductionStages, "cap", return_value=plan),
              patch.object(reply.Stages, "edit", return_value=plan)):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, ["cap ready=yes", "cap stamped=no", "edit capped=patch",
                                 "edit stamped=patch", "FAIL seen-missing"])

    def test_c2_2_edit_diverges(self):
        # A present but wrong stamp can still reread the caption.
        plan = Plan(listing={**checker.LISTING, reply.SEEN: 0}, identified=True)
        with patch.object(stages.ProductionStages, "cap", return_value=plan):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, ["cap ready=yes", "cap stamped=yes", "edit capped=ask_edit_unclear",
                                 "edit stamped=patch", "FAIL edit-diverges"])

    def test_c2_3_cap_not_ready(self):
        # The fallback listing is for comparison, not evidence of a ready cap.
        with patch.object(stages.ProductionStages, "start_plan", return_value=Plan()):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, ["cap ready=no", "cap stamped=no", "edit capped=ask_edit_unclear",
                                 "edit stamped=patch", "FAIL cap-not-ready",
                                 "FAIL seen-missing", "FAIL edit-diverges"])

    def test_c2_4_check_error(self):
        # Stage exceptions must not leak details or yield a traceback or PASS.
        error = ValueError("synthetic private exception detail")
        with patch.object(stages.ProductionStages, "cap", side_effect=error):
            self.assertEqual(self.run_main(1, FAIL), ["FAIL check-error"])
        plan = Plan(listing={**checker.LISTING, reply.SEEN: 2}, identified=True)
        with (patch.object(stages.ProductionStages, "cap", return_value=plan),
              patch.object(reply.Stages, "edit", side_effect=[error, plan])):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, ["cap ready=yes", "cap stamped=yes", "edit stamped=patch",
                                 "FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # No argument, not even a help flag or end-of-options marker, is accepted.
        for arg in ("extra", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("error: unrecognized arguments:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Detect creations, overwrites, or directory changes in either source tree.
        def snapshot():
            result = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (tree, *tree.rglob("*")):
                    info = path.lstat()
                    result[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return result

        before = snapshot()
        self.assert_cli_failure(self.run_cli())
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # An accidental debug print, reply body, or stdout preamble breaks the report.
        lines = self.assert_cli_failure(self.run_cli())
        self.assertEqual(len(lines), 6)
        for line, pattern in zip(lines, (
            r"cap ready=(yes|no)", r"cap stamped=(yes|no)",
            r"edit capped=[A-Za-z_][A-Za-z_0-9]*", r"edit stamped=[A-Za-z_][A-Za-z_0-9]*",
            r"FAIL (seen-missing|edit-diverges|cap-not-ready|check-error)",
            r"FAIL (seen-missing|edit-diverges|cap-not-ready|check-error)",
        ), strict=True):
            self.assertRegex(line, rf"\A{pattern}\Z")

    def test_c6_fixture(self):
        # Only the plan is replaced: the real cap returns the (plan, card) tuple.
        plan = Plan(listing={**checker.LISTING, "_texts": 2}, identified=True)
        with patch.object(stages.ProductionStages, "start_plan", return_value=plan):
            lines = self.run_main(0, PASS)
        self.assertEqual(lines, ["cap ready=yes", "cap stamped=yes", "edit capped=patch",
                                 "edit stamped=patch"])

    def test_c7_live_pins(self):
        # Detect base/fixture drift or a regression in how the checker calls either edit.
        lines = self.assert_cli_failure(self.run_cli())
        self.assertEqual(lines, ["cap ready=yes", "cap stamped=no", "edit capped=ask_edit_unclear",
                                 "edit stamped=patch", "FAIL seen-missing", "FAIL edit-diverges"])
