"""Offline contract fixtures for the private Clover journal report."""

from contextlib import closing, redirect_stderr, redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/clover_journal_report.py"
NOW = "2030-01-07T23:30:00-02:00"  # January 8 UTC, not January 7.
TODAY = "2030-01-08"
PASS = "PASS clover_journal_report"
FAIL = "FAIL clover_journal_report"
NOT_SQLITE = "FAIL not-sqlite journal.sqlite3"
SCHEMA = (
    "CREATE TABLE changes(code TEXT PRIMARY KEY, draft TEXT, sender TEXT, chat TEXT, "
    "expires REAL, status TEXT, day TEXT, result TEXT)"
)


class CloverJournalReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / "fixture-private-state"
        self.clover = self.state / "clover"
        self.clover.mkdir(parents=True)
        self.store = self.clover / "journal.sqlite3"
        self.scratch = self.root / "scratch"
        self.scratch.mkdir()

    def write_rows(self, *rows):
        with closing(sqlite3.connect(self.store)) as db, db:
            db.execute(SCHEMA)
            db.executemany("INSERT INTO changes(status, day) VALUES(?, ?)", rows)

    def cli(self, *args, tmpdir=None):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            env={**os.environ, "TMPDIR": str(tmpdir or self.scratch), "TEMP": str(self.scratch)},
            capture_output=True, text=True, timeout=10,
        )

    def report(self, state=None, **kwargs):
        return self.cli("--state", str(state or self.state), "--now", NOW, **kwargs)

    def assert_report(self, result, *findings):
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.returncode, int(bool(findings)))
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [FAIL if findings else PASS])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(findings))
        return lines[:-1]

    def input_snapshot(self):
        return {
            path.relative_to(self.state): (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
            for path in (self.state, *self.state.rglob("*"))
        }

    def copy_uncheckpointed_wal(self):
        writer_store = self.root / self.store.name
        with closing(sqlite3.connect(writer_store)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA wal_autocheckpoint=0")
            db.execute(SCHEMA)
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.execute("INSERT INTO changes(status, day) VALUES('applied', ?)", (TODAY,))
            db.commit()
            shutil.copyfile(writer_store, self.store)
            shutil.copyfile(str(writer_store) + "-wal", str(self.store) + "-wal")
        return writer_store

    def test_c1_full_pass(self):
        # Local dates, off-by-one windows and counting drafts as writes give different totals.
        self.write_rows(
            ("applied", "2030-01-01"), ("applied", "2030-01-02"), ("applied", TODAY),
            ("applied", TODAY), ("applied", "2030-01-09"), ("draft", TODAY), ("held", None),
        )
        self.assertEqual(self.assert_report(self.report()), [
            "changes 7", "status applied 5", "status draft 1", "status held 1",
            "applied-day 2030-01-02 1", "applied-day 2030-01-03 0", "applied-day 2030-01-04 0",
            "applied-day 2030-01-05 0", "applied-day 2030-01-06 0", "applied-day 2030-01-07 0",
            "applied-day 2030-01-08 2",
        ])
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_c2_1_unsafe_state(self):
        # Following a directory symlink or treating a file as missing would incorrectly pass.
        state_alias = self.root / "state-alias"
        state_alias.symlink_to(self.state, target_is_directory=True)
        state_file = self.root / "state-file"
        state_file.touch()
        for state in (state_alias, state_file, self.root / "missing-state"):
            with self.subTest(state=state.name):
                self.assertEqual(self.assert_report(self.report(state), "FAIL unsafe-state"), ["FAIL unsafe-state"])
        for kind in ("symlink", "file"):
            with self.subTest(clover=kind):
                state = self.root / kind
                state.mkdir()
                clover = state / "clover"
                if kind == "symlink":
                    clover.symlink_to(self.clover, target_is_directory=True)
                else:
                    clover.touch()
                self.assertEqual(self.assert_report(self.report(state), "FAIL unsafe-state"), ["FAIL unsafe-state"])

    def test_c2_2_intent_pending(self):
        # Interrupted writes must not pass or collapse multiple rows into a boolean count.
        self.write_rows(("intent", TODAY), ("intent", None), ("draft", TODAY))
        lines = self.assert_report(self.report(), "FAIL intent-pending 2")
        self.assertIn("status intent 2", lines)
        self.assertIn(f"applied-day {TODAY} 0", lines)

    def test_c2_3_uncertain(self):
        # An uncertain outcome requires an operator check even without a pending intent.
        self.write_rows(("uncertain", TODAY))
        self.assertIn("status uncertain 1", self.assert_report(self.report(), "FAIL uncertain 1"))

    def test_c2_4_failed(self):
        # A settled failure is not a full pass, even when the row is outside the day window.
        self.write_rows(("failed", "2030-01-01"))
        self.assertIn("status failed 1", self.assert_report(self.report(), "FAIL failed 1"))

    def test_c2_5_not_sqlite(self):
        # Don't follow a store/sidecar link or mistake unreadable contents/schema for an empty journal.
        good_target = self.root / "target.sqlite3"
        self.write_rows(("draft", None))
        shutil.copyfile(self.store, good_target)
        for case in ("bytes", "table", "status", "day", "directory", "link", "dangling-link",
                     "wal-link", "wal-directory", "journal-link", "journal-directory"):
            with self.subTest(case=case), tempfile.TemporaryDirectory(dir=self.root) as tmp:
                clover = Path(tmp) / "clover"
                clover.mkdir()
                store = clover / self.store.name
                if case == "bytes":
                    store.write_bytes(b"synthetic invalid database")
                elif case in ("table", "status", "day"):
                    sql = {"table": "CREATE TABLE placeholder(n)",
                           "status": "CREATE TABLE changes(day)", "day": "CREATE TABLE changes(status)"}
                    with closing(sqlite3.connect(store)) as db:
                        db.execute(sql[case])
                elif case == "directory":
                    store.mkdir()
                elif case in ("link", "dangling-link"):
                    store.symlink_to(good_target if case == "link" else self.root / "missing-target")
                else:
                    suffix, kind = case.split("-")
                    shutil.copyfile(good_target, store)
                    sidecar = clover / f"{store.name}-{suffix}"
                    if kind == "link":
                        sidecar.symlink_to(good_target)
                    else:
                        sidecar.mkdir()
                self.assertEqual(self.assert_report(self.report(Path(tmp)), NOT_SQLITE), [NOT_SQLITE])
                self.assertEqual(list(self.scratch.iterdir()), [])

    def test_c2_6_temp_unavailable(self):
        # Only an unsafe or missing location is offered; a fallback must not write into state.
        self.write_rows(("draft", None))
        alias = self.root / "temp-alias"
        alias.symlink_to(self.clover, target_is_directory=True)
        spec = importlib.util.spec_from_file_location("clover_journal_report", SCRIPT)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stdout, stderr = io.StringIO(), io.StringIO()
        before = self.input_snapshot()
        with (patch.object(module, "_temp_candidates", return_value=[self.state, alias, self.root / "missing"]),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            code = module.main(["--state", str(self.state), "--now", NOW])
        result = subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())
        self.assertEqual(self.assert_report(result, "FAIL temp-unavailable"), ["FAIL temp-unavailable"])
        self.assertEqual(self.input_snapshot(), before)

    def test_c2_reports_multiple_findings(self):
        # Returning on the first finding would hide other unsettled rows from the operator.
        self.write_rows(("failed", TODAY), ("uncertain", TODAY), ("intent", TODAY))
        self.assert_report(self.report(), "FAIL intent-pending 1", "FAIL uncertain 1", "FAIL failed 1")

    def test_c3_usage_exit_2(self):
        # Missing/unknown/invalid options must not masquerade as report findings.
        for args in ((), ("--state", str(self.state), "--unknown"),
                     ("--state", str(self.state), "--now", "not-an-iso-time"),
                     ("--state", str(self.state), "--now", "2030-01-08T00:00:00")):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # There is no last line for usage errors.
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # Even SQLite's read-only open on a WAL DB can create SHM in the input directory.
        self.copy_uncheckpointed_wal()
        self.assertFalse(Path(str(self.store) + "-shm").exists())
        before = self.input_snapshot()
        self.assert_report(self.report())
        self.assertEqual(self.input_snapshot(), before)

    def test_c5_no_private_values(self):
        # Invalid status/day text and raw argument diagnostics can leak private data.
        message = "synthetic message text"
        full_id = "synthetic-id-01e4c613"
        digest = "f17e" * 16
        self.write_rows((message, TODAY), (full_id, TODAY), (digest, TODAY),
                        ("applied", str(self.store)), (None, None), ("intent\n", TODAY),
                        ("draft", TODAY), ("other", TODAY))
        result = self.report()
        lines = self.assert_report(result)
        self.assertEqual(lines[:4], ["changes 8", "status applied 1", "status draft 1", "status other 6"])
        self.assertIn(f"applied-day {TODAY} 0", lines)
        for arguments in (("--now", str(self.store)), ("--unknown", str(self.clover))):
            usage = self.cli("--state", str(self.state), *arguments)
            self.assertEqual((usage.returncode, usage.stdout), (2, ""))
            self.assertNotIn(str(self.state), usage.stderr)
        for canary in (message, full_id, digest, str(self.state), str(self.clover), str(self.store)):
            self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_absent_journal_pass(self):
        # SQLite would create the journal if a missing path were opened directly.
        for state in (self.state, self.root / "without-clover"):
            with self.subTest(state=state.name):
                state.mkdir(exist_ok=True)
                before = list(state.rglob("*"))
                self.assertEqual(self.assert_report(self.report(state)), ["journal absent"])
                self.assertEqual(list(state.rglob("*")), before)
                self.assertEqual(list(self.scratch.iterdir()), [])

    def test_c7_no_journal_values(self):
        # Outputting complete rows, even for an unsettled finding, would reveal approval details.
        canaries = ("synthetic-approval-code", "synthetic-draft-json", "synthetic-sender",
                    "synthetic-chat", "synthetic-result-json")
        self.write_rows()
        with closing(sqlite3.connect(self.store)) as db, db:
            db.execute("INSERT INTO changes(code, draft, sender, chat, result, status) "
                       "VALUES(?, ?, ?, ?, ?, 'intent')", canaries)
        result = self.report()
        self.assertIn("status intent 1", self.assert_report(result, "FAIL intent-pending 1"))
        for canary in canaries:
            self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c8_wal_rows_counted(self):
        # A main-file-only snapshot misses a committed WAL row; SHM must not be needed or copied.
        decoy = self.copy_uncheckpointed_wal()
        shutil.copyfile(self.store, decoy)
        with closing(sqlite3.connect(decoy)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM changes").fetchone(), (0,))
        Path(str(self.store) + "-shm").symlink_to(self.root / "missing-shm-target")
        lines = self.assert_report(self.report())
        self.assertEqual(lines[:2], ["changes 1", "status applied 1"])
        self.assertIn(f"applied-day {TODAY} 1", lines)

    def test_c9_tmpdir_inside_input(self):
        # A temp-root write probe or transient snapshot is visible in directory mtimes.
        self.write_rows(("applied", TODAY))
        nested = self.clover / "nested"
        nested.mkdir()
        alias = self.root / "tmp-alias"
        alias.symlink_to(nested, target_is_directory=True)
        for temp in (self.state, self.clover, nested, alias):
            with self.subTest(temp=temp.name):
                before = self.input_snapshot()
                lines = self.assert_report(self.report(tmpdir=temp))
                self.assertIn(f"applied-day {TODAY} 1", lines)
                self.assertEqual(self.input_snapshot(), before)
                self.assertEqual(list(self.scratch.iterdir()), [])
