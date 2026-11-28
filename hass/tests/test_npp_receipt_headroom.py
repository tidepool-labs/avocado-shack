"""Offline CLI and failure-path contracts for the NPP receipt drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_receipt_headroom.py"
PASS = "PASS npp_receipt_headroom"
FAIL = "FAIL npp_receipt_headroom"


def load_checker():
    spec = importlib.util.spec_from_file_location("npp_receipt_headroom", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # The script adds its checkout to sys.path. Don't retain that change in the suite.
    with patch.object(sys, "path", sys.path.copy()):
        spec.loader.exec_module(module)
    return module


def cli(*args):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
        capture_output=True, text=True, timeout=15,
    )


def snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class NppReceiptHeadroomTests(unittest.TestCase):
    def run_checker(self, module):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = module.main([])
        self.assertEqual(stderr.getvalue(), "")
        return code, stdout.getvalue().splitlines()

    def test_c1_full_pass(self):
        # The entrypoint must import from the checkout and propagate success to the shell.
        result = cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # Finding one issue must not skip the next runnable check or lose the trailer.
        module = load_checker()
        write = module.Jobs.write_receipts

        def write_then_report_failure(jobs):
            write(jobs)
            jobs.c._problem("error", "npp-receipt-write-failed")

        with (
            patch.object(module.Jobs, "write_receipts", write_then_report_failure),
            patch.object(module.receipt, "RECEIPT_MAX", 100000),
        ):
            code, lines = self.run_checker(module)
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["receipt rows=100 bytes=70177 cap=100000",
                                 "FAIL receipt-not-written", "FAIL receipt-over-half", FAIL])

    def test_c2_1_receipt_not_written(self):
        # A silent no-op and a caught refusal both have to fail closed, once each.
        module = load_checker()
        with patch.object(module.Jobs, "write_receipts", return_value=None):
            self.assertEqual(self.run_checker(module), (1, ["FAIL receipt-not-written", FAIL]))
        with patch.object(module.receipt.Artifacts, "write_receipt", side_effect=ValueError):
            self.assertEqual(self.run_checker(module), (1, ["FAIL receipt-not-written", FAIL]))

    def test_c2_2_receipt_over_half(self):
        # Exactly half is allowed; one byte less in the cap makes the same receipt fail.
        module = load_checker()
        for cap, code, trailer in ((140354, 0, [PASS]), (140353, 1, ["FAIL receipt-over-half", FAIL])):
            with self.subTest(cap=cap), patch.object(module.receipt, "RECEIPT_MAX", cap):
                self.assertEqual(self.run_checker(module),
                                 (code, [f"receipt rows=100 bytes=70177 cap={cap}", *trailer]))

    def test_c2_3_check_error(self):
        # A raised error at any of these boundaries must not leak text or pass silently.
        module = load_checker()
        for owner, method in ((module, "Jobs"), (module.Jobs, "write_receipts"),
                              (module.receipt, "read_artifact")):
            with self.subTest(method=method), patch.object(owner, method, side_effect=RuntimeError("fixture detail")):
                self.assertEqual(self.run_checker(module), (1, ["FAIL check-error", FAIL]))

    def test_c3_usage_exit_2(self):
        # No flag, positional token, or option terminator may run the checker.
        for arg in ("unexpected", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertIn("error:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # A misdirected media root or asset rewrite would leave a changed tree entry.
        before = snapshot()
        result = cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # The CLI must not print payloads, paths, asset pins, or incidental diagnostics.
        result = cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        stats, trailer = result.stdout.splitlines()
        self.assertRegex(stats, r"\Areceipt rows=[0-9]+ bytes=[0-9]+ cap=[0-9]+\Z")
        self.assertEqual(trailer, PASS)

    def test_c6_fixture(self):
        # The single-row fixture pins the base receipt plus one attempt and version.
        module = load_checker()
        with patch.object(module, "ROWS", 1):
            self.assertEqual(self.run_checker(module), (0, ["receipt rows=1 bytes=5728 cap=262144", PASS]))

    def test_c7_live_pins(self):
        # Real asset or serialization drift must not silently move the measured baseline.
        result = cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, f"receipt rows=100 bytes=70177 cap=262144\n{PASS}\n")
