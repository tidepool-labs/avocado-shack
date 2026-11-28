"""Behavioral contracts for the offline NPP reply-link check."""

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
SCRIPT = ROOT / "scripts/hass/npp_reply_turn_link.py"
PASS = "PASS npp_reply_turn_link"
FAIL = "FAIL npp_reply_turn_link"
CLOCK_FINDINGS = ["FAIL reply-changed 0", "FAIL reply-changed 1", "FAIL reply-changed 2"]


def snapshot():
    result = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            result[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return result


class NppReplyTurnLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_reply_turn_link", SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError("cannot load the reply-link checker")
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def cli(self, *args):
        # A fresh process from outside the checkout tests the script's own import path.
        with TemporaryDirectory() as root:
            return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=root,
                                  capture_output=True, text=True, timeout=15)

    def run_check(self, code, trailer):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = self.checker.main([])
        lines = out.getvalue().splitlines()
        self.assertEqual((result, lines[-1:], err.getvalue()), (code, [trailer], ""), lines)
        return lines[:-1]

    def without_reply_clock(self):
        real_turn = self.checker.job.Jobs.turn

        def turn(jobs, job_id, message, *args):
            message.received_at = None
            return real_turn(jobs, job_id, message, *args)

        return patch.object(self.checker.job.Jobs, "turn", turn)

    def test_c1_full_pass(self):
        # Pins successful shell invocation, including the final machine-readable verdict.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(result.stderr, "")

    def test_c2_findings_trailer(self):
        # Successful repo calls can still fail the check if the receipt isn't marked dirty.
        real_reply = self.checker.job.Jobs.reply

        def reply(jobs, *args):
            row_id = real_reply(jobs, *args)
            jobs.dirty.clear()
            return row_id

        with patch.object(self.checker.job.Jobs, "reply", reply):
            lines = self.run_check(1, FAIL)
        self.assertIn("FAIL reply-changed 0", lines)

    def test_c2_1_ids_without_card(self):
        # If Jobs.reply starts granting ID permission unconditionally, both plain cases must fail.
        with patch.object(self.checker.job, "bool", lambda value: True, create=True):
            lines = self.run_check(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL")], [
            "FAIL ids-without-card 0", "FAIL reply-changed 0",
            "FAIL ids-without-card 2", "FAIL reply-changed 2",
        ])

    def test_c2_2_reply_changed(self):
        # The line comparison must catch lost threading even when ID permission is unchanged.
        with self.without_reply_clock():
            lines = self.run_check(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL")], CLOCK_FINDINGS)

    def test_c2_3_check_error(self):
        # Asset-load failure must not silently skip the check or echo the underlying error.
        with patch.object(self.checker.npp, "assets", side_effect=RuntimeError("fixture error details")):
            self.assertEqual(self.run_check(1, FAIL), ["FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # No accepted arguments, including argparse's otherwise implicit help flags.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("error: unrecognized arguments:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Detect accidental caches or writes alongside repo inputs, not just changed content.
        before = snapshot()
        result = self.cli()
        self.assertEqual(snapshot(), before)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(result.stderr, "")

    def test_c5_output_shape(self):
        # A failing run must not interleave debug output or omit its case lines.
        with self.without_reply_clock():
            lines = self.run_check(1, FAIL)
        self.assertEqual(len(lines), 7)
        for index in range(3):
            self.assertRegex(lines[2 * index], rf'^case {index} reply_to=\S+ ids_ok=[01] '
                             r'attachments=\[.*\] linked=\S* dirty=\S*$')
            self.assertEqual(lines[2 * index + 1], f"FAIL reply-changed {index}")
        self.assertEqual(lines[-1], "case 3 error=TypeError")

    def test_c6_fixture(self):
        # The mutation must persist a null clock and still exercise per-turn linking and ID permission.
        with self.without_reply_clock():
            lines = self.run_check(1, FAIL)
        self.assertEqual(lines, [
            "case 0 reply_to=None ids_ok=0 attachments=[] linked=p-r0 dirty=a1b2",
            "FAIL reply-changed 0",
            'case 1 reply_to=None ids_ok=1 attachments=["/fixture/card.png"] linked=p-r1 dirty=a1b2',
            "FAIL reply-changed 1",
            "case 2 reply_to=None ids_ok=0 attachments=[] linked=p-r2 dirty=a1b2",
            "FAIL reply-changed 2",
            "case 3 error=TypeError",
        ])

    def test_c7_live_pins(self):
        # Independent oracle: a wrong timestamp, wrong linked turn or unknown-turn send must differ.
        self.assertEqual(self.run_check(0, PASS), [
            "case 0 reply_to=2026-11-21T14:01:00+00:00 ids_ok=0 attachments=[] linked=p-r0 dirty=a1b2",
            'case 1 reply_to=2026-11-21T14:02:00+00:00 ids_ok=1 attachments=["/fixture/card.png"] linked=p-r1 dirty=a1b2',
            "case 2 reply_to=2026-11-21T14:03:00+00:00 ids_ok=0 attachments=[] linked=p-r2 dirty=a1b2",
            "case 3 error=TypeError",
        ])
