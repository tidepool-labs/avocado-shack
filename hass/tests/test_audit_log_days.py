"""Fixture-only tests for the audit day count and its CLI contract."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/audit_log_days.py"
NOW = "2024-03-02T00:00:00Z"


class AuditLogDaysTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / "synthetic-state"
        self.state.mkdir()
        self.audit = self.state / "audit"
        self.argv = ("--state", str(self.state), "--days", "1", "--now", NOW)

    def cli(self, *argv):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *argv], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def assert_status(self, result, code, last):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stdout.splitlines()[-1:], [] if last is None else [last])

    def test_c1_full_pass(self):
        # Counting malformed dates or treating notes as findings changes this report.
        self.audit.mkdir()
        for name in ("2024-03-01.jsonl", "2024-02-29.jsonl", "2023-02-29.jsonl",
                     "2024-13-01.jsonl", "2024-01-01.jsonl.bak", "2024-02-28.jsonl\n"):
            (self.audit / name).touch()
        result = self.cli(*self.argv)
        self.assert_status(result, 0, "PASS audit_log_days")
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), [
            "days 1", "files 2", "older 1", "oldest 2024-02-29",
            "note invalid-dates 2", "note other-names 2", "deletes 0", "PASS audit_log_days",
        ])

    def test_directory_named_like_a_log_is_not_counted(self):
        # Protects the "retained logs / oldest log" report: a name-only listing counts a
        # directory, symlink or FIFO named like a day log as a file and as the oldest one.
        self.audit.mkdir()
        (self.audit / "2024-03-01.jsonl").touch()
        (self.audit / "2024-02-29.jsonl").mkdir()
        (self.audit / "2024-02-28.jsonl").symlink_to(self.audit / "2024-03-01.jsonl")
        os.mkfifo(self.audit / "2024-02-27.jsonl")
        result = self.cli(*self.argv)
        self.assert_status(result, 0, "PASS audit_log_days")
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), [
            "days 1", "files 1", "older 0", "oldest 2024-03-01",
            "note invalid-dates 0", "note other-names 3", "deletes 0", "PASS audit_log_days",
        ])

    def test_c2_1_no_audit_dir(self):
        # Missing input must not look like a successful empty report.
        for state in (self.state, self.root / "absent"):
            with self.subTest(state=state.name):
                result = self.cli("--state", str(state), *self.argv[2:])
                self.assert_status(result, 1, "FAIL audit_log_days")
                self.assertEqual(result.stdout.splitlines(), ["FAIL no-audit-dir", "FAIL audit_log_days"])
                self.assertEqual(result.stderr, "")

    def test_c2_2_unsafe_audit_dir(self):
        # Directory APIs that follow symlinks or collapse wrong types into missing fail here.
        for leaf in ("state", "audit"):
            for kind in ("file", "symlink", "dangling-symlink"):
                with self.subTest(leaf=leaf, kind=kind):
                    case = self.root / f"{leaf}-{kind}"
                    case.mkdir()
                    state = case / "state"
                    bad = state
                    if leaf == "audit":
                        state.mkdir()
                        bad = state / "audit"
                    if kind == "file":
                        bad.touch()
                    else:
                        target = case / "target"
                        if kind == "symlink":
                            (target / "audit").mkdir(parents=True)
                        bad.symlink_to(target, target_is_directory=True)
                    result = self.cli("--state", str(state), *self.argv[2:])
                    self.assert_status(result, 1, "FAIL audit_log_days")
                    self.assertEqual(result.stdout.splitlines(), ["FAIL unsafe-audit-dir", "FAIL audit_log_days"])
                    self.assertEqual(result.stderr, "")

    def test_c3_usage_exit_2(self):
        # A permissive conversion or a tool-level failure would hide CLI misuse.
        self.audit.mkdir()
        cases = [self.argv[2:], self.argv[:2], (*self.argv, "--unknown"),
                 (*self.argv, "--day", "1")]
        cases.extend((*self.argv[:2], "--days", value) for value in ("0", "-1", "36501", "1.0", "1_0", "abc"))
        cases.extend((*self.argv[:4], "--now", value) for value in (
            "2024-03-02", "2024-03-02T00:00:00", "not-an-iso-time", "2024-03-02x00:00:00Z",
        ))
        for index, argv in enumerate(cases):
            with self.subTest(case=index):
                result = self.cli(*argv)
                self.assert_status(result, 2, None)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "))

    def test_c4_read_only(self):
        # Catch opening audit data as well as deleting, rewriting or creating files.
        self.audit.mkdir()
        (self.state / "outside-audit.txt").write_bytes(b"synthetic state\n")
        (self.audit / "2024-02-27.jsonl").write_bytes(b"\xff synthetic non-JSON\n")
        (self.audit / "other.txt").write_bytes(b"synthetic extra\n")

        def snapshot():
            return {p.relative_to(self.root): None if p.is_dir() else (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in self.root.rglob("*")}

        spec = importlib.util.spec_from_file_location("audit_log_days", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        before = snapshot()
        stdout, stderr = io.StringIO(), io.StringIO()
        real_open = os.open

        def directory_open(path, flags, *args, **kwargs):
            self.assertEqual(flags & os.O_ACCMODE, os.O_RDONLY)
            self.assertTrue(flags & os.O_DIRECTORY)
            return real_open(path, flags, *args, **kwargs)

        denied = AssertionError("the report must not open input files")
        with (patch("builtins.open", side_effect=denied), patch("io.open", side_effect=denied),
              patch("os.open", side_effect=directory_open), redirect_stdout(stdout), redirect_stderr(stderr)):
            code = module.main(self.argv)
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue().splitlines()[-1], "PASS audit_log_days")
        self.assertIn("files 1\nolder 1\n", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Debug output, filename warnings and argparse echoes must not expose inputs.
        self.audit.mkdir()
        canaries = {"message": "synthetic-message-canary", "chat": "synthetic-chat-canary",
                    "sender": "synthetic-sender-canary", "id": "synthetic-full-id-canary",
                    "digest": "ab" * 32}
        extra = "synthetic-private-basename"
        (self.audit / "2024-02-20.jsonl").write_text(json.dumps(canaries) + "\n", encoding="utf-8")
        (self.audit / extra).touch()
        for argv, code, last in (
            (self.argv, 0, "PASS audit_log_days"),
            (("--state", str(self.audit), *self.argv[2:]), 1, "FAIL audit_log_days"),
            ((*self.argv, str(self.audit / extra)), 2, None),
        ):
            with self.subTest(code=code):
                result = self.cli(*argv)
                self.assert_status(result, code, last)
                for value in (*canaries.values(), extra, str(self.root)):
                    self.assertNotIn(value, result.stdout)
                    self.assertNotIn(value, result.stderr)

    def test_c6_cutoff_edge(self):
        # Comparing date labels alone can count a day before its UTC end.
        self.audit.mkdir()
        (self.audit / "2024-03-01.jsonl").touch()
        for now, expected in (("2024-03-02T15:00:00Z", 0),
                              ("2024-03-03T00:59:59.999999+01:00", 0),
                              ("2024-03-02T19:00:00-05:00", 1)):
            with self.subTest(now=now):
                result = self.cli(*self.argv[:-1], now)
                self.assert_status(result, 0, "PASS audit_log_days")
                self.assertIn(f"older {expected}", result.stdout.splitlines())
                self.assertIn("oldest 2024-03-01", result.stdout.splitlines())

    def test_c6_empty_and_upper_days_bound(self):
        # Maximum --days still parses; no valid day must not invent an oldest date.
        self.audit.mkdir()
        result = self.cli(*self.argv[:2], "--days", "36500")
        self.assert_status(result, 0, "PASS audit_log_days")
        self.assertEqual(result.stdout.splitlines(), [
            "days 36500", "files 0", "older 0", "oldest null",
            "note invalid-dates 0", "note other-names 0", "deletes 0", "PASS audit_log_days",
        ])
