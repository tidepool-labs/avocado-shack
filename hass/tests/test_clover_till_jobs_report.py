"""Offline CLI contract for the approved till-change queue report."""

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

from hass.clover.approvals import MAX_JOBS, SCHEMA


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/clover_till_jobs_report.py"
SPEC = importlib.util.spec_from_file_location("clover_till_jobs_report", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)
STORE = "conversation.sqlite3"
NOW = "2031-06-02T12:00:00+00:00"
STAMP = "2031-06-02T11:30:00Z"
PASS = "PASS clover_till_jobs_report"
FAIL = "FAIL clover_till_jobs_report"


class CloverTillJobsReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / "synthetic-private-state"
        self.state.mkdir()
        self.store = self.state / STORE
        self.scratch = self.root / "snapshot-temp"
        self.scratch.mkdir()
        self.enterContext(patch.dict(os.environ, {"TMPDIR": str(self.scratch)}))

    def make_jobs(self, rows, *, store=None):
        with closing(sqlite3.connect(self.store if store is None else store)) as db:
            db.execute("CREATE TABLE till_jobs (received_at TEXT, done INTEGER, allowed INTEGER)")
            db.executemany("INSERT INTO till_jobs VALUES (?, ?, ?)", rows)
            db.commit()

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = report.main(list(args))
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def run_report(self, *, state=None, now=NOW):
        return self.invoke("--state", str(self.state if state is None else state), "--now", now)

    def run_cli(self):
        proc = subprocess.run([sys.executable, "-B", str(SCRIPT), "--state", str(self.state)],
                              cwd=self.root, capture_output=True, text=True, timeout=10)
        return proc.returncode, proc.stdout, proc.stderr

    def assert_result(self, result, code, last, body):
        actual_code, out, err = result
        self.assertEqual(actual_code, code)
        self.assertEqual(out, "\n".join([*body, last]) + "\n")
        self.assertEqual(err, "")
        self.assertEqual(list(self.scratch.iterdir()), [])

    def counts(self, jobs, done, pending, denied=0):
        return [f"jobs {jobs}", f"done {done}", f"pending {pending}",
                f"pending-not-allowed {denied}", f"capacity {pending}/{MAX_JOBS}"]

    def input_tree(self):
        tree = {}
        for path in (self.state, *self.state.rglob("*")):
            info = path.lstat()
            contents = os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file() else None
            tree[path.relative_to(self.state)] = (info.st_mtime_ns, contents)
        return tree

    def test_c1_full_pass(self):
        # Completed rows must not cause a finding; the script must run outside the repo cwd.
        self.make_jobs([(STAMP, 1, 1), (STAMP, 1, 0)])
        self.assert_result(self.run_cli(), 0, PASS, self.counts(2, 2, 0))

    def test_c2_1_unsafe_state(self):
        # Following either symlink, or treating a non-file store as absent, is wrong.
        alias = self.root / "alias"
        alias.symlink_to(self.state, target_is_directory=True)
        ordinary = self.root / "not-a-directory"
        ordinary.touch()
        target = self.root / "other.sqlite3"
        self.make_jobs([], store=target)
        for state in (alias, ordinary, self.root / "missing"):
            with self.subTest(state=state.name):
                self.assert_result(self.run_report(state=state), 1, FAIL, ["FAIL unsafe-state"])
        self.store.symlink_to(target)
        self.assert_result(self.run_report(), 1, FAIL, ["FAIL unsafe-state"])
        self.store.unlink()
        self.store.mkdir()
        self.assert_result(self.run_report(), 1, FAIL, ["FAIL unsafe-state"])

    def test_c2_2_pending(self):
        # A below-cap queue still fails, and denied completed rows are not pending denials.
        self.make_jobs([(STAMP, 0, 1), (STAMP, 0, 0), (STAMP, 1, 0)])
        self.assert_result(self.run_report(), 1, FAIL,
                           [*self.counts(3, 1, 2, 1), "oldest-pending-minutes 30", "FAIL pending 2"])

    def test_c2_3_queue_full(self):
        # Total rows and strictly-greater-than comparisons give the wrong answer at the cap.
        self.make_jobs([(STAMP, 0, 1)] * MAX_JOBS)
        self.assert_result(self.run_report(), 1, FAIL,
                           [*self.counts(MAX_JOBS, 0, MAX_JOBS), "oldest-pending-minutes 30",
                            f"FAIL pending {MAX_JOBS}", "FAIL queue-full"])
        with closing(sqlite3.connect(self.store)) as db:
            db.execute("UPDATE till_jobs SET done=1 WHERE rowid=1")
            db.commit()
        self.assert_result(self.run_report(), 1, FAIL,
                           [*self.counts(MAX_JOBS, 1, MAX_JOBS - 1), "oldest-pending-minutes 30",
                            f"FAIL pending {MAX_JOBS - 1}"])

    def test_c2_4_bad_time(self):
        # Bad completed times count, but only bad pending times suppress oldest age.
        self.make_jobs([(STAMP, 0, 1), ("2031-06-02T11:00:00", 1, 1)])
        self.assert_result(self.run_report(), 1, FAIL,
                           [*self.counts(2, 1, 1), "oldest-pending-minutes 30", "FAIL pending 1",
                            "FAIL bad-time 1"])
        with closing(sqlite3.connect(self.store)) as db:
            db.executemany("INSERT INTO till_jobs VALUES (?, 0, 1)", [("not-a-time",), (b"bytes",)])
            db.commit()
        self.assert_result(self.run_report(), 1, FAIL,
                           [*self.counts(4, 1, 3), "FAIL pending 3", "FAIL bad-time 3"])

    def test_c2_5_not_sqlite(self):
        # Broken SQLite, a missing column, and unsafe recovery sidecars must not pass as absent.
        finding = [f"FAIL not-sqlite {STORE}"]
        self.store.write_bytes(b"not a SQLite file")
        self.assert_result(self.run_report(), 1, FAIL, finding)
        self.store.unlink()
        with closing(sqlite3.connect(self.store)) as db:
            db.execute("CREATE TABLE till_jobs (done INTEGER, allowed INTEGER)")
        self.assert_result(self.run_report(), 1, FAIL, finding)
        self.store.unlink()
        self.make_jobs([])
        for suffix in ("-wal", "-journal"):
            sidecar = self.state / (STORE + suffix)
            with self.subTest(sidecar=suffix, kind="symlink"):
                sidecar.symlink_to(self.root / "missing-recovery-file")
                self.assert_result(self.run_report(), 1, FAIL, finding)
                sidecar.unlink()
            with self.subTest(sidecar=suffix, kind="directory"):
                sidecar.mkdir()
                self.assert_result(self.run_report(), 1, FAIL, finding)
                sidecar.rmdir()

    def test_c2_6_temp_unavailable(self):
        # No usable temp parent has its own finding and must not fall back inside state.
        self.make_jobs([])
        alias = self.root / "temp-alias"
        alias.symlink_to(self.state, target_is_directory=True)
        before = self.input_tree()
        with patch.object(report, "_temp_candidates", return_value=[str(alias), str(self.store)]):
            self.assert_result(self.run_report(), 1, FAIL, ["FAIL temp-unavailable"])
        self.assertEqual(self.input_tree(), before)

    def test_c3_usage_exit_2(self):
        # CLI misuse must remain argparse usage (no report or terminal marker).
        args = ("--state", str(self.state))
        for options in ((), (*args, "--unknown"), (*args, "--now", "2031-06-02T12:00:00"),
                        (*args, "--now", "not-a-time"), (*args, "--now")):
            with self.subTest(options=options):
                code, out, err = self.invoke(*options)
                self.assertEqual((code, out.splitlines()), (2, []))
                self.assertEqual(out, "")
                self.assertTrue(err.splitlines()[0].startswith("usage: "))
                self.assertIn("error:", err.splitlines()[-1])

    def test_c4_read_only(self):
        # Opening even a checkpointed WAL-mode input directly can create sidecars.
        self.make_jobs([(STAMP, 1, 1)])
        with closing(sqlite3.connect(self.store)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
        self.assertEqual(list(self.state.iterdir()), [self.store])
        before = self.input_tree()
        self.assert_result(self.run_report(), 0, PASS, self.counts(1, 1, 0))
        self.assertEqual(self.input_tree(), before)
        # An ignored -shm name is not a recovery input, even if it cannot be opened.
        (self.state / (STORE + "-shm")).symlink_to(self.root / "missing-shared-memory")
        before = self.input_tree()
        self.assert_result(self.run_report(), 0, PASS, self.counts(1, 1, 0))
        self.assertEqual(self.input_tree(), before)

    def test_c5_no_private_values(self):
        # A row dump, raw parsing error or output from another table leaks private text.
        canaries = [f"synthetic-canary-{field}" for field in
                    ("provider", "journal", "code", "sender", "chat", "bad-time", "other-table")]
        with closing(sqlite3.connect(self.store)) as db:
            db.execute(SCHEMA)
            db.execute("INSERT INTO till_jobs VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0)", canaries[:6])
            db.execute("CREATE TABLE unrelated_conversation (body TEXT)")
            db.execute("INSERT INTO unrelated_conversation VALUES (?)", (canaries[-1],))
            db.commit()
        result = self.run_report()
        self.assert_result(result, 1, FAIL, [*self.counts(1, 0, 1, 1), "FAIL pending 1", "FAIL bad-time 1"])
        for canary in [*canaries, str(self.state), str(self.store)]:
            self.assertNotIn(canary, result[1] + result[2])

    def test_c6_absent_pass(self):
        # A missing store or a legacy store without the table is not broken SQLite.
        self.assert_result(self.run_report(), 0, PASS, ["till jobs absent"])
        self.assertEqual(list(self.state.iterdir()), [])
        with closing(sqlite3.connect(self.store)) as db:
            db.execute("CREATE TABLE unrelated_conversation (body TEXT)")
            db.execute("CREATE VIEW till_jobs AS SELECT body FROM unrelated_conversation")
        self.assert_result(self.run_report(), 0, PASS, ["till jobs absent"])

    def test_c7_oldest_uses_now(self):
        # Wall-clock use, rounding instead of flooring, or including done rows all change this age.
        self.make_jobs([(STAMP, 0, 1), ("2031-06-02T03:29:30-07:00", 0, 1),
                        ("2031-06-01T12:00:00+00:00", 1, 1)])
        for now, age in ((NOW, 90), ("2031-06-02T10:29:00Z", -1)):
            with self.subTest(now=now):
                self.assert_result(self.run_report(now=now), 1, FAIL,
                                   [*self.counts(3, 1, 2), f"oldest-pending-minutes {age}", "FAIL pending 2"])

    def test_c8_wal_rows_counted(self):
        # A main-file-only or immutable open silently reports zero jobs on this snapshot.
        original = self.root / "wal-source.sqlite3"
        self.make_jobs([], store=original)
        with closing(sqlite3.connect(original)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
            db.execute("PRAGMA wal_autocheckpoint=0")
            main_only = original.read_bytes()
            db.execute("INSERT INTO till_jobs VALUES (?, 0, 1)", (STAMP,))
            db.commit()
            self.assertEqual(original.read_bytes(), main_only)
            shutil.copyfile(original, self.store)
            shutil.copyfile(str(original) + "-wal", str(self.store) + "-wal")
        self.assertFalse(Path(str(self.store) + "-shm").exists())
        before = self.input_tree()
        self.assert_result(self.run_report(), 1, FAIL,
                           [*self.counts(1, 0, 1), "oldest-pending-minutes 30", "FAIL pending 1"])
        self.assertEqual(self.input_tree(), before)

    def test_c9_tmpdir_inside_input(self):
        # Final filenames alone miss transient tempfile probes and create/remove cycles.
        self.make_jobs([(STAMP, 1, 1)])
        below = self.state / "nested"
        below.mkdir()
        for path in (self.state, below):
            os.utime(path, ns=(1_000_000_000, 1_000_000_000))
        before = self.input_tree()
        for temp in (self.state, below):
            with self.subTest(temp=temp.name), patch.dict(os.environ, {"TMPDIR": str(temp),
                                                                     "TEMP": str(self.scratch)}):
                self.assert_result(self.run_cli(), 0, PASS, self.counts(1, 1, 0))
                self.assertEqual(self.input_tree(), before)
