"""Exercise the offline NPP owner-answer check against real Jobs fixtures."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_owner_answer_binding.py"
PASS = "PASS npp_owner_answer_binding"
FAIL = "FAIL npp_owner_answer_binding"


class OwnerAnswerBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        # The standalone CLI bootstraps sys.path; don't leak that change in-process.
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(cls.tool)

    def cli(self, *args):
        with TemporaryDirectory() as cwd:
            return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                                  capture_output=True, text=True, timeout=15)

    def invoke(self, code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            actual = self.tool.main([])
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(actual, code)
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def findings(self, lines):
        return [line for line in lines if line.startswith("FAIL ")]

    def test_c1_full_pass(self):
        # The CLI entry point must actually exit zero and use the stable trailer.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # A non-None return without a persisted answer must fail, not just warn.
        original = self.tool.job.Jobs.answer

        def phantom_answer(jobs, row, msg, polarity, accepted, now):
            result = original(jobs, row, msg, polarity, accepted, now)
            return "npp-working" if msg.provider_id == "p-ans-4" else result

        with patch.object(self.tool.job.Jobs, "answer", phantom_answer):
            lines = self.invoke(1, FAIL)
        self.assertEqual(self.findings(lines), ["FAIL answer-row-without-binding 4", "FAIL answer-changed 4"])

    def test_c2_1_answer_row_without_binding(self):
        # A seemingly refused reply must not leave an answer written behind.
        original = self.tool.job.Jobs.answer

        def drop_disposition(jobs, row, msg, polarity, accepted, now):
            original(jobs, row, msg, polarity, accepted, now)
            return None

        with patch.object(self.tool.job.Jobs, "answer", drop_disposition):
            lines = self.invoke(1, FAIL)
        self.assertEqual(self.findings(lines), [
            "FAIL answer-row-without-binding 0", "FAIL answer-changed 0",
            "FAIL answer-row-without-binding 1", "FAIL answer-changed 1",
            "FAIL answer-row-without-binding 2", "FAIL answer-changed 2",
            "FAIL answer-row-without-binding 3", "FAIL answer-changed 3",
        ])

    def test_c2_2_answer_changed(self):
        # Even when rows and return values agree, changed case lines are findings.
        with patch.object(self.tool.job, "instant", lambda value: None):
            lines = self.invoke(1, FAIL)
        self.assertEqual(lines[:8], [line for i in range(4) for line in (
            f"case {i} None answers=0 job=asking", f"FAIL answer-changed {i}",
        )])
        self.assertEqual(self.findings(lines), [f"FAIL answer-changed {i}" for i in range(4)])

    def test_c2_3_check_error(self):
        # A broken repo call must neither pass nor leak exception details.
        with patch.object(self.tool.hass.npp, "assets", side_effect=RuntimeError("fixture detail")):
            self.assertEqual(self.invoke(1, FAIL), ["FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # Arguments (including help) cannot silently run the check or return success.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # A repo-relative database or media root could write into the checkout.
        def snapshot():
            entries = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (tree, *tree.rglob("*")):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug prints or warnings must not break the line protocol.
        result = self.cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [PASS])
        self.assertEqual(len(lines), 13)
        for i, line in enumerate(lines[:-1]):
            self.assertRegex(line, rf"^case {i} (None|npp-working|cancelled) "
                                   r"answers=[0-9]+ job=(asking|working|cancelled)$")

    def test_c6_fixture(self):
        # Disabling the real time parser must affect just the four valid bindings.
        with patch.object(self.tool.job, "instant", lambda value: None):
            lines = self.invoke(1, FAIL)
        self.assertEqual(self.findings(lines), [
            "FAIL answer-changed 0", "FAIL answer-changed 1", "FAIL answer-changed 2", "FAIL answer-changed 3",
        ])
        self.assertEqual([line for line in lines if line.startswith("case ")],
                         [f"case {i} None answers=0 job=asking" for i in range(12)])

    def test_c7_live_pins(self):
        # The actual job-store outcomes pin cancellation, resumption and all refusals.
        self.assertEqual(self.invoke(0, PASS), [
            "case 0 npp-working answers=1 job=working",
            "case 1 cancelled answers=1 job=cancelled",
            "case 2 npp-working answers=1 job=working",
            "case 3 npp-working answers=1 job=working",
            "case 4 None answers=0 job=asking",
            "case 5 None answers=0 job=asking",
            "case 6 None answers=0 job=asking",
            "case 7 None answers=0 job=asking",
            "case 8 None answers=0 job=asking",
            "case 9 None answers=0 job=asking",
            "case 10 None answers=0 job=asking",
            "case 11 None answers=0 job=asking",
        ])
