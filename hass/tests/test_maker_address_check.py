"""Fixture-only CLI contract tests for the offline maker-address report."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/maker_address_check.py"
PASS = "PASS maker_address_check"
FAIL = "FAIL maker_address_check"


class MakerAddressCheckTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory(dir=ROOT))).resolve()
        self.source = self.root / "owner-lines.txt"

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *map(str, args)],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )

    def run_text(self, text):
        self.source.write_bytes(text.encode("utf-8"))
        return self.cli("--lines", self.source)

    def assert_report(self, result, code, trailer):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines

    def assert_input_failure(self, result, reason):
        self.assertEqual(self.assert_report(result, 1, FAIL), [f"FAIL {reason}", FAIL])

    def test_c1_full_pass(self):
        # Skipping blanks must not renumber later rows or spoil a clean pass.
        result = self.run_text("\r\n  example.com  \r\n \t\nhttps://example.org/about\r")
        self.assertEqual(self.assert_report(result, 0, PASS), [
            "line 2 address ok found 0", "line 4 address ok found 1",
            "lines 2", "accepted 2", "refused 0", PASS,
        ])

    def test_c2_findings_trailer(self):
        # An invalid suffix beyond the byte limit must not yield two findings or a partial pass.
        self.source.write_bytes(b" " * 200_000 + b"\xff")
        self.assert_input_failure(self.cli("--lines", self.source), "too-large")

    def test_c2_1_unsafe_input(self):
        # A symlink to valid data is still unsafe; neither a directory nor a FIFO is a file.
        self.source.write_bytes(b"example.com\n")
        alias = self.root / "alias"
        alias.symlink_to(self.source)
        fifo = self.root / "pipe"
        os.mkfifo(fifo)
        for path in (alias, self.root, fifo):
            with self.subTest(kind=path.name if path != self.root else "directory"):
                self.assert_input_failure(self.cli("--lines", path), "unsafe-input")

    def test_c2_2_too_large(self):
        # An inclusive byte cap must count UTF-8 bytes, not characters, and never truncate.
        exact_limit = b"example.com\n" + "\u2002".encode() * 66_662 + b"  "
        self.assertEqual(len(exact_limit), 200_000)
        self.source.write_bytes(exact_limit)
        self.assert_report(self.cli("--lines", self.source), 0, PASS)
        self.source.write_bytes(exact_limit + b" ")
        self.assert_input_failure(self.cli("--lines", self.source), "too-large")

    def test_c2_3_not_utf8(self):
        # Replacement decoding or streaming output would expose a partial report.
        self.source.write_bytes(b"example.com\n\xff\n")
        self.assert_input_failure(self.cli("--lines", self.source), "not-utf8")

    def test_c2_4_too_many_lines(self):
        # The cap is inclusive and counts non-blank lines only.
        exact_limit = "example.com\n\n" * 500
        lines = self.assert_report(self.run_text(exact_limit), 0, PASS)
        self.assertEqual(lines[-5:], ["line 999 address ok found 0", "lines 500", "accepted 500", "refused 0", PASS])
        self.assert_input_failure(self.run_text(exact_limit + "example.com"), "too-many-lines")

    def test_c2_5_refused(self):
        # Every pinned refusal contributes one to the aggregate finding; a good row does not.
        refused = ["http://x.com", "https://user@x.com", "https://x.com:8080/", "https://localhost/",
                   "https://x.local/", "https://10.0.0.1/", "https://harbor lane.com"]
        lines = self.assert_report(self.run_text("\n".join([*refused, "example.org"])), 1, FAIL)
        for k, line in enumerate(lines[:7], 1):
            self.assertRegex(line, rf"^line {k} address refused found [0-2]$")
        self.assertEqual(lines[7:], ["line 8 address ok found 0", "lines 8", "accepted 1", "refused 7",
                                     "FAIL refused 7", FAIL])

    def test_c3_usage_exit_2(self):
        # Missing, unknown, and valueless flags must remain argparse errors, not findings.
        self.source.write_bytes(b"example.com\n")
        for args in ([], ["--lines", self.source, "--unknown"], ["--lines"]):
            with self.subTest(argc=len(args)):
                result = self.cli(*args)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # Rewriting the same bytes or briefly creating a sidecar is not read-only.
        self.source.write_bytes(b"example.com\r\n")
        before = (self.source.read_bytes(), self.source.stat().st_mtime_ns)
        entries, dir_mtime = set(self.root.iterdir()), self.root.stat().st_mtime_ns
        self.assert_report(self.cli("--lines", self.source), 0, PASS)
        self.assertEqual((self.source.read_bytes(), self.source.stat().st_mtime_ns), before)
        self.assertEqual((set(self.root.iterdir()), self.root.stat().st_mtime_ns), (entries, dir_mtime))

    def test_c5_no_private_values(self):
        # Refusal paths and argparse diagnostics must not echo private inputs.
        address = "https://example.org/synthetic-address-marker"
        owner_line = "site https://example.net/synthetic-owner-line-marker"
        missing = self.root / "not-present.txt"
        result = self.run_text(f"{address}\n{owner_line}\n")
        self.assert_report(result, 1, FAIL)
        unavailable = self.cli("--lines", missing)
        self.assert_input_failure(unavailable, "unsafe-input")
        usage = self.cli("--lines", self.source, missing, address, owner_line)
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for output in (result, unavailable, usage):
            for canary in (address, owner_line, str(self.source), str(missing)):
                self.assertNotIn(canary, output.stdout + output.stderr)

    def test_c6_accepted(self):
        # Whole-line acceptance does not depend on extraction or fragment normalization.
        result = self.run_text("harborlane.com\nhttps://harborlane.com/about\nwww.harborlane.farm\nhttps://x.com/#frag")
        self.assertEqual(self.assert_report(result, 0, PASS), [
            "line 1 address ok found 0", "line 2 address ok found 1",
            "line 3 address ok found 1", "line 4 address ok found 1",
            "lines 4", "accepted 4", "refused 0", PASS,
        ])

    def test_c7_found_counts(self):
        # Extraction must run even on refused rows and keep Hass's cue rule and cap.
        result = self.run_text("\n".join([
            "harborlane.com is great", "see their site harborlane.com", "harborlane.com/about",
            "www.a-farm.com and https://b.com/about and https://c.com",
            "https://user@bad.com", "call 805 555 0100",
        ]))
        self.assertEqual(self.assert_report(result, 1, FAIL), [
            "line 1 address refused found 0", "line 2 address refused found 1",
            "line 3 address ok found 1", "line 4 address refused found 2",
            "line 5 address refused found 0", "line 6 address refused found 0",
            "lines 6", "accepted 1", "refused 5", "FAIL refused 5", FAIL,
        ])
