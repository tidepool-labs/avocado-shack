"""Offline acceptance for the listing closure drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_job_close_rows.py"
PASS = "PASS npp_job_close_rows"
FAIL = "FAIL npp_job_close_rows"


class NppJobCloseRowsTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("npp_job_close_rows", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path[:]), patch.object(sys, "dont_write_bytecode", True):
            spec.loader.exec_module(self.tool)

    def cli(self, *args):
        with TemporaryDirectory() as cwd:
            return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                                  capture_output=True, text=True, timeout=30)

    def invoke(self, code, trailer):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.tool.main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(result, code)
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual(stderr.getvalue(), "")
        return lines[:-1]

    def collateral_close(self):
        original = self.tool.job.Jobs.close

        def close(jobs, listing, state, now):
            original(jobs, listing, state, now)
            jobs.db.execute("UPDATE npp_questions SET state='expired' WHERE job_id='c3d4'")

        return patch.object(self.tool.job.Jobs, "close", close)

    def skip_request(self):
        return patch.object(self.tool.job.Jobs, "request", lambda jobs, listing, now: None)

    def test_c1_full_pass(self):
        # The standalone entry point could import from the wrong cwd or lose its exit status.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # One finding must not short-circuit another or make the run look successful.
        with self.collateral_close(), self.skip_request():
            lines = self.invoke(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL other-job-touched 0", "FAIL close-changed 0", "FAIL other-job-touched 1",
            "FAIL other-job-touched 2", "FAIL close-changed 2", "FAIL other-job-touched 3",
            "FAIL close-changed 3", "FAIL other-job-touched 4", "FAIL close-changed 4",
        ])

    def test_c2_1_other_job_touched(self):
        # An unscoped question UPDATE can leave the target projection entirely correct.
        with self.collateral_close():
            lines = self.invoke(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         [f"FAIL other-job-touched {i}" for i in range(5)])

    def test_c2_2_close_changed(self):
        # A missed request close must be a finding, not just printed as a different state.
        with self.skip_request():
            lines = self.invoke(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         [f"FAIL close-changed {i}" for i in (0, 2, 3, 4)])

    def test_c2_3_check_error(self):
        # An unexpected repository error must not leak its text or silently pass.
        with patch.object(self.tool.job.Jobs, "close", side_effect=RuntimeError("fixture error")):
            self.assertEqual(self.invoke(1, FAIL), ["FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # Accepting a stray argument could run an unintended check.
        for arg in ("fixture", "--unknown", "--", "--help"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertIn(": error: ", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # A fixture accidentally anchored in the checkout can leave a file or rewrite an asset.
        def snapshot():
            entries = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (tree, *tree.rglob("*")):
                    stat = path.lstat()
                    entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Extra diagnostics or malformed case fields would break a line-oriented reader.
        pattern = (r"^case [0-4] job=[a-z_]+ closed=(yes|no) open_segments=[0-9]+ outcomes=[a-z_,-]+ "
                   r"questions=[a-z_:,]* versions=[0-9a-z_:,]* request=[a-z_]+$")
        for mutate in (False, True):
            with self.subTest(mutate=mutate):
                if mutate:
                    with self.collateral_close(), self.skip_request():
                        lines = self.invoke(1, FAIL)
                else:
                    lines = self.invoke(0, PASS)
                count = 0
                for line in lines:
                    if mutate and line.startswith("FAIL "):
                        self.assertRegex(line, r"^FAIL (other-job-touched|close-changed) [0-4]$")
                    else:
                        self.assertRegex(line, pattern)
                        count += 1
                self.assertEqual(count, 5)

    def test_c6_fixture(self):
        # The expired request is already unavailable; suppressing the lookup must only affect live cases.
        with self.skip_request():
            lines = self.invoke(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL close-changed 0", "FAIL close-changed 2", "FAIL close-changed 3", "FAIL close-changed 4"])
        reports = [line for line in lines if line.startswith("case ")]
        self.assertEqual([line.rsplit(" ", 1)[-1] for line in reports], ["request=open"] * 5)

    def test_c7_live_pins(self):
        # Changes to any reported row, including approved or historical rows, must change the pin.
        questions = "questions=duplicate:expired,item:answered,near_maker:expired,selling_price:expired"
        expected = [
            f"case {i} job={state} closed=yes open_segments=0 outcomes=card,{outcome},card,card "
            f"{questions} versions=1:superseded,2:{v2},3:superseded,4:superseded request={request}"
            for i, (state, outcome, v2, request) in enumerate((
                ("cancelled", "cancelled", "superseded", "closed"),
                ("expired", "expired", "superseded", "open"),
                ("approved", "approved", "approved", "closed"),
                ("cancelled", "card", "superseded", "closed"),
                ("publish_failed", "publish_failed", "superseded", "closed"),
            ))
        ]
        self.assertEqual(self.invoke(0, PASS), expected)
        self.assertEqual(list(self.tool.EXPECTED), expected)
