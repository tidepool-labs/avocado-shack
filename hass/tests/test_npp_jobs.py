"""Offline CLI contracts for the NPP job list, using the production schema."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import runpy
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass.npp.job import SCHEMA


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_jobs.py"
CREATED = "2025-01-01T09:00:04+00:00"
CANARIES = ("CHAT_CANARY", "SENDER_CANARY", "PHOTO_CANARY", "TEXT_CANARY",
            "PRICE_CANARY", "RECEIPT_CANARY", "SEGMENT_CANARY", "TURN_CANARY")


def job(db, code, state, created=CREATED, closed=None, version=None):
    db.execute("""INSERT INTO npp_jobs
        (job_id,state,created_at,closed_at,current_version,chat,sender,photo_sha,open_request_id)
        VALUES (?,?,?,?,?,'CHAT_CANARY','SENDER_CANARY','PHOTO_CANARY',1)""",
        (code, state, created, closed, version))


class JobsCLI(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory(dir=ROOT.parent)))
        self.state = self.root / "copy ?#.db"

    def fixture(self):
        db = self.enterContext(closing(sqlite3.connect(self.state)))
        db.executescript(SCHEMA)
        return db

    def cli(self, *args, path=None):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), "--state-db",
                               str(path or self.state), *args], capture_output=True, text=True, timeout=15)

    def assert_output(self, result, code, stdout):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stdout, stdout)
        self.assertEqual(result.stderr, "")

    def test_c1_lines(self):
        # Catch counting queued versions, dropping superseded deliveries, or using only creation time.
        # A revision in a live segment must advance the report minute even when segment times don't change.
        with self.fixture() as db:
            job(db, "aaaa", "editing", version=3)
            for n, state, delivered in [(1, "superseded", "2025-01-01T09:06:00Z"),
                                        (2, "delivered", "2025-01-01T04:15:59-05:00"),
                                        (3, "queued", None)]:
                db.execute("""INSERT INTO npp_versions
                    (job_id,n,segment_id,listing_json,listing_sha,patch_json,queued_at,state,delivered_at,transport_message_id)
                    VALUES ('aaaa',?,?,'{"description":"TEXT_CANARY","price":"PRICE_CANARY"}',
                            'fixture','{}','2025-01-01T09:05:00Z',?,?,'RECEIPT_CANARY')""",
                    (n, n, state, delivered))
            job(db, "bbbb", "published", closed="2025-01-01T09:26:00Z", version=1)
            job(db, "cccc", "cancelled", closed="2025-01-01T09:36:00Z")
            job(db, "dddd", "expired", closed="2025-01-01T09:46:00Z")
            job(db, "eeee", "retake")
            db.execute("""INSERT INTO npp_segments (job_id,started_by,accepted_at,deadline_at,ended_at,outcome)
                          VALUES ('eeee','SEGMENT_CANARY','2025-01-01T09:54:00Z',
                                  '2025-01-01T09:57:00Z','2025-01-01T09:56:39Z','retake')""")
            job(db, "ffff", "editing", version=1)
            segment = db.execute("""INSERT INTO npp_segments (job_id,started_by,accepted_at,deadline_at,revision)
                                    VALUES ('ffff','SEGMENT_CANARY','2025-01-01T09:49:00Z',
                                            '2025-01-01T09:52:00Z',1)""").lastrowid
            db.executemany("""INSERT INTO npp_turns (provider_id,job_id,kind,accepted_at,segment_id)
                               VALUES (?,'ffff','edit',?,?)""", [
                ("TURN_CANARY-1", "2025-01-01T09:49:00Z", segment),
                ("TURN_CANARY-2", "2025-01-01T04:51:39-05:00", segment),
            ])
        self.assert_output(self.cli("--all"), 0,
                           "aaaa\tediting\t3\t2\t2025-01-01T09:15Z\topen\n"
                           "bbbb\tpublished\t1\t0\t2025-01-01T09:26Z\tposted\n"
                           "cccc\tcancelled\t-\t0\t2025-01-01T09:36Z\tcancelled\n"
                           "dddd\texpired\t-\t0\t2025-01-01T09:46Z\texpired\n"
                           "eeee\tretake\t-\t0\t2025-01-01T09:56Z\tretake\n"
                           "ffff\tediting\t1\t0\t2025-01-01T09:51Z\topen\n")

    def test_c2_ro(self):
        # Catch writable opens, transient WAL sidecars, stale reads, and linked-worktree aliases.
        db = self.fixture()
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA wal_autocheckpoint=0")
        job(db, "aaaa", "working")
        db.commit()
        wal_copy = self.root / "wal-copy"
        wal_copy.mkdir()
        detached = wal_copy / "state.db"
        shutil.copyfile(self.state, detached)
        shutil.copyfile(str(self.state) + "-wal", str(detached) + "-wal")
        db.close()  # Checkpointed control in WAL mode, with no sidecars.

        def snapshot(folder):
            return folder.stat().st_mtime_ns, {
                p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir() if p.is_file()
            }

        before = snapshot(self.root)
        self.assert_output(self.cli(), 0, "aaaa\tworking\t-\t0\t2025-01-01T09:00Z\topen\n")
        self.assertEqual(snapshot(self.root), before)
        before = snapshot(wal_copy)
        self.assert_output(self.cli(path=detached), 1, "FAIL bad-input non-standalone-copy\n")
        self.assertEqual(snapshot(wal_copy), before)

        entry = runpy.run_path(str(SCRIPT))["main"]
        with patch("sqlite3.connect", wraps=sqlite3.connect) as connect, patch("builtins.print"):
            self.assertEqual(entry(["--state-db", str(self.state)]), 0)
        connect.assert_called_once()
        self.assertTrue(connect.call_args.kwargs["uri"])
        self.assertIn("mode=ro", connect.call_args.args[0].partition("?")[2].split("&"))

        checkout = self.root / "checkout"
        checkout.mkdir()
        (checkout / ".git").write_text("gitdir: ../fixture-git\n", encoding="utf-8")
        in_tree = checkout / "state.db"
        shutil.copyfile(self.state, in_tree)
        alias = self.root / "alias.db"
        alias.symlink_to(in_tree)
        before = snapshot(checkout)
        for path in (in_tree, alias):
            self.assert_output(self.cli(path=path), 1, "FAIL bad-input worktree\n")
        self.assertEqual(snapshot(checkout), before)

    def test_c3_bad(self):
        # Catch silently treating missing schema as an empty list or hiding the missing table name.
        for table in ("npp_jobs", "npp_versions", "npp_segments", "npp_turns"):
            with self.subTest(table=table), closing(sqlite3.connect(self.state)) as db:
                db.executescript(SCHEMA)
                db.execute(f"DROP TABLE {table}")
                self.assert_output(self.cli(), 1, f"FAIL bad-input {table}\n")

    def test_c4_order_privacy(self):
        # Catch date filters that drop stale open jobs, sort by activity, or expose payload columns.
        # Approval and publish failure set closed_at, but their report outcome is still open.
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(days=6)).isoformat()
        older = (now - timedelta(days=8)).isoformat()
        with self.fixture() as db:
            job(db, "aaaa", "published", "2025-01-02T09:00:00Z", older)
            job(db, "cccc", "cancelled", CREATED, recent)
            job(db, "bbbb", "card_out", CREATED)
            job(db, "dddd", "approved", closed=older, version=1)
            job(db, "eeee", "publish_failed", closed=older, version=1)
            db.execute("""INSERT INTO npp_versions
                (job_id,n,segment_id,listing_json,listing_sha,patch_json,state,transport_message_id)
                VALUES ('bbbb',1,1,'TEXT_CANARY','fixture','PRICE_CANARY','queued','RECEIPT_CANARY')""")
            db.execute("""INSERT INTO npp_segments (job_id,started_by,accepted_at,deadline_at)
                          VALUES ('bbbb','SEGMENT_CANARY',?,?)""", (now.isoformat(), now.isoformat()))
            db.execute("""INSERT INTO npp_turns (provider_id,job_id,kind,accepted_at)
                          VALUES ('TURN_CANARY','dddd','yes',?)""", (older,))
        all_ids = ["bbbb", "cccc", "dddd", "eeee", "aaaa"]
        for args, ids in (((), all_ids[:-1]), (("--all",), all_ids),
                          (("--since", older[:10]), all_ids),
                          (("--since", (now + timedelta(days=1)).date().isoformat()), ["bbbb", "dddd", "eeee"])):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual((result.returncode, result.stderr), (0, ""))
                rows = [line.split("\t") for line in result.stdout.splitlines()]
                self.assertEqual([row[0] for row in rows], ids)
                self.assertEqual([(row[1], row[-1]) for row in rows if row[0] in ("dddd", "eeee")],
                                 [("approved", "open"), ("publish_failed", "open")])
                for marker in CANARIES:
                    self.assertNotIn(marker, result.stdout)
        missing = subprocess.run([sys.executable, "-B", str(SCRIPT)], capture_output=True, text=True, timeout=15)
        for result in (missing, self.cli("--since", "2025-02-30"), self.cli("--since", "20250101"),
                       self.cli("--unknown")):
            self.assertEqual((result.returncode, result.stdout), (2, ""))
            self.assertIn("usage:", result.stderr)


if __name__ == "__main__":
    unittest.main()
