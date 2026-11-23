"""Fixture-only tests of the offline Clover bundle report's CLI contract."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/clover_bundle_report.py"
SPEC = importlib.util.spec_from_file_location("clover_bundle_report", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)
STORE = "bundles.sqlite3"
PASS = "PASS clover_bundle_report"
FAIL = "FAIL clover_bundle_report"
DONE = ["bundles 1", "state done 1", "proposed-expired 0", "undo-bundles 0", PASS]


class CloverBundleReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / "fixture-state"
        self.clover = self.state / "clover"
        self.clover.mkdir(parents=True)
        self.store = self.clover / STORE

    @staticmethod
    def seed(db, rows):
        db.execute("CREATE TABLE bundles(code TEXT PRIMARY KEY, row TEXT NOT NULL)")
        db.executemany("INSERT INTO bundles VALUES(?, ?)", (
            (f"fixture-key-{index}", json.dumps(row) if isinstance(row, (dict, list)) else row)
            for index, row in enumerate(rows)
        ))
        db.commit()

    def write_rows(self, *rows):
        with closing(sqlite3.connect(self.store)) as db:
            self.seed(db, rows)

    def cli(self, *args, env=None):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              env=env, capture_output=True, text=True, timeout=10)

    def run_report(self, *args, state=None, env=None):
        return self.cli("--state", str(self.state if state is None else state), *args, env=env)

    def call_main(self, state=None):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = REPORT.main(["--state", str(self.state if state is None else state)])
        return subprocess.CompletedProcess([], code, out.getvalue(), err.getvalue())

    def assert_result(self, result, code, lines):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, "\n".join(lines) + "\n")

    def assert_state_finding(self, state):
        self.write_rows({"state": state}, {"state": state})
        self.assert_result(self.call_main(), 1, ["bundles 2", f"state {state} 2",
                           "proposed-expired 0", "undo-bundles 0", f"FAIL {state} 2", FAIL])

    def snapshot_input(self):
        return {str(path.relative_to(self.state)): (path.stat().st_mtime_ns,
                path.read_bytes() if path.is_file() else None)
                for path in (self.state, *self.state.rglob("*"))}

    def test_c1_full_pass(self):
        # Insertion/alphabetical order or treating terminal failures as findings is wrong.
        self.write_rows({"state": "undone"}, {"state": "failed"},
                        {"state": "done", "undo_of": "fixture-old-key"},
                        {"state": "done", "undo_of": 1}, {"state": "proposed"})
        self.assert_result(self.run_report(), 0, ["bundles 5", "state proposed 1", "state done 2",
                           "state failed 1", "state undone 1", "proposed-expired 0",
                           "undo-bundles 1", PASS])

    def test_c2_1_unsafe_state(self):
        # A follow-symlinks check accepts the right type at the wrong path.
        alias = self.root / "state-alias"
        alias.symlink_to(self.state, target_is_directory=True)
        plain = self.root / "plain-file"
        plain.touch()
        other = self.root / "other"
        other.mkdir()
        (other / "clover").symlink_to(self.clover, target_is_directory=True)
        plain_clover = self.root / "plain-clover"
        plain_clover.mkdir()
        (plain_clover / "clover").touch()
        for state in (alias, plain, self.root / "missing", other, plain_clover):
            with self.subTest(state=state.name):
                self.assert_result(self.call_main(state), 1, ["FAIL unsafe-state", FAIL])
        self.store.symlink_to(plain)
        self.assert_result(self.call_main(), 1, ["FAIL unsafe-state", FAIL])
        self.store.unlink()
        self.store.mkdir()
        self.assert_result(self.call_main(), 1, ["FAIL unsafe-state", FAIL])

    def test_c2_2_bad_row(self):
        # Bad JSON, invalid UTF-8, non-objects and non-string/missing states are counted separately.
        self.write_rows("{truncated", b"\xff", ["proposed"], {}, {"state": 1}, {"state": "done"})
        self.assert_result(self.run_report(), 1, ["bundles 6", *DONE[1:-1],
                           "FAIL bad-row 5", FAIL])

    def test_c2_3_unknown_state(self):
        # An unfamiliar state is neither skipped, printed, nor confused with a malformed row.
        self.write_rows({"state": "future-state"}, {"state": "future-state"}, {"state": "done"})
        self.assert_result(self.run_report(), 1, ["bundles 3", *DONE[1:-1],
                           "FAIL unknown-state 2", FAIL])

    def test_c2_4_till_uncertain(self):
        # Unconfirmed till writes require a distinct finding, counted once in aggregate.
        self.assert_state_finding("till-uncertain")

    def test_c2_5_partial(self):
        # A partial write must not be treated as a settled till change.
        self.assert_state_finding("partial")

    def test_c2_6_split(self):
        # A site/till split has its own finding, not an in-flight or partial one.
        self.assert_state_finding("split")

    def test_c2_7_in_flight(self):
        # Looking only at intent states misses restarts after successful intermediate writes.
        states = ("till-intent", "till-applied", "link-written", "site-intent", "site-live")
        self.write_rows(*({"state": name} for name in reversed(states)), {"state": "done"})
        self.assert_result(self.run_report(), 1, ["bundles 6", *[f"state {name} 1" for name in states],
                           *DONE[1:-1], "FAIL in-flight 5", FAIL])

    def test_c2_8_not_sqlite(self):
        # Corruption, missing schema and both kinds of unsafe sidecar must not pass as empty.
        failure = [f"FAIL not-sqlite {STORE}", FAIL]
        self.store.write_bytes(b"synthetic non-database")
        self.assert_result(self.call_main(), 1, failure)
        self.store.unlink()
        for schema in ("CREATE TABLE decoy(row TEXT)", "CREATE TABLE bundles(wrong_column TEXT)"):
            with self.subTest(schema=schema):
                with closing(sqlite3.connect(self.store)) as db:
                    db.execute(schema)
                self.assert_result(self.call_main(), 1, failure)
                self.store.unlink()
        self.write_rows({"state": "done"})
        for suffix in ("-wal", "-journal"):
            with self.subTest(suffix=suffix):
                sidecar = self.store.with_name(STORE + suffix)
                sidecar.symlink_to(self.root / "missing-target")
                self.assert_result(self.call_main(), 1, failure)
                sidecar.unlink()
                sidecar.mkdir()
                self.assert_result(self.call_main(), 1, failure)
                sidecar.rmdir()

    def test_c2_9_temp_unavailable(self):
        # With no acceptable parent, don't fall back to tempfile defaults or mislabel the DB.
        self.write_rows({"state": "done"})
        before = self.snapshot_input()
        with patch.object(REPORT, "_temp_candidates", return_value=[self.state, self.root / "missing"]):
            self.assert_result(self.call_main(), 1, ["FAIL temp-unavailable", FAIL])
        self.assertEqual(self.snapshot_input(), before)

    def test_c3_usage_exit_2(self):
        # Argument errors must not turn into report findings or expose bad values.
        for args in ((), ("--state",), ("--state", str(self.state), "--unknown", str(self.state)),
                     ("--state", str(self.state), "--now", str(self.state)),
                     ("--state", str(self.state), "--now", "2030-01-01T00:00:00")):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # C3 has no stdout trailer by design.
                self.assertIn("usage: clover_bundle_report.py", result.stderr)
                self.assertNotIn(str(self.state), result.stderr)

    def test_c4_read_only(self):
        # Even a read-only SQLite open in place can create WAL/SHM files.
        with closing(sqlite3.connect(self.store)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            self.seed(db, [{"state": "done"}])
        self.assertEqual(set(self.clover.iterdir()), {self.store})
        before = self.snapshot_input()
        self.assert_result(self.run_report(), 0, DONE)
        self.assertEqual(self.snapshot_input(), before)

    def test_c5_no_private_values(self):
        # Printing a raw row, rejected state, or parser/SQLite exception can disclose input.
        bundle = {"code": "synthetic-code-canary", "bundle_hash": "synthetic-hash-canary",
                  "lines": ["synthetic-preview-canary"]}
        private = {"sender": "synthetic-sender-canary", "chat": "synthetic-chat-canary",
                   "reply": "synthetic-reply-canary", "change_id": "synthetic-change-canary"}
        unknown = "synthetic-state-canary"
        bad = "synthetic-malformed-canary"
        self.write_rows({"state": "done", "bundle": bundle, **private},
                        {"state": unknown}, bad)
        canaries = [bundle["code"], bundle["bundle_hash"], *bundle["lines"], *private.values(),
                    unknown, bad, "fixture-key-0", str(self.state), str(self.store)]
        result = self.run_report()
        for token in canaries:
            self.assertNotIn(token, result.stdout)
            self.assertNotIn(token, result.stderr)
        self.assert_result(result, 1, ["bundles 3", *DONE[1:-1], "FAIL bad-row 1",
                           "FAIL unknown-state 1", FAIL])

    def test_c6_absent_pass(self):
        # Connecting at the source could create the very store we're checking for.
        before = self.snapshot_input()
        self.assert_result(self.run_report(), 0, ["bundles absent", PASS])
        self.assertEqual(self.snapshot_input(), before)
        empty_state = self.root / "without-clover"
        empty_state.mkdir()
        self.assert_result(self.run_report(state=empty_state), 0, ["bundles absent", PASS])
        self.assertEqual(list(empty_state.iterdir()), [])

    def test_c7_expiry_uses_now(self):
        # Offset, equality, and non-numeric values distinguish expiry from wall-clock or coercion.
        now = "2030-01-01T01:00:00+01:00"
        seconds = datetime.fromisoformat(now).timestamp()
        self.write_rows(*({"state": "proposed", "expires": expiry}
                          for expiry in (seconds - 1, seconds, seconds + 1, str(seconds), True)),
                        {"state": "done", "expires": seconds - 1})
        self.assert_result(self.run_report("--now", now), 0, ["bundles 6", "state proposed 5",
                           "state done 1", "proposed-expired 2", "undo-bundles 0", PASS])

    def test_c8_wal_rows_counted(self):
        # Skipping the WAL (or using immutable SQLite) drops the committed insert.
        producer = self.root / "producer.sqlite3"
        with closing(sqlite3.connect(producer)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA wal_autocheckpoint=0")
            self.seed(db, [])
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.execute("INSERT INTO bundles VALUES (?, ?)", ("fixture-key", '{"state":"done"}'))
            db.commit()
            shutil.copyfile(producer, self.store)
            control = self.root / "no-wal.sqlite3"
            shutil.copyfile(producer, control)
            with closing(sqlite3.connect(control)) as without_wal:
                self.assertEqual(without_wal.execute("SELECT COUNT(*) FROM bundles").fetchone(), (0,))
            shutil.copyfile(producer.with_name(producer.name + "-wal"), self.store.with_name(STORE + "-wal"))
        self.assertFalse(self.store.with_name(STORE + "-shm").exists())
        before = self.snapshot_input()
        self.assert_result(self.run_report(), 0, DONE)
        self.assertEqual(self.snapshot_input(), before)
        # The source SHM is not an input, even when it isn't a regular file.
        self.store.with_name(STORE + "-shm").mkdir()
        before = self.snapshot_input()
        self.assert_result(self.run_report(), 0, DONE)
        self.assertEqual(self.snapshot_input(), before)

    def test_c9_tmpdir_inside_input(self):
        # Even a temporary probe in the input changes its mtime; lexical checks miss aliases.
        self.write_rows({"state": "done"})
        nested = self.clover / "nested"
        nested.mkdir()
        alias = self.root / "temp-alias"
        alias.symlink_to(nested, target_is_directory=True)
        fallback = self.root / "fixture-state-fallback"
        fallback.mkdir()
        for directory in (self.state, self.clover, nested):
            os.utime(directory, (1, 1))
        before = self.snapshot_input()
        for candidate in (self.state, nested, alias):
            with self.subTest(candidate=candidate.name):
                env = dict(os.environ, TMPDIR=str(candidate), TEMP=str(fallback))
                self.assert_result(self.run_report(env=env), 0, DONE)
                self.assertEqual(self.snapshot_input(), before)
                self.assertEqual(list(fallback.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
