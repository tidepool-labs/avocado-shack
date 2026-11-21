"""Offline CLI contracts for comparison against a saved IANA list."""

from collections.abc import Iterable
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from hass.tlds import TLDS


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/tlds_freshness_check.py"
PIN_VERSION = "2026111000"
PIN_SIZE = 1436


class TldsFreshnessCheckTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.source = self.root / "saved-tlds.txt"

    def save(self, payload):
        self.source.write_bytes(payload)
        return str(self.source)

    def snapshot(self, header="", endings: Iterable[str] = TLDS, newline="\n"):
        return (header + newline.join(name.upper() for name in sorted(endings))
                + newline).encode("utf-8")

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def check(self, result, code):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], f"{'PASS' if code == 0 else 'FAIL'} tlds_freshness_check")
        return lines[:-1]

    def check_refusal(self, path, reason):
        self.assertEqual(self.check(self.run_cli("--iana", str(path)), 1), [f"FAIL {reason}"])

    def test_c1_full_pass(self):
        # Ignoring CRLF, duplicates, IDNs, blank lines or the first-comment rule breaks parity.
        idn = next(name for name in sorted(TLDS) if name.startswith("xn--"))
        header = f"\r\n# snapshot\r\n \t\r\n# Version 123\r\n{idn.upper()}\r\n"
        path = self.save(self.snapshot(header, newline="\r\n"))
        lines = self.check(self.run_cli("--iana", path), 0)
        self.assertIn("iana-version none", lines)
        self.assertIn(f"iana {PIN_SIZE}", lines)

    def test_c2_findings_trailer(self):
        # A short circuit after malformed input hides independently actionable drift.
        path = self.save(b"AAA\nnot.an.ending\n")
        lines = self.check(self.run_cli("--iana", path), 1)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL iana-malformed 2", f"FAIL stale added 0 removed {PIN_SIZE - 1}",
        ])

    def test_c2_1_unsafe_input(self):
        # An ordinary open can follow a symlink or hang on a FIFO.
        self.save(self.snapshot())
        link = self.root / "link.txt"
        link.symlink_to(self.source)
        missing = self.root / "absent.txt"
        fifo = self.root / "input.fifo"
        os.mkfifo(fifo)
        for path in (link, self.root, fifo, missing):
            with self.subTest(kind=path.name):
                self.check_refusal(path, "unsafe-input")

    def test_c2_2_too_large(self):
        # An off-by-one cap or clipping an oversized comment can misclassify the file.
        body = self.snapshot()
        exact = body + b"#" * (1_000_000 - len(body))
        path = self.save(exact)
        self.check(self.run_cli("--iana", path), 0)
        self.save(exact + b"x")
        self.check_refusal(path, "too-large")

    def test_c2_3_not_utf8(self):
        # Replacement decoding or skipping raw comments can hide invalid UTF-8.
        path = self.save(self.snapshot() + b"#\xff\n")
        self.check_refusal(path, "not-utf8")

    def test_c2_4_malformed(self):
        # Partial matches, stripping invalid whitespace and uncapped dumps break the grammar.
        prefix = b"# Version 456\r\n\r\n"
        invalid = [b"a.b", b"a" * 64, b"xn--" + b"a" * 60, b"a_b", b" AAA",
                   b"AAA ", "é".encode("utf-8")]
        path = self.save(prefix + b"\r\n".join(invalid) + b"\r\n" + self.snapshot())
        lines = self.check(self.run_cli("--iana", path), 1)
        self.assertEqual(lines[:6], [f"FAIL iana-malformed {n}" for n in range(3, 8)]
                         + ["note more-malformed 2"])
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], lines[:5])
        self.assertIn("added 0", lines)
        self.assertIn("removed 0", lines)

    def test_c2_5_stale(self):
        # Matching version IDs cannot suppress a set difference or disable sorted note caps.
        added = {f"sample-ending-{i:02d}" for i in range(21)} | {"a" * 63, "xn--" + "b" * 59}
        self.assertTrue(added.isdisjoint(TLDS))
        path = self.save(self.snapshot(f"# Version {PIN_VERSION}\n", {"aaa"} | added))
        lines = self.check(self.run_cli("--iana", path), 1)
        self.assertEqual(lines[2:6], ["iana 24", f"pinned {PIN_SIZE}", "added 23",
                                      f"removed {PIN_SIZE - 1}"])
        self.assertEqual(lines[6:], [f"note added {name}" for name in sorted(added)[:20]]
                         + [f"note removed {name}" for name in sorted(TLDS - {"aaa"})[:20]]
                         + [f"FAIL stale added 23 removed {PIN_SIZE - 1}"])

    def test_c2_6_empty(self):
        # A comment-only snapshot is a finding, not just a zero count or a stale registry.
        path = self.save(b"\n# Version 456\n\t\r\n# comment\r\n")
        lines = self.check(self.run_cli("--iana", path), 1)
        self.assertIn("iana 0", lines)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL iana-empty", f"FAIL stale added 0 removed {PIN_SIZE}",
        ])

    def test_c3_usage_exit_2(self):
        # Missing option/value or an unknown flag must not become a comparison outcome.
        path = self.save(self.snapshot())
        for args in ((), ("--iana",), ("--iana", path, "--unknown")):
            with self.subTest(case=len(args)):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # In-place normalization or report/cache sidecars would change this snapshot.
        raw = self.snapshot("# fixture\r\n", newline="\r\n")
        path = self.save(raw)
        stamp = self.source.stat().st_mtime_ns
        directory_stamp = self.root.stat().st_mtime_ns
        self.check(self.run_cli("--iana", path), 0)
        self.assertEqual(self.source.read_bytes(), raw)
        self.assertEqual(self.source.stat().st_mtime_ns, stamp)
        self.assertEqual(set(self.root.iterdir()), {self.source})
        self.assertEqual(self.root.stat().st_mtime_ns, directory_stamp)

    def test_c5_no_private_values(self):
        # Raw header/line/exception text (including argparse's argv echo) leaks input.
        comment = "synthetic-header-canary"
        marker = "synthetic-invalid@marker"
        path = self.save(self.snapshot(f"# Version 456, {comment}\n") + marker.encode())
        result = self.run_cli("--iana", path)
        lines = self.check(result, 1)
        self.assertIn("iana-version 456", lines)
        self.assertIn(f"FAIL iana-malformed {PIN_SIZE + 2}", lines)
        missing = str(self.root / "unavailable.txt")
        failed_read = self.run_cli("--iana", missing)
        self.assertEqual(self.check(failed_read, 1), ["FAIL unsafe-input"])
        usage = self.run_cli("--iana", path, missing)
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for run in (result, failed_read, usage):
            for value in (comment, marker, path, missing):
                self.assertNotIn(value, run.stdout + run.stderr)

    def test_c6_same_as_pin(self):
        # Case normalization or report drift can make the canonical pinned snapshot unusable.
        path = self.save(self.snapshot(f"# Version {PIN_VERSION}, Last Updated fixture\n"))
        lines = self.check(self.run_cli("--iana", path), 0)
        self.assertEqual(lines, [f"iana-version {PIN_VERSION}", f"pinned-version {PIN_VERSION}",
                                 f"iana {PIN_SIZE}", f"pinned {PIN_SIZE}", "added 0", "removed 0"])

    def test_c7_one_each(self):
        # A count-only check misses replacements; reversed differences swap the notes.
        name = "sample-new-ending"
        self.assertIn("aaa", TLDS)
        self.assertNotIn(name, TLDS)
        path = self.save(self.snapshot(endings=(TLDS - {"aaa"}) | {name}))
        lines = self.check(self.run_cli("--iana", path), 1)
        self.assertEqual(lines[4:], ["added 1", "removed 1", f"note added {name}",
                                     "note removed aaa", "FAIL stale added 1 removed 1"])
