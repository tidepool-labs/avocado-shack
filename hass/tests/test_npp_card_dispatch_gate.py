"""Exercise the dispatch-gate CLI and its drift findings entirely offline."""

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
SCRIPT = ROOT / "scripts/hass/npp_card_dispatch_gate.py"
PASS = "PASS npp_card_dispatch_gate"
FAIL = "FAIL npp_card_dispatch_gate"
PINNED = [
    "case 0 result=True sent=send_card",
    "case 1 result=False sent=none",
    "case 2 result=False sent=none",
    "case 3 result=False sent=none",
    "case 4 result=False sent=none",
    "case 5 result=False sent=none",
    "case 6 result=False sent=none",
    "case 7 result=False sent=none",
    "case 8 result=True sent=send",
]


def snapshot(root):
    entries = {}
    for path in (root, *root.rglob("*")):
        stat = path.lstat()
        entries[path.relative_to(root)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class CardDispatchGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_card_dispatch_gate", SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError("could not load the dispatch-gate script")
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def invoke(self, *args, cwd=None):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                              capture_output=True, text=True, timeout=20)

    def invoke_main(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.tool.main([])
        self.assertEqual(stderr.getvalue(), "")
        return status, stdout.getvalue().splitlines()

    def assert_findings(self, run, expected):
        status, lines = run
        self.assertEqual(status, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], expected)

    def run_with_artifact_reader_disabled(self):
        with patch.object(self.tool.job, "read_artifact", lambda path: b""):
            return self.invoke_main()

    def test_c1_full_pass(self):
        # The standalone entry point must work without the repo as its cwd.
        with TemporaryDirectory() as cwd:
            result = self.invoke(cwd=cwd)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # A case can violate both send invariants: report both before the drift finding.
        original = self.tool.job.Jobs.dispatch
        first = True

        def send_and_refuse_first(jobs, adapter, row, text):
            nonlocal first
            if first:
                first = False
                adapter.send(row["chat"], text, [])
                return False
            return original(jobs, adapter, row, text)

        with patch.object(self.tool.job.Jobs, "dispatch", send_and_refuse_first):
            run = self.invoke_main()
        self.assert_findings(run, ["FAIL sent-on-false 0", "FAIL card-via-send 0", "FAIL dispatch-changed 0"])

    def test_c2_1_sent_on_false(self):
        # A successful send followed by a false return must not look like a refusal.
        original = self.tool.job.Jobs.dispatch

        def dispatch_then_refuse(jobs, adapter, row, text):
            original(jobs, adapter, row, text)
            return False

        with patch.object(self.tool.job.Jobs, "dispatch", dispatch_then_refuse):
            run = self.invoke_main()
        self.assert_findings(run, ["FAIL sent-on-false 0", "FAIL dispatch-changed 0",
                                   "FAIL sent-on-false 8", "FAIL dispatch-changed 8"])

    def test_c2_2_card_via_send(self):
        # A fallback to ordinary send bypasses card tracking on every card row.
        def plain_dispatch(jobs, adapter, row, text):
            adapter.send(row["chat"], text, [])
            return True

        with patch.object(self.tool.job.Jobs, "dispatch", plain_dispatch):
            run = self.invoke_main()
        self.assert_findings(run, [line for i in range(8)
                                   for line in (f"FAIL card-via-send {i}", f"FAIL dispatch-changed {i}")])

    def test_c2_3_dispatch_changed(self):
        # A successful but invalid card send still differs from the pinned answer.
        self.assert_findings(self.run_with_artifact_reader_disabled(),
                             ["FAIL dispatch-changed 6", "FAIL dispatch-changed 7"])

    def test_c2_4_check_error(self):
        # A broken reader must fail the run without printing exception contents.
        with patch.object(self.tool.job, "read_artifact", side_effect=RuntimeError("synthetic reader error")):
            status, lines = self.invoke_main()
        self.assertEqual(status, 1)
        self.assertEqual(lines, ["FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # No argument can opt out of the checks, including argparse's usual help/end marker.
        for arg in ("extra", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.invoke(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 "npp_card_dispatch_gate.py: error: no arguments are accepted")

    def test_c4_read_only(self):
        # Catch artifacts or state written into either source tree or the launch directory.
        with TemporaryDirectory() as cwd:
            roots = (ROOT / "hass", ROOT / "storefront-mockup", Path(cwd))
            before = [snapshot(root) for root in roots]
            result = self.invoke(cwd=cwd)
            self.assertEqual([snapshot(root) for root in roots], before)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c5_output_shape(self):
        # Incidental logging, including on stderr, would pollute the check output.
        result = self.invoke()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(len(lines), 10)
        for i, line in enumerate(lines[:-1]):
            self.assertRegex(line, rf"^case {i} result=(True|False) sent=(none|send(?:_card)?(?:\+send(?:_card)?)*)$")

    def test_c6_fixture(self):
        # Skipping the actual read must change just the missing and tampered PNG cases.
        status, lines = self.run_with_artifact_reader_disabled()
        self.assertEqual(status, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(lines, PINNED[:6] + [
            "case 6 result=True sent=send_card", "FAIL dispatch-changed 6",
            "case 7 result=True sent=send_card", "FAIL dispatch-changed 7",
            PINNED[8], FAIL,
        ])

    def test_c7_live_pins(self):
        # The actual dispatch boundary, not just the script's expected values, must match all nine pins.
        status, lines = self.invoke_main()
        self.assertEqual(status, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(lines, PINNED + [PASS])
