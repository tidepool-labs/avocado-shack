"""Contract tests for the offline NPP listing lookup checker."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_active_job_lookup.py"
SPEC = importlib.util.spec_from_file_location("npp_active_job_lookup", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
PASS = "PASS npp_active_job_lookup"
FAIL = "FAIL npp_active_job_lookup"
WITHOUT_RETAKE = "'working','asking','card_out','editing'"


def snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class NppActiveJobLookupTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.scratch = temp.name

    def invoke_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.scratch,
            env={**os.environ, "TMPDIR": self.scratch}, capture_output=True, text=True,
            timeout=10, check=False,
        )

    def invoke_main(self):
        out, err = io.StringIO(), io.StringIO()
        with patch("tempfile.tempdir", self.scratch), redirect_stdout(out), redirect_stderr(err):
            code = CHECK.main([])
        self.assertEqual(err.getvalue(), "")
        return code, out.getvalue().splitlines()

    def assert_findings(self, result, *expected):
        code, lines = result
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(expected))
        return lines

    def test_c1_full_pass(self):
        # The standalone CLI must resolve its package even from a different cwd.
        result = self.invoke_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # Filtering taken codes to open rows would let a cancelled code be reused.
        def only_open(jobs, code):
            return jobs.one("SELECT 1 FROM npp_jobs WHERE job_id=? AND closed_at IS NULL", code) is not None

        with patch.object(CHECK.job.Jobs, "taken", only_open):
            lines = self.assert_findings(self.invoke_main(), "FAIL taken-changed a1b2")
        self.assertIn("taken a1b2 no", lines)

    def test_c2_1_other_sender(self):
        # Dropping either identity predicate can pick the wrong person's or chat's row.
        for field in ("chat", "sender"):
            def newest(jobs, chat, sender):
                return jobs.one(
                    f"SELECT * FROM npp_jobs WHERE {field}=? ORDER BY created_at DESC, rowid DESC",
                    {"chat": chat, "sender": sender}[field],
                )

            with self.subTest(field=field), patch.object(CHECK.job.Jobs, "active", newest):
                self.assert_findings(self.invoke_main(), *(
                    f"FAIL {reason} {i}" for i in range(10) for reason in ("other-sender", "active-changed")
                ))

    def test_c2_2_closed_job_active(self):
        # If the live allowlist grows, it must not also redefine the check's oracle.
        with patch.object(CHECK.job, "ACTIVE", CHECK.job.ACTIVE + ",'approved','cancelled'"):
            self.assert_findings(
                self.invoke_main(), "FAIL closed-job-active 5", "FAIL active-changed 5",
                "FAIL closed-job-active 8", "FAIL active-changed 8",
            )

    def test_c2_3_active_changed(self):
        # A pin mismatch must be reported even without returning an unsafe row.
        with patch.object(CHECK.job, "ACTIVE", WITHOUT_RETAKE):
            self.assert_findings(self.invoke_main(), "FAIL active-changed 4")

    def test_c2_4_check_error(self):
        # A broken repo call fails closed without exposing the exception text.
        with patch.object(CHECK.job.Jobs, "active", side_effect=RuntimeError("fixture detail")) as active:
            lines = self.assert_findings(self.invoke_main(), "FAIL check-error")
            active.assert_called_once_with("chat-owner", "sender-1")
        self.assertEqual(lines, ["FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # Reject even argparse's ordinary help option: this CLI takes no arguments.
        for arg in ("a1b2", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.invoke_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No stdout trailer on usage errors.
                self.assertTrue(result.stderr.splitlines()[-1].startswith("npp_active_job_lookup.py: error:"))

    def test_c4_read_only(self):
        # Writing a fixture or bytecode to the checkout must not look like success.
        before = snapshot()
        result = self.invoke_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(Path(self.scratch).iterdir()), [])

    def test_c5_output_shape(self):
        # Debug chatter would break consumers of the check's line protocol.
        code, lines = self.invoke_main()
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)
        for line in lines[:-1]:
            self.assertRegex(line, r"^(?:case [0-9] [a-z_]+ active=(?:[0-9a-f]+|none)|taken [0-9a-fA-F]+ (?:yes|no))$")

    def test_c6_fixture(self):
        # Retake must reach the repo call rather than being inferred by the checker.
        with patch.object(CHECK.job, "ACTIVE", WITHOUT_RETAKE):
            lines = self.assert_findings(self.invoke_main(), "FAIL active-changed 4")
        self.assertEqual(lines[4:6], ["case 4 retake active=none", "FAIL active-changed 4"])

    def test_c7_live_pins(self):
        # Independently pin the full transcript, including the exact-match code negatives.
        expected = (
            "case 0 working active=a1b2",
            "case 1 asking active=a1b2",
            "case 2 card_out active=a1b2",
            "case 3 editing active=a1b2",
            "case 4 retake active=a1b2",
            "case 5 approved active=none",
            "case 6 published active=none",
            "case 7 publish_failed active=none",
            "case 8 cancelled active=none",
            "case 9 expired active=none",
            "taken a1b2 yes",
            "taken A1B2 no",
            "taken a1b2c3 no",
            "taken ffff no",
        )
        result = self.invoke_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(tuple(result.stdout.splitlines()), (*expected, PASS))
        self.assertEqual(CHECK.EXPECTED, expected)
