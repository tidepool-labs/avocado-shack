"""Contract tests for the offline delivery receipt diagnostic (not a product fix)."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_delivery_receipt_rules.py"
PASS = "PASS npp_delivery_receipt_rules"
FAIL = "FAIL npp_delivery_receipt_rules"
CONFIRMED = (datetime(2026, 11, 21, 10, 1, tzinfo=timezone.utc), "g-1")


def snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class DeliveryReceiptRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("receipt_rules_checker", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.checker = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(cls.checker)

    def cli(self, *args):
        with tempfile.TemporaryDirectory() as directory:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=directory,
                capture_output=True, text=True, timeout=10,
            )

    def run_checker(self, code, trailer, **replacements):
        out, err = io.StringIO(), io.StringIO()
        with (patch.multiple(self.checker.receipt, **replacements),
              redirect_stdout(out), redirect_stderr(err)):
            actual_code = self.checker.main([])
        return self.assert_run(actual_code, out.getvalue(), err.getvalue(), code, trailer)

    def assert_run(self, actual_code, stdout, stderr, code, trailer):
        self.assertEqual(actual_code, code)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def assert_findings(self, lines, *reasons):
        self.assertEqual([line for line in lines if line.startswith("FAIL")],
                         [f"FAIL {reason}" for reason in reasons])

    def assert_queue_results(self, lines, status):
        self.assertEqual([line for line in lines if line.startswith("queued-bad")],
                         [f"queued-bad {i} result={status}" for i in range(3)])

    def for_unreadable_queue(self, replacement):
        real = self.checker.receipt.confirmation

        def confirmation(source, row_id, png_sha, queued, now):
            if queued is None:
                return replacement
            return real(source, row_id, png_sha, queued, now)

        return confirmation

    def test_c1_full_pass(self):
        # A checker that always exits red on unreadable queue text cannot pass.
        lines = self.run_checker(0, PASS, confirmation=self.for_unreadable_queue(None))
        self.assert_findings(lines)
        self.assert_queue_results(lines, "none")

    def test_c2_findings_trailer(self):
        # A single receipt mismatch must flip both the return code and trailer.
        passing = self.for_unreadable_queue(None)

        def confirmation(*args):
            result = passing(*args)
            return None if result == CONFIRMED else result

        lines = self.run_checker(1, FAIL, confirmation=confirmation)
        self.assert_findings(lines, "record-rule 0")
        self.assert_queue_results(lines, "none")

    def test_c2_1_record_rule(self):
        # Detect a skipped receipt case, duplicate finding, or hard-coded status.
        real = self.checker.receipt.confirmation

        def confirmation(source, row_id, png_sha, queued, now):
            if queued is None:
                return None
            return CONFIRMED if real(source, row_id, png_sha, queued, now) is None else None

        lines = self.run_checker(1, FAIL, confirmation=confirmation)
        labels = [*range(10), "oserror", "valueerror", "no-source"]
        self.assert_findings(lines, *(f"record-rule {label}" for label in labels))
        self.assertEqual([line for line in lines if line.startswith("record ")],
                         [f"record {i} ok=no" for i in range(10)])

    def test_c2_2_instant_rule(self):
        # Ignoring the awareness observation would miss a spuriously parsed integer.
        real = self.checker.receipt.instant
        lines = self.run_checker(
            1, FAIL, instant=lambda value: CONFIRMED[0] if value == 5 else real(value),
            confirmation=self.for_unreadable_queue(None),
        )
        self.assert_findings(lines, "instant-rule 5")

    def test_c2_3_queued_unreadable_raises(self):
        # An exception at confirmation must not be mistaken for no receipt or a crash.
        real = self.checker.receipt.confirmation

        def confirmation(source, row_id, png_sha, queued, now):
            if queued is None:
                raise RuntimeError("synthetic confirmation error")
            return real(source, row_id, png_sha, queued, now)

        lines = self.run_checker(1, FAIL, confirmation=confirmation)
        self.assert_queue_results(lines, "raises")
        self.assert_findings(lines, *(f"queued-unreadable-raises {i}" for i in range(3)))

    def test_c2_3_queued_unreadable_non_none(self):
        # Catch a spurious delivery tuple and a falsey non-None result independently.
        for result in (CONFIRMED, False):
            with self.subTest(result=result):
                lines = self.run_checker(1, FAIL, confirmation=self.for_unreadable_queue(result))
                self.assert_queue_results(lines, "non-none")
                self.assert_findings(lines, *(f"queued-unreadable-non-none {i}" for i in range(3)))

    def test_c2_4_check_error(self):
        # These exceptions are check errors, not receipt findings or leaked tracebacks.
        real_instant = self.checker.receipt.instant
        real_confirmation = self.for_unreadable_queue(None)

        def instant(value):
            if value == 5 or value == "":
                raise ValueError("synthetic parse error")
            return real_instant(value)

        def confirmation(source, row_id, png_sha, queued, now):
            if source is None:
                raise RuntimeError("synthetic record error")
            return real_confirmation(source, row_id, png_sha, queued, now)

        with self.subTest(check="instant"):
            lines = self.run_checker(1, FAIL, instant=instant, confirmation=real_confirmation)
            self.assert_findings(lines, "check-error", "check-error")
            self.assertEqual([line for line in lines if line.startswith("queued-bad")],
                             ["queued-bad 0 result=none", "queued-bad 1 result=none"])
        with self.subTest(check="record"):
            lines = self.run_checker(1, FAIL, confirmation=confirmation)
            self.assert_findings(lines, "check-error")
            self.assert_queue_results(lines, "none")

    def test_c3_usage_exit_2(self):
        # No argument (including a would-be help flag) may run or print the checker.
        for arg in ("unexpected", "--unexpected", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.splitlines()[-1].startswith(
                    f"{SCRIPT.name}: error:"))

    def test_c4_read_only(self):
        # Catch new files or rewrites in either checkout tree, including pyc files.
        before = snapshot()
        result = self.cli()
        self.assertEqual(snapshot(), before)
        self.assert_run(result.returncode, result.stdout, result.stderr, 1, FAIL)

    def test_c5_output_shape(self):
        # Forbid extra output such as record dumps, warnings or progress chatter.
        result = self.cli()
        lines = self.assert_run(result.returncode, result.stdout, result.stderr, 1, FAIL)
        for line in lines:
            self.assertRegex(line, r"\A(?:record [0-9] ok=(?:yes|no)|"
                                   r"queued-bad [0-2] result=(?:none|non-none|raises)|"
                                   r"FAIL (?:record-rule (?:[0-9]|oserror|valueerror|no-source)|"
                                   r"instant-rule [0-5]|queued-unreadable-(?:raises|non-none) [0-2]|"
                                   r"check-error))\Z")

    def test_c6_fixture(self):
        # Both repository functions must influence the verdict, not a pinned transcript.
        lines = self.run_checker(0, PASS, confirmation=self.for_unreadable_queue(None))
        self.assert_findings(lines)
        self.assert_queue_results(lines, "none")
        lines = self.run_checker(1, FAIL, instant=lambda _value: None)
        self.assert_findings(lines, "record-rule 0", "record-rule 6", "record-rule 7",
                             "instant-rule 0", "instant-rule 3")
        self.assert_queue_results(lines, "none")

    def test_c7_live_pins(self):
        # The unchanged product must surface only the three unreadable-queue findings.
        result = self.cli()
        lines = self.assert_run(result.returncode, result.stdout, result.stderr, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("record ")],
                         [f"record {i} ok=yes" for i in range(10)])
        self.assert_queue_results(lines, "raises")
        self.assert_findings(lines, *(f"queued-unreadable-raises {i}" for i in range(3)))
