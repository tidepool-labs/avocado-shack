"""CLI contract and mutation checks for the offline receipt-state replay."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_receipt_refresh_states.py"
PASS = "PASS npp_receipt_refresh_states"
FAIL = "FAIL npp_receipt_refresh_states"


class NppReceiptRefreshStatesTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.enterContext(patch.object(tempfile, "tempdir", str(self.root)))
        self.enterContext(patch.object(sys, "path", sys.path.copy()))
        spec = importlib.util.spec_from_file_location("npp_receipt_refresh_states", SCRIPT)
        if spec is None or spec.loader is None:
            self.fail(f"Cannot load {SCRIPT.name}")
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)

    def cli(self, *args):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            env={**os.environ, "TMPDIR": str(self.root)},
            text=True, capture_output=True, timeout=15,
        )
        return result.returncode, result.stdout, result.stderr

    def invoke(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.tool.main([])
        return code, out.getvalue(), err.getvalue()

    def assert_run(self, result, code, trailer):
        status, out, err = result
        self.assertEqual(status, code, out + err)
        self.assertEqual(err, "")
        lines = out.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def permissive_confirmation(self):
        def confirm_everything(source, row_id, png_sha, queued, now):
            return now, "guid-fixture"

        with patch.object(self.tool.job, "confirmation", confirm_everything):
            return self.invoke()

    def test_c1_full_pass(self):
        # A standalone invocation from outside the checkout must import and pass.
        self.assert_run(self.cli(), 0, PASS)

    def test_c2_findings_trailer(self):
        # A state regression with valid delivery must set the overall failing status.
        refresh = self.tool.job.Jobs.refresh_receipts

        def forget_card_out(jobs):
            refresh(jobs)
            jobs.db.execute("UPDATE npp_jobs SET state='editing' WHERE state='card_out'")

        with patch.object(self.tool.job.Jobs, "refresh_receipts", forget_card_out):
            lines = self.assert_run(self.invoke(), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL receipt-changed 0", "FAIL receipt-changed 10"])

    def test_c2_1_card_out_without_delivery(self):
        # A version marked delivered without a timestamp must not justify card_out.
        refresh = self.tool.job.Jobs.refresh_receipts

        def clear_delivery(jobs):
            refresh(jobs)
            jobs.db.execute("UPDATE npp_versions SET delivered_at=NULL")

        with patch.object(self.tool.job.Jobs, "refresh_receipts", clear_delivery):
            lines = self.assert_run(self.invoke(), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL card-out-without-delivery 0", "FAIL receipt-changed 0",
            "FAIL receipt-changed 1", "FAIL receipt-changed 6", "FAIL receipt-changed 7",
            "FAIL card-out-without-delivery 10", "FAIL receipt-changed 10",
        ])

    def test_c2_2_receipt_changed(self):
        # A changed observation must yield exactly one finding beside that case.
        lines = self.assert_run(self.permissive_confirmation(), 1, FAIL)
        for i in (2, 3, 4, 5, 9, 10):
            with self.subTest(case=i):
                finding = f"FAIL receipt-changed {i}"
                self.assertEqual(lines.count(finding), 1)
                self.assertTrue(lines[lines.index(finding) - 1].startswith(f"case {i} "))

    def test_c2_3_check_error(self):
        # An unexpected exception must not turn into a traceback, leak, or pass.
        with patch.object(self.tool.job.Jobs, "refresh_receipts", side_effect=RuntimeError("fixture detail")):
            lines = self.assert_run(self.invoke(), 1, FAIL)
        self.assertEqual(lines, ["FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # Positional, flag, help and bare end-of-options input must all be refused.
        for arg in ("fixture", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                status, out, err = self.cli(arg)
                self.assertEqual(status, 2)
                self.assertEqual(out.splitlines()[-1:], [])
                self.assertTrue(err.startswith("usage:"), err)
                self.assertTrue(err.splitlines()[-1].endswith("error: no arguments are accepted"), err)

    def test_c4_read_only(self):
        # A write into source assets/state (or stray bytecode) changes the snapshot.
        def snapshot():
            entries = {}
            for name in ("hass", "storefront-mockup"):
                tree = ROOT / name
                for path in (tree, *tree.rglob("*")):
                    stat = path.lstat()
                    entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
            return entries

        before = snapshot()
        self.assert_run(self.cli(), 0, PASS)
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_c5_output_shape(self):
        # Extra debug output, missing cases, or mixed stdout/stderr break consumers.
        lines = self.assert_run(self.cli(), 0, PASS)
        self.assertEqual(len(lines), 11)
        for i, line in enumerate(lines):
            self.assertRegex(line, rf"\Acase {i} version=[a-z_]+ delivered=(yes|no) guid=(yes|no) job=[a-z_]+\Z")

    def test_c6_fixture(self):
        # A permissive confirmer must expose the exact changed cases, not pass a copied table.
        lines = self.assert_run(self.permissive_confirmation(), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL receipt-changed 2", "FAIL receipt-changed 3", "FAIL receipt-changed 4",
            "FAIL receipt-changed 5", "FAIL receipt-changed 9", "FAIL receipt-changed 10",
        ])

    def test_c7_live_pins(self):
        # Pin real persisted state and output independently of the script's EXPECTED table.
        self.assertEqual(self.assert_run(self.invoke(), 0, PASS), [
            "case 0 version=delivered delivered=yes guid=yes job=card_out",
            "case 1 version=superseded delivered=yes guid=yes job=editing",
            "case 2 version=queued delivered=no guid=no job=editing",
            "case 3 version=queued delivered=no guid=no job=editing",
            "case 4 version=queued delivered=no guid=no job=editing",
            "case 5 version=queued delivered=no guid=no job=editing",
            "case 6 version=delivered delivered=yes guid=yes job=asking",
            "case 7 version=delivered delivered=yes guid=yes job=editing",
            "case 8 version=queued delivered=no guid=no job=editing",
            "case 9 version=queued delivered=no guid=no job=editing",
            "case 10 version=delivered delivered=yes guid=no job=card_out",
        ])
