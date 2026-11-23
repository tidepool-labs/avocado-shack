"""Offline contract tests for the inbox payload checker."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
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
from unittest import mock

from hass.conversation import Inbound
from hass.inbox import Inbox, SCHEMA


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/inbox_payload_check.py"
STORE = "inbox.sqlite3"
PASS = "PASS inbox_payload_check"
FAIL = "FAIL inbox_payload_check"
STAMP = "2000-01-02T00:00:00+00:00"


def insert_rows(db, rows):
    db.executemany(
        "INSERT INTO inbound (provider_id, received_at, payload, state, disposition, enqueued_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(f"synthetic-id-{i}", STAMP, payload, state, "synthetic-disposition", STAMP)
         for i, (state, payload) in enumerate(rows)],
    )
    db.commit()


def fingerprint(root):
    return {path.relative_to(root): (path.stat().st_mtime_ns, None if path.is_dir() else path.read_bytes())
            for path in (root, *root.rglob("*"))}


class InboxPayloadCheckTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.state = self.root / "synthetic-state"
        self.state.mkdir(mode=0o700)
        self.scratch = self.root / "checker-scratch"
        self.scratch.mkdir()
        self.store = self.state / STORE

    def fixture(self, *rows, store=None, wal=False):
        with closing(sqlite3.connect(store or self.store)) as db:
            if wal:
                db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            insert_rows(db, rows)

    def run_cli(self, *args, tmpdir=None):
        env = dict(os.environ, TMPDIR=str(tmpdir or self.scratch), TEMP=str(self.scratch))
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)],
                              cwd=self.root, env=env, capture_output=True, text=True, timeout=10)

    def check(self, *lines, exit_code=0, state=None, tmpdir=None):
        run = self.run_cli("--state", state or self.state, tmpdir=tmpdir)
        self.assertEqual(run.returncode, exit_code, run.stderr)
        self.assertEqual(run.stderr, "")
        self.assertEqual(run.stdout.splitlines(), [*lines, FAIL if exit_code else PASS])
        self.assertEqual(list(self.scratch.iterdir()), [])
        return run.stdout, run.stderr

    def test_c1_full_pass(self):
        # Pending data is allowed; state counts are emitted in contract order, not insertion order.
        self.fixture(("history", None), ("done", None), ("pending", "synthetic-caption"), ("done", None))
        self.check("inbound 4", "state pending 1", "state done 2", "state history 1")

    def test_c2_1_unsafe_state(self):
        # Following even a dangling link could make unsafe state look absent.
        missing = self.root / "missing"
        alias = self.root / "alias"
        alias.symlink_to(self.state, target_is_directory=True)
        file_state = self.root / "file-state"
        file_state.touch()
        for path in (missing, alias, file_state):
            with self.subTest(case=path.name):
                self.check("FAIL unsafe-state", exit_code=1, state=path)
        for kind in ("directory", "dangling-link"):
            with self.subTest(store=kind), tempfile.TemporaryDirectory(dir=self.root) as directory:
                store = Path(directory) / STORE
                if kind == "directory":
                    store.mkdir()
                else:
                    store.symlink_to(missing)
                self.check("FAIL unsafe-state", exit_code=1, state=store.parent)

    def test_c2_2_payload_kept_done(self):
        # Count only offending rows; even an empty string still occupies the payload column.
        self.fixture(("done", "synthetic-caption"), ("done", ""), ("done", None))
        self.check("inbound 3", "state done 3", "FAIL payload-kept done 2", exit_code=1)

    def test_c2_3_payload_kept_history(self):
        # Skipping history entirely would miss retained payloads.
        self.fixture(("history", "synthetic-caption"))
        self.check("inbound 1", "state history 1", "FAIL payload-kept history 1", exit_code=1)

    def test_c2_4_pending_empty(self):
        # A NULL pending payload cannot be decoded by a future drain.
        self.fixture(("pending", None), ("pending", "synthetic-caption"))
        self.check("inbound 2", "state pending 2", "FAIL pending-empty 1", exit_code=1)

    def test_c2_5_not_sqlite(self):
        # Refuse broken schema and content rather than certifying an empty inbox.
        for schema in (None, "CREATE TABLE other (state, payload)", "CREATE TABLE inbound (state)",
                       "CREATE TABLE inbound (payload)"):
            with self.subTest(schema=schema), tempfile.TemporaryDirectory(dir=self.root) as directory:
                store = Path(directory) / STORE
                if schema is None:
                    store.write_bytes(b"synthetic non-SQLite bytes")
                else:
                    with closing(sqlite3.connect(store)) as db:
                        db.execute(schema)
                self.check(f"FAIL not-sqlite {STORE}", exit_code=1, state=store.parent)
        # An unsafe sidecar must not be followed or silently discarded.
        for suffix in ("-wal", "-journal"):
            for kind in ("directory", "dangling-link"):
                with self.subTest(suffix=suffix, kind=kind), tempfile.TemporaryDirectory(dir=self.root) as directory:
                    store = Path(directory) / STORE
                    self.fixture(("done", None), store=store)
                    sidecar = store.with_name(STORE + suffix)
                    if kind == "directory":
                        sidecar.mkdir()
                    else:
                        sidecar.symlink_to(self.root / "missing")
                    self.check(f"FAIL not-sqlite {STORE}", exit_code=1, state=store.parent)

    def test_c2_6_temp_unavailable(self):
        # Exhaust the candidate list without depending on machine-wide permissions.
        self.fixture(("done", None))
        spec = importlib.util.spec_from_file_location("inbox_payload_check", SCRIPT)
        assert spec is not None and spec.loader is not None
        checker = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(checker)
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(checker, "_temp_candidates", return_value=[self.state, self.root / "missing"]), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(checker.main(["--state", str(self.state)]), 1)
        self.assertEqual(stdout.getvalue().splitlines(), ["FAIL temp-unavailable", FAIL])
        self.assertEqual(stderr.getvalue(), "")

    def test_c2_multiple_findings(self):
        # Do not stop at the first mismatch or change the order of findings.
        self.fixture(("history", "synthetic-caption"), ("pending", None), ("done", "synthetic-caption"))
        self.check("inbound 3", "state pending 1", "state done 1", "state history 1",
                   "FAIL payload-kept done 1", "FAIL payload-kept history 1", "FAIL pending-empty 1", exit_code=1)

    def test_c3_usage_exit_2(self):
        # These errors belong to argparse, not the report's FAIL path.
        for args in ((), ("--state",), ("--state", self.state, "--unknown")):
            with self.subTest(args=args):
                run = self.run_cli(*args)
                self.assertEqual(run.returncode, 2)
                self.assertEqual(run.stdout, "")  # No last stdout line on a usage error.
                self.assertIn("error:", run.stderr)

    def test_c4_read_only(self):
        # Opening the original SQLite file even in mode=ro can create WAL sidecars.
        self.fixture(("done", None), wal=True)
        before = fingerprint(self.state)
        self.check("inbound 1", "state done 1")
        self.assertEqual(fingerprint(self.state), before)

    def test_c5_no_private_values(self):
        # A row dump could leak identifiers, dispositions, or a retained caption.
        self.fixture(("done", "synthetic-private-caption"), ("pending", "placeholder"))
        with closing(sqlite3.connect(self.store)) as db, db:
            # Selecting the raw TEXT would also fail decoding this pending payload.
            db.execute("UPDATE inbound SET payload = CAST(x'ff' AS TEXT) WHERE state = 'pending'")
        stdout, stderr = self.check("inbound 2", "state pending 1", "state done 1",
                                    "FAIL payload-kept done 1", exit_code=1)
        for value in ("synthetic-private-caption", "synthetic-id-0", "synthetic-id-1",
                      "synthetic-disposition", str(self.state), str(self.store)):
            self.assertNotIn(value, stdout + stderr)

    def test_c6_absent_pass(self):
        # sqlite3.connect on a missing source would create it.
        before = fingerprint(self.state)
        self.check("inbox absent")
        self.assertEqual(fingerprint(self.state), before)

    def test_c7_real_inbox_pass(self):
        # An invented fixture schema alone cannot prove compatibility with the real writer.
        stamp = datetime.fromisoformat(STAMP)

        class ConversationStub:
            def handle(self, msg, last_try=False):
                return "synthetic-disposition"

        def message(provider_id, when):
            return Inbound(provider_id, "synthetic-chat", "synthetic-sender", "synthetic-caption",
                           False, "new", when.isoformat())

        with closing(Inbox(self.state, STAMP, clock=lambda: stamp)) as inbox:
            self.assertEqual(inbox.enqueue(message("synthetic-new-id", stamp)), "queued")
            self.assertEqual(inbox.drain(ConversationStub()), [("synthetic-new-id", "synthetic-disposition")])
            self.assertEqual(inbox.enqueue(message("synthetic-old-id", stamp - timedelta(seconds=1))), "history")
        self.check("inbound 2", "state done 1", "state history 1")

    def test_c8_wal_rows_counted(self):
        # The bare database has the schema but not the committed row. SHM is not portable or needed.
        writer = self.root / "writer.sqlite3"
        with closing(sqlite3.connect(writer)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
            db.execute("PRAGMA wal_autocheckpoint=0")
            db.executescript(SCHEMA)
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            bare = writer.read_bytes()
            insert_rows(db, [("done", None)])
            self.assertEqual(writer.read_bytes(), bare)
            shutil.copyfile(writer, self.store)
            shutil.copyfile(writer.with_name(writer.name + "-wal"), self.state / (STORE + "-wal"))
        before = fingerprint(self.state)
        self.assertFalse((self.state / (STORE + "-shm")).exists())
        self.check("inbound 1", "state done 1")
        self.assertEqual(fingerprint(self.state), before)

    def test_c9_tmpdir_inside_input(self):
        # Briefly creating scratch under state can leave no files but still change directory mtime.
        self.fixture(("history", None))
        child = self.state / "nested"
        child.mkdir()
        alias = self.root / "nested-alias"
        alias.symlink_to(child, target_is_directory=True)
        for temp in (self.state, child, alias):
            with self.subTest(candidate=temp.name):
                before = fingerprint(self.state)
                self.check("inbound 1", "state history 1", tmpdir=temp)
                self.assertEqual(fingerprint(self.state), before)


if __name__ == "__main__":
    unittest.main()
