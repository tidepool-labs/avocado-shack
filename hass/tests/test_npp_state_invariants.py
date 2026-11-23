"""Exercise the counts-only NPP report on synthetic conversation snapshots."""

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

from hass import conversation
from hass.npp import job


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_state_invariants.py"
SPEC = importlib.util.spec_from_file_location("npp_state_invariants", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)

STORE = "conversation.sqlite3"
TOTALS = ["jobs 2", "open 1", "versions 1", "approvals 1"]
PASS = "PASS npp_state_invariants"
FAIL = "FAIL npp_state_invariants"
NOT_SQLITE = "not-sqlite conversation.sqlite3"
PUBLISHED = "synthetic-published-job-id"
ASKING = "synthetic-asking-job-id"
CHAT = "synthetic-private-chat"
SENDER = "synthetic-private-sender"
MESSAGE = "synthetic private draft message"
PHOTO, LISTING, DRAFT, CARD = (digit * 64 for digit in "abcd")
WHEN = "2000-01-01T00:00:00+00:00"


class NppStateInvariantsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / "synthetic-private-state"
        self.state.mkdir()
        self.store = self.state / STORE
        self.scratch = self.root / "outside-state"
        self.scratch.mkdir()

    def schema(self):
        self.write(conversation.SCHEMA + job.SCHEMA)

    def write(self, sql):
        with closing(sqlite3.connect(self.store)) as db:
            db.executescript(sql)

    def clean_jobs(self):
        self.schema()
        with closing(sqlite3.connect(self.store)) as db, db:
            db.executemany("""
                INSERT INTO npp_jobs (job_id, chat, sender, photo_sha, open_request_id, state, created_at,
                                      closed_at, current_version, approval_row)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [(PUBLISHED, CHAT, SENDER, PHOTO, 1, "published", WHEN, WHEN, 1, 27),
                  (ASKING, CHAT, SENDER, PHOTO, 2, "asking", WHEN, None, None, None)])
            db.execute("""
                INSERT INTO drafts (row_id, code, state, draft_hash, ops_json, summary, sender, chat, created_at)
                VALUES (27, ?, 'published', ?, '[]', ?, ?, ?, ?)
            """, (PUBLISHED, DRAFT, MESSAGE, SENDER, CHAT, WHEN))
            db.execute("""
                INSERT INTO npp_versions (job_id, n, segment_id, listing_json, listing_sha, patch_json,
                                          draft_hash, card_png_sha, outbox_id, state, delivered_at)
                VALUES (?, 1, 1, '{}', ?, '{}', ?, ?, 41, 'approved', ?)
            """, (PUBLISHED, LISTING, DRAFT, CARD, WHEN))
            db.execute("INSERT INTO npp_approvals (approval_id, job_id, n, outbox_id) VALUES (11, ?, 1, 41)",
                       (PUBLISHED,))
            db.executemany("""
                INSERT INTO npp_questions (job_id, qid, asked_outbox_id, asked_at, state)
                VALUES (?, ?, 42, ?, 'asked')
            """, [(ASKING, qid, WHEN) for qid in ("fixture-q-one", "fixture-q-two")])

    def run_cli(self, *args, tmpdir=None):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            env={**os.environ, "TMPDIR": str(tmpdir or self.scratch), "TEMP": str(self.scratch)},
            capture_output=True, text=True, timeout=10,
        )

    def invoke(self, **kwargs):
        return self.run_cli("--state", str(self.state), **kwargs)

    def assert_report(self, result, totals, *reasons):
        self.assertEqual(result.returncode, int(bool(reasons)), result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), [*totals, *(f"FAIL {reason}" for reason in reasons),
                                                      FAIL if reasons else PASS])

    def state_contents(self):
        contents: dict[Path, tuple[int, bytes | None]] = {self.state: (self.state.stat().st_mtime_ns, None)}
        for path in self.state.rglob("*"):
            contents[path] = (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
        return contents

    def test_c1_full_pass(self):
        # An initialized but empty pipeline is not a missing schema or a finding.
        self.schema()
        self.assert_report(self.invoke(), ["jobs 0", "open 0", "versions 0", "approvals 0"])

    def test_c2_1_no_state(self):
        # Do not create a missing store or follow a symlinked state argument.
        self.assert_report(self.invoke(), [], "no-state")
        self.schema()
        alias = self.root / "state-alias"
        alias.symlink_to(self.state, target_is_directory=True)
        for state in (f"{alias}/", str(self.store)):
            with self.subTest(state_kind="symlink" if state.endswith("/") else "file"):
                self.assert_report(self.run_cli("--state", state), [], "no-state")

    def test_c2_2_no_npp_tables(self):
        # A pre-NPP conversation database is valid SQLite, not corrupt.
        self.write(conversation.SCHEMA)
        self.assert_report(self.invoke(), [], "no-npp-tables")

    def test_c2_3_approval_undelivered(self):
        # Detect both a present-but-undelivered version and an absent version.
        self.clean_jobs()
        self.write("UPDATE npp_versions SET delivered_at = NULL")
        self.write("INSERT INTO npp_approvals SELECT 12, job_id, 2, outbox_id, NULL FROM npp_approvals")
        self.assert_report(self.invoke(), [*TOTALS[:3], "approvals 2"], "approval-undelivered 2")

    def test_c2_4_approval_outbox_mismatch(self):
        # SQL != would miss a NULL outbox on the existing version.
        self.clean_jobs()
        for value in ("49", "NULL"):
            with self.subTest(value=value):
                self.write(f"UPDATE npp_versions SET outbox_id = {value}")
                self.assert_report(self.invoke(), TOTALS, "approval-outbox-mismatch 1")

    def test_c2_5_approval_row_dangling(self):
        # The approval ID exists but is not the conversation draft key.
        self.clean_jobs()
        self.write("UPDATE npp_jobs SET approval_row = 11 WHERE approval_row = 27")
        self.assert_report(self.invoke(), TOTALS, "approval-row-dangling 1")
        # All non-NULL links are dangling without drafts; NULL still is not a link.
        self.write("UPDATE npp_jobs SET approval_row = 27 WHERE approval_row = 11; DROP TABLE drafts;")
        self.assert_report(self.invoke(), TOTALS, "approval-row-dangling 1")
        self.write("UPDATE npp_jobs SET approval_row = NULL")
        self.assert_report(self.invoke(), TOTALS)

    def test_c2_6_current_version_missing(self):
        # An existing version number on another job must not satisfy the check.
        self.clean_jobs()
        self.write("UPDATE npp_jobs SET current_version = 1 WHERE state = 'asking'")
        self.assert_report(self.invoke(), TOTALS, "current-version-missing 1")

    def test_c2_7_delivered_without_card(self):
        # A recorded delivery does not imply the card SHA was stored.
        self.clean_jobs()
        self.write("UPDATE npp_versions SET card_png_sha = NULL")
        self.assert_report(self.invoke(), TOTALS, "delivered-without-card 1")

    def test_c2_8_approved_without_draft(self):
        # A valid conversation draft link cannot replace the version's hash.
        self.clean_jobs()
        self.write("UPDATE npp_versions SET draft_hash = NULL")
        self.assert_report(self.invoke(), TOTALS, "approved-without-draft 1")

    def test_c2_9_over_two_questions(self):
        # Count offending replies, not excess questions or groups by job.
        self.clean_jobs()
        with closing(sqlite3.connect(self.store)) as db, db:
            db.executemany("INSERT INTO npp_questions VALUES (?, ?, ?, ?, NULL, NULL, 'asked')",
                           [(PUBLISHED, "fixture-q-three", 42, WHEN)]
                           + [(ASKING, f"fixture-extra-{i}", 43, WHEN) for i in range(4)])
        self.assert_report(self.invoke(), TOTALS, "over-two-questions 2")

    def test_c2_10_state_closed_mismatch(self):
        # Closing an active job and leaving an inactive job open are both wrong.
        self.clean_jobs()
        self.write("UPDATE npp_jobs SET state = CASE state WHEN 'asking' THEN 'published' ELSE 'working' END")
        self.assert_report(self.invoke(), TOTALS, "state-closed-mismatch 2")

    def test_c2_11_not_sqlite(self):
        # A corrupt store, schema drift, or unsafe input must not masquerade as empty.
        self.store.write_bytes(b"not a database")
        self.assert_report(self.invoke(), [], NOT_SQLITE)
        self.store.unlink()
        self.clean_jobs()
        for suffix in ("-wal", "-journal", ""):
            with self.subTest(suffix=suffix):
                path = self.state / (STORE + suffix)
                saved = self.root / "saved-store"
                if not suffix:
                    path.rename(saved)
                path.symlink_to(saved)
                self.assert_report(self.invoke(), [], NOT_SQLITE)
                path.unlink()
                if not suffix:
                    saved.rename(path)
        self.write("ALTER TABLE drafts RENAME COLUMN row_id TO wrong_key")
        self.assert_report(self.invoke(), [], NOT_SQLITE)
        self.write("ALTER TABLE drafts RENAME COLUMN wrong_key TO row_id; DROP TABLE npp_questions;")
        self.assert_report(self.invoke(), [], NOT_SQLITE)

    def test_c2_12_temp_unavailable(self):
        # With no eligible parent, never fall through to a default temp probe.
        self.clean_jobs()
        alias = self.root / "temp-alias"
        alias.symlink_to(self.state, target_is_directory=True)
        before = self.state_contents()
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(CHECKER, "_temp_candidates", return_value=[alias, self.root / "missing"]), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = CHECKER.main(["--state", str(self.state)])
        self.assert_report(subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue()),
                           [], "temp-unavailable")
        self.assertEqual(self.state_contents(), before)

    def test_c3_usage_exit_2(self):
        # Argument errors must not print a report or reflect an unknown argument.
        for args in ((), ("--state",), ("--state", str(self.state), f"--unknown={self.state}")):
            with self.subTest(arg_count=len(args)):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)
                self.assertNotIn(str(self.state), result.stderr)

    def test_c4_read_only(self):
        # A direct open can create WAL/SHM files even when just reading.
        self.clean_jobs()
        self.write("PRAGMA journal_mode=WAL")
        sidecar = self.state / (STORE + "-shm")
        sidecar.symlink_to(self.root / "nonexistent-shm-target")
        before = self.store.read_bytes(), self.store.stat().st_mtime_ns, self.state.stat().st_mtime_ns
        self.assert_report(self.invoke(), TOTALS)
        self.assertEqual(before, (self.store.read_bytes(), self.store.stat().st_mtime_ns,
                                  self.state.stat().st_mtime_ns))
        self.assertEqual(set(self.state.iterdir()), {self.store, sidecar})
        self.assertEqual(sidecar.readlink(), self.root / "nonexistent-shm-target")
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_c5_no_private_values(self):
        # Diagnosing multiple faults must not emit stored values or input paths.
        self.clean_jobs()
        self.write("UPDATE npp_versions SET delivered_at = NULL, outbox_id = 49")
        result = self.invoke()
        self.assert_report(result, TOTALS, "approval-undelivered 1", "approval-outbox-mismatch 1")
        for canary in (PUBLISHED, ASKING, CHAT, SENDER, MESSAGE, PHOTO, LISTING, DRAFT, CARD, str(self.state)):
            self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_clean_jobs_pass(self):
        # Regression guard for confusing draft row 27 with approval ID 11.
        self.clean_jobs()
        result = self.invoke()
        self.assert_report(result, TOTALS)
        self.assertNotIn("approval-row-dangling", result.stdout)

    def test_c7_wal_rows_counted(self):
        # Copy committed frames while the writer still holds the WAL; omit SHM.
        self.clean_jobs()
        wal = self.state / (STORE + "-wal")
        snapshot = self.root / "wal-copy"
        snapshot.mkdir()
        with closing(sqlite3.connect(self.store)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
            db.execute("PRAGMA wal_autocheckpoint=0")
            db.execute("""INSERT INTO npp_jobs (job_id, chat, sender, photo_sha, open_request_id, state, created_at)
                          VALUES ('synthetic-wal-only-job', ?, ?, ?, 3, 'asking', ?)""", (CHAT, SENDER, PHOTO, WHEN))
            db.commit()
            bare = self.root / STORE
            shutil.copyfile(self.store, bare)
            with closing(sqlite3.connect(bare)) as without_wal:
                self.assertEqual(without_wal.execute("SELECT COUNT(*) FROM npp_jobs").fetchone(), (2,))
            shutil.copyfile(self.store, snapshot / STORE)
            shutil.copyfile(wal, snapshot / wal.name)
        self.state = snapshot
        before = self.state_contents()
        self.assert_report(self.invoke(), ["jobs 3", "open 2", "versions 1", "approvals 1"])
        self.assertEqual(self.state_contents(), before)

    def test_c8_tmpdir_inside_input(self):
        # A transient tempdir write can leave bytes unchanged; check dir mtimes too.
        self.clean_jobs()
        nested = self.state / "nested"
        nested.mkdir()
        alias = self.root / "temp-alias"
        alias.symlink_to(nested, target_is_directory=True)
        before = self.state_contents()
        for candidate in (self.state, nested, alias):
            with self.subTest(candidate=candidate.name):
                self.assert_report(self.invoke(tmpdir=candidate), TOTALS)
                self.assertEqual(self.state_contents(), before)
                self.assertEqual(list(self.scratch.iterdir()), [])
