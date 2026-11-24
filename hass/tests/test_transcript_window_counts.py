"""Offline CLI contracts for the transcript window report."""

from contextlib import closing, redirect_stderr, redirect_stdout
from hashlib import sha256
import importlib.util
import io
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/transcript_window_counts.py"
NAME = "transcript.sqlite3"
PASS = "PASS transcript_window_counts"
FAIL = "FAIL transcript_window_counts"
SINCE = "2040-06-14T10:00:00Z"
UNTIL = "2040-06-14T11:00:00Z"
CHAT = "fixture chat alpha"
SECOND_CHAT = "fixture chat β"
PRIVATE = (
    "fixture message marker",
    "fixture sender marker",
    "fixture provider-id marker",
    "fixture reply-to marker",
    "fixture attachment marker",
    "fixture draft-code marker",
)
# Allow NULL utc here to model a store with missing timestamps.
SCHEMA = """CREATE TABLE events (
    utc TEXT, chat TEXT, direction TEXT, kind TEXT, disposition TEXT,
    text TEXT, sender TEXT, provider_id TEXT, reply_to TEXT, attachments TEXT, draft_code TEXT
)"""
INSERT = "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"


def event(utc: str | None = SINCE, chat=CHAT, direction="in", kind="message", disposition="received",
          draft=None):
    return (utc, chat, direction, kind, disposition, *PRIVATE[:5], draft)


class TranscriptWindowCountsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        # The URI must treat query and fragment characters as part of the path.
        self.state = self.root / "fixture ?mode=rw#snapshot%"
        self.state.mkdir()
        self.db = self.state / NAME

    def seed(self, *rows, path=None):
        with closing(sqlite3.connect(path or self.db)) as db, db:
            db.execute(SCHEMA)
            db.executemany(INSERT, rows)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def invoke(self, *flags, since=SINCE, until=UNTIL, state=None):
        return self.cli("--state", str(state or self.state), "--since", since, "--until", until, *flags)

    def assert_pass(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(result.stderr, "")
        return result.stdout.splitlines()[:-1]

    def assert_findings(self, result, *reasons):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [*(f"FAIL {reason}" for reason in reasons), FAIL])
        self.assertEqual(result.stderr, "")

    def test_c1_full_pass(self):
        # Lexical times, an inclusive upper bound, raw labels, or truth-testing draft codes fail.
        self.seed(
            event("2040-06-14T12:00:00+02:00", SECOND_CHAT, "out", "notice", "sent", ""),
            event("2040-06-14T09:59:59.999999+00:00", direction="before"),
            event("2040-06-14T06:59:59.999999-04:00", direction="in"),
            event("2040-06-14T10:30:00Z", direction="in\n", kind="a" * 33, disposition="9sent"),
            event("2040-06-14T13:00:00+02:00", direction="at-end"),
            event("2040-06-14T11:00:00.000001Z", direction="after"),
            event(None), event("2040-06-14T10:15:00"), event("not-an-iso-time"),
        )
        chats = sorted((sha256(chat.encode()).hexdigest()[:12], count)
                       for chat, count in ((CHAT, 2), (SECOND_CHAT, 1)))
        self.assertEqual(self.assert_pass(self.invoke()), [
            "events 3", "direction in 1", "direction other 1", "direction out 1",
            "kind message 1", "kind notice 1", "kind other 1",
            "disposition other 1", "disposition received 1", "disposition sent 1",
            *(f"chat {digest} {count}" for digest, count in chats), "draft-codes 1", "unparsed 3",
        ])
        # Strict mode must count all unassignable rows without printing partial aggregates.
        self.assert_findings(self.invoke("--require-complete"), "incomplete-window unparsed 3")

    def test_c2_1_missing_db(self):
        # A writable connection could silently create a missing DB.
        self.assert_findings(self.invoke(), f"missing-db {NAME}")
        self.assertEqual(list(self.state.iterdir()), [])

    def test_c2_2_unsafe_db(self):
        # Following a symlink accepts a valid decoy; stat() misclassifies a dangling link.
        target = self.root / "decoy.sqlite3"
        self.seed(event(), path=target)
        self.db.symlink_to(target)
        self.assert_findings(self.invoke(), f"unsafe-db {NAME}")
        dangling = self.root / "dangling"
        dangling.mkdir()
        (dangling / NAME).symlink_to(self.root / "absent")
        self.assert_findings(self.invoke(state=dangling), f"unsafe-db {NAME}")
        directory = self.root / "directory-store"
        (directory / NAME).mkdir(parents=True)
        self.assert_findings(self.invoke(state=directory), f"unsafe-db {NAME}")

    def test_c2_3_not_sqlite(self):
        # A connect-only check misses unreadable data and absent tables/columns.
        self.db.write_bytes(b"fixture: not a database")
        self.assert_findings(self.invoke(), f"not-sqlite {NAME}")
        for ddl in ("CREATE TABLE unrelated (utc TEXT)",
                    "CREATE TABLE events (utc TEXT, chat TEXT, direction TEXT, kind TEXT, disposition TEXT)"):
            with self.subTest(ddl=ddl), tempfile.TemporaryDirectory(dir=self.root) as directory:
                state = Path(directory)
                with closing(sqlite3.connect(state / NAME)) as db, db:
                    db.execute(ddl)
                self.assert_findings(self.invoke(state=state), f"not-sqlite {NAME}")

    def test_c2_4_bad_window(self):
        # Parsing either bound without an offset, or allowing a zero/reversed window, fails.
        self.seed()
        for since, until in (
            ("bad", UNTIL), (SINCE, "bad"), ("2040-06-14T10:00:00", UNTIL),
            (SINCE, "2040-06-14T11:00:00"), (SINCE, "2040-06-14T12:00:00+02:00"),
            (UNTIL, SINCE),
        ):
            with self.subTest(since=since, until=until):
                self.assert_findings(self.invoke(since=since, until=until), "bad-window")
        self.assert_findings(self.invoke(since="bad", state=self.root),
                             "bad-window", f"missing-db {NAME}")

    def test_c3_usage_exit_2(self):
        # Missing or unknown options are usage errors, not tool findings.
        for args in (("--state", str(self.state), "--since", SINCE),
                     ("--state", str(self.state), "--since", SINCE, "--until", UNTIL, "--bogus")):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage:"))

    def assert_unchanged(self, expected_events):
        def snapshot():
            return {p.name: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_mode)
                    for p in self.state.iterdir()}

        before = snapshot()
        self.assertEqual(self.assert_pass(self.invoke())[0], f"events {expected_events}")
        self.assertEqual(snapshot(), before)

    def test_c4_read_only(self):
        # Opening a WAL database with plain mode=ro can create SHM files.
        self.seed(event())
        self.assert_unchanged(1)
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("PRAGMA locking_mode=EXCLUSIVE")
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
            with db:
                db.execute(INSERT, event())
            self.assertEqual({p.name for p in self.state.iterdir()}, {NAME, f"{NAME}-wal"})
            self.assert_unchanged(2)

    def test_c5_no_private_values(self):
        # Raw rows, full hashes, database errors and argparse errors can leak canaries.
        invalid_label = "fixture category marker\nPASS synthetic"
        self.seed(event(direction=invalid_label, draft=PRIVATE[-1]))
        spec = importlib.util.spec_from_file_location("transcript_window_counts", SCRIPT)
        assert spec is not None and spec.loader is not None
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)

        allowed = {"utc", "chat", "direction", "kind", "disposition", "draft_code"}
        connect = sqlite3.connect

        def authorize(action, table, column, _schema, _trigger):
            if action == sqlite3.SQLITE_READ and (table != "events" or column not in allowed):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        def guarded_connect(*args, **kwargs):
            db = connect(*args, **kwargs)
            db.set_authorizer(authorize)
            return db

        args = ["--state", str(self.state), "--since", SINCE, "--until", UNTIL]
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(tool.sqlite3, "connect", guarded_connect), redirect_stdout(stdout), redirect_stderr(stderr):
            code = tool.main(args)
        success = subprocess.CompletedProcess(args, code, stdout.getvalue(), stderr.getvalue())
        digest = sha256(CHAT.encode()).hexdigest()
        self.assertIn(f"chat {digest[:12]} 1", self.assert_pass(success))
        broken = self.root / "fixture-error-source"
        broken.mkdir()
        (broken / NAME).write_bytes(PRIVATE[0].encode())
        failure = self.invoke(state=broken)
        self.assert_findings(failure, f"not-sqlite {NAME}")
        usage = self.cli(*args, str(broken))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (success, failure, usage):
            for canary in (*PRIVATE, CHAT, digest[12:], invalid_label.splitlines()[0], str(self.root)):
                self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_empty_window_passes(self):
        # Ignoring unparsed rows in the strict verdict would mistake incomplete
        # evidence for a quiet window. A parsable row at the upper bound is excluded.
        self.seed(event("2040-06-14T13:00:00+02:00"))
        empty = ["events 0", "draft-codes 0", "unparsed 0"]
        self.assertEqual(self.assert_pass(self.invoke()), empty)
        self.assertEqual(self.assert_pass(self.invoke("--require-complete")), empty)

        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute(INSERT, event("fixture malformed timestamp"))
        self.assert_findings(self.invoke("--require-complete"), "incomplete-window unparsed 1")
        self.assertEqual(self.assert_pass(self.invoke()), ["events 0", "draft-codes 0", "unparsed 1"])
