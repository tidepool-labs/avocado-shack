"""Contract tests for the offline listing segment resume check."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_segment_resume.py"
PASS = "PASS npp_segment_resume"
FAIL = "FAIL npp_segment_resume"
CAP_FINDINGS = ["FAIL resume-changed 0", "FAIL resume-changed 2", "FAIL resume-changed 3", "FAIL resume-changed 5"]
# Independent oracle from the six unpatched fixture runs.
LIVE_CASE_LINES = (
    "case 0 segments=1 open=1 revision=0 ended=- deadline_s=100 job=- versions=- turn=start@open",
    "case 1 segments=2 open=1 revision=1 ended=card deadline_s=1800 job=working versions=- turn=answer@open",
    "case 2 segments=3 open=1 revision=0 ended=card,superseded deadline_s=100 job=editing "
    "versions=1:superseded,2:superseded turn=edit@open",
    "case 3 segments=2 open=1 revision=0 ended=card deadline_s=100 job=editing versions=1:superseded turn=edit@open",
    "case 4 segments=2 open=1 revision=1 ended=card deadline_s=1800 job=editing versions=1:delivered turn=edit@open",
    "case 5 segments=2 open=1 revision=0 ended=card deadline_s=100 job=working versions=- turn=photo@open",
)


def tree_snapshot():
    snapshot = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            snapshot[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


class SegmentResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_segment_resume", SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError("could not load the segment resume check")
        cls.check = importlib.util.module_from_spec(spec)
        # The CLI deliberately bootstraps sys.path; don't leak its change into other tests.
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(cls.check)

    def cli(self, *args):
        with TemporaryDirectory() as cwd:
            return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                                  capture_output=True, text=True, timeout=10)

    def invoke(self):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.check.main([])
        self.assertEqual(stderr.getvalue(), "")
        return code, stdout.getvalue().splitlines()

    @contextmanager
    def shorter_cap(self):
        jobs = self.check.job.Jobs
        original = jobs.__init__

        def init_with_short_cap(instance, *args, **kwargs):
            original(instance, *args, **kwargs)
            pins = instance.pins
            instance.pins = {**pins, "segment": {**pins["segment"], "cap_s": 60}}

        with patch.object(jobs, "__init__", init_with_short_cap):
            yield

    def test_c1_full_pass(self):
        # The CLI could print the passing report but return a nonzero shell status.
        result = self.cli()
        self.assertEqual((result.returncode, result.stdout.splitlines()[-1]), (0, PASS))

    def test_c2_findings_trailer(self):
        # A real finding could be reported while the CLI still claims success.
        with self.shorter_cap():
            code, lines = self.invoke()
        self.assertIn("FAIL resume-changed 0", lines[:-1])
        self.assertEqual((code, lines[-1]), (1, FAIL))

    def test_c2_1_open_segments(self):
        # If the resumed segment is immediately closed, the count must fail independently of the golden line.
        original = self.check.job.Jobs._resume

        def resume_then_close(instance, *args):
            original(instance, *args)
            instance.db.execute("UPDATE npp_segments SET ended_at=?, outcome='fixture' WHERE ended_at IS NULL",
                                (self.check.T(6).isoformat(),))

        with patch.object(self.check.job.Jobs, "_resume", resume_then_close):
            code, lines = self.invoke()
        expected = [f"FAIL {reason} {index}" for index in range(6) for reason in ("open-segments", "resume-changed")]
        self.assertEqual((code, lines[-1]), (1, FAIL))
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL")], expected)

    def test_c2_2_resume_changed(self):
        # Checking only the open count would miss deadline drift with one still-open segment.
        with self.shorter_cap():
            code, lines = self.invoke()
        self.assertEqual((code, lines[-1]), (1, FAIL))
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL")], CAP_FINDINGS)

    def test_c2_3_check_error(self):
        # A repo exception must not leak details, silently skip a check, or report PASS.
        with patch.object(self.check.hass.npp, "assets", side_effect=RuntimeError("fixture detail")) as assets:
            code, lines = self.invoke()
        assets.assert_called_once_with()
        self.assertEqual((code, lines), (1, ["FAIL check-error", FAIL]))

    def test_c3_usage_exit_2(self):
        # Neither arbitrary input nor argparse's built-in help may start the check or print on stdout.
        for argument in ("extra", "--unknown", "--help", "-h", "--", ""):
            with self.subTest(argument=argument):
                result = self.cli(argument)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertIn("error: unrecognized arguments:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # A misplaced database or media root would leave files or change metadata in the checkout.
        before = tree_snapshot()
        result = self.cli()
        self.assertEqual((result.returncode, result.stdout.splitlines()[-1]), (0, PASS))
        self.assertEqual(tree_snapshot(), before)

    def test_c5_output_shape(self):
        # Debug output or buffer/log noise would break consumers of the closed line protocol.
        case_pattern = (
            r"case \d+ segments=\d+ open=\d+ revision=(?:\d+|-) ended=[a-z,-]+ "
            r"deadline_s=(?:\d+|-) job=[a-z_-]+ versions=(?:-|\d+:[a-z_]+(?:,\d+:[a-z_]+)*) "
            r"turn=[a-z-]+@(?:open|other)"
        )
        result = self.cli()
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], PASS)
        for line in lines[:-1]:
            self.assertIsNotNone(re.fullmatch(case_pattern, line), line)
        with self.shorter_cap():
            code, lines = self.invoke()
        self.assertEqual((code, lines[-1]), (1, FAIL))
        finding_pattern = r"FAIL (?:open-segments \d+|resume-changed \d+|check-error)"
        for line in lines[:-1]:
            self.assertIsNotNone(re.fullmatch(case_pattern + "|" + finding_pattern, line), line)

    def test_c6_fixture(self):
        # Only new segments use the changed cap; existing open deadlines must stay at 1800 s.
        with self.shorter_cap():
            code, lines = self.invoke()
        self.assertEqual((code, lines[-1]), (1, FAIL))
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL")], CAP_FINDINGS)
        self.assertEqual(tuple(line for line in lines[:-1] if line.startswith("case ")),
                         tuple(line.replace("deadline_s=100 ", "deadline_s=60 ") for line in LIVE_CASE_LINES))

    def test_c7_live_pins(self):
        # Unpatched real resume must keep the pinned revisions, outcomes, versions, and turn bindings.
        code, lines = self.invoke()
        self.assertEqual((code, tuple(lines)), (0, (*LIVE_CASE_LINES, PASS)))
        self.assertEqual(self.check.EXPECTED, LIVE_CASE_LINES)
