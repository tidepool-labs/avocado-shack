"""Fixture-only tests at the saved self-test stdout CLI boundary."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/selftest_summary_check.py"
PASS = "PASS selftest_summary_check"
FAIL = "FAIL selftest_summary_check"
CLEAN = "PASS alpha detail\nHASS-SELFTEST fixture-stamp pass=1 warn=0 fail=0 skip=0\n"


class SelftestSummaryCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.capture = self.root / "capture.txt"

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )

    def run_capture(self, text):
        self.capture.write_text(text, encoding="utf-8")
        return self.run_cli("--stdout", str(self.capture))

    def assert_output(self, result, code, *lines):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), list(lines))

    def test_c1_full_pass(self):
        # WARN/SKIP and unrelated lines must not make an otherwise clean capture fail.
        result = self.run_capture(
            "PASS alpha detail\nWARN beta detail\nSKIP gamma detail\nWARN delta detail\n"
            " PASS not-a-check detail\nPASS\tnot-a-check detail\n"
            "HASS-SELFTEST fixture-stamp pass=1 warn=2 fail=0 skip=1\n\n"
        )
        self.assert_output(result, 0, "checks 4", "warn beta", "warn delta", "note other-lines 3", PASS)

    def test_zero_positive_checks_is_not_health_proof(self):
        # Count agreement and zero failures can hide an empty or entirely skipped run.
        for skipped in (0, 1):
            with self.subTest(skipped=skipped):
                rows = "SKIP alpha detail\n" if skipped else ""
                result = self.run_capture(
                    rows + f"HASS-SELFTEST fixture-stamp pass=0 warn=0 fail=0 skip={skipped}\n"
                )
                self.assert_output(result, 1, f"checks {skipped}", "note other-lines 0",
                                   "FAIL no-passing-check", FAIL)

    def test_c2_1_no_file(self):
        # Absent and non-regular paths must produce a named verdict, not a traceback.
        for path in (self.capture, self.root):
            with self.subTest(name=path.name):
                self.assert_output(self.run_cli("--stdout", str(path)), 1, "FAIL no-file", FAIL)

    def test_c2_2_no_summary(self):
        # Neither an earlier valid summary nor a final near match satisfies the format.
        cases = (
            ("PASS alpha detail\n", 0),
            (CLEAN + "extra line\n", 2),
            (CLEAN.rstrip("\n") + " \n", 1),
            (CLEAN.replace("skip=0", "skip=+0"), 1),
        )
        for text, other in cases:
            with self.subTest(capture=text):
                self.assert_output(self.run_capture(text), 1, "checks 1", f"note other-lines {other}",
                                   "FAIL no-summary", FAIL)

    def test_c2_3_count_mismatch(self):
        # Each status must be compared independently, including a missing summary FAIL count.
        for status, counts in (
            ("pass", "pass=2 warn=0 fail=0 skip=0"),
            ("warn", "pass=1 warn=1 fail=0 skip=0"),
            ("fail", "pass=1 warn=0 fail=0 skip=0"),
            ("skip", "pass=1 warn=0 fail=0 skip=1"),
        ):
            with self.subTest(status=status):
                text = "PASS alpha detail\n"
                extra = []
                if status == "fail":
                    text += "FAIL beta detail\n"
                    extra = ["FAIL failed-check beta"]
                result = self.run_capture(text + f"HASS-SELFTEST fixture-stamp {counts}\n")
                self.assert_output(result, 1, f"checks {1 + len(extra)}", "note other-lines 0",
                                   f"FAIL count-mismatch {status}", *extra, FAIL)

    def test_c2_4_failed_check(self):
        # A producer-style failed: suffix is not a valid summary, but never hides FAIL rows.
        result = self.run_capture(
            "FAIL alpha detail\nFAIL beta detail\nFAIL alpha repeated detail\n"
            "HASS-SELFTEST fixture-stamp pass=0 warn=0 fail=3 skip=0 failed:alpha,beta,alpha\n"
        )
        self.assert_output(result, 1, "checks 3", "note other-lines 1", "FAIL no-summary",
                           "FAIL failed-check alpha", "FAIL failed-check beta", "FAIL failed-check alpha", FAIL)

    def test_c2_5_summary_fail(self):
        # Count agreement cannot make a nonzero summary FAIL count pass.
        result = self.run_capture(
            "FAIL alpha detail\nHASS-SELFTEST fixture-stamp pass=0 warn=0 fail=1 skip=0\n"
        )
        self.assert_output(result, 1, "checks 1", "note other-lines 0", "FAIL no-passing-check",
                           "FAIL failed-check alpha", "FAIL summary-fail 1", FAIL)

    def test_c3_usage_exit_2(self):
        # Missing flag/value and unknown flags retain argparse's exit, not a finding verdict.
        for args in ((), ("--stdout",), ("--stdout", str(self.capture), "--unknown")):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # Even an in-place rewrite of identical bytes or a sidecar would break this receipt.
        self.capture.write_bytes(CLEAN.replace("\n", "\r\n").encode("utf-8"))
        neighbor = self.root / "neighbor.txt"
        neighbor.write_bytes(b"unrelated fixture\n")
        files = (self.capture, neighbor)
        before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in files]
        entries = set(self.root.rglob("*"))
        self.assert_output(self.run_cli("--stdout", str(self.capture)), 0, "checks 1", "note other-lines 0", PASS)
        self.assertEqual([(path.read_bytes(), path.stat().st_mtime_ns) for path in files], before)
        self.assertEqual(set(self.root.rglob("*")), entries)

    def test_c5_no_private_values(self):
        # Printing raw WARNING/FAIL/other/summary data or argv would disclose these markers.
        message = "fixture private message marker"
        chat = "fixture-chat-marker"
        sender = "fixture-sender-marker"
        full_id = "fixture-full-id-marker"
        digest = "a1b2" * 16
        stamp = "fixture-private-stamp"
        path = str(self.capture)
        self.capture.write_text(
            f"PASS alpha {message}\nWARN beta chat={chat} sender={sender}\n"
            f"FAIL gamma id={full_id} digest={digest}\nraw detail {path}\n"
            f"HASS-SELFTEST {stamp} pass=1 warn=1 fail=1 skip=0\n",
            encoding="utf-8",
        )
        result = self.run_cli("--stdout", path)
        usage = self.run_cli("--stdout", path, path)
        for invocation in (result, usage):
            for canary in (message, chat, sender, full_id, digest, stamp, path):
                self.assertNotIn(canary, invocation.stdout)
                self.assertNotIn(canary, invocation.stderr)
        self.assert_output(result, 1, "checks 3", "warn beta", "note other-lines 1",
                           "FAIL failed-check gamma", "FAIL summary-fail 1", FAIL)
        self.assertEqual(usage.returncode, 2)
        self.assertEqual(usage.stdout, "")


if __name__ == "__main__":
    unittest.main()
