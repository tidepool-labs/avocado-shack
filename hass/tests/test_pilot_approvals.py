"""Fixture-only tests of the read-only pilot approval report."""

import ast
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


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/pilot_approvals.py"
SPEC = importlib.util.spec_from_file_location("pilot_approvals", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)
SOURCE = ast.parse((ROOT / "hass/conversation.py").read_text(encoding="utf-8"))
SCHEMA = next(ast.literal_eval(node.value) for node in SOURCE.body
              if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "SCHEMA"
                                                      for target in node.targets))

CHANGE = "fixture-change"
HASH = "sha256:" + "a" * 64
OLD_HASH = HASH[:-1] + "b"  # Same displayed prefix; compare the entire stored value.
BASE = "sha256:" + "c" * 64
OTHER_BASE = BASE[:-1] + "d"
COMMIT = "e" * 40
CREATED = "2000-01-01T00:00:00+00:00"
PROPOSED = "2000-01-01T00:01:00+00:00"
APPROVED = "2000-01-01T00:02:00+00:00"
EXPIRES = "2000-01-01T00:03:00+00:00"
CHECKED = "2000-01-01T00:04:00+00:00"
PROVIDER = "fixture-provider-private"
PRIVATE = ("fixture-sender-private", "fixture-chat-private", "fixture-summary-private",
           '["fixture-ops-private"]')


class PilotApprovalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db_path = Path(temporary.name) / "fixture ?#%.sqlite"
        with closing(sqlite3.connect(self.db_path)) as db:
            db.executescript(SCHEMA)

    def insert(self, query, params):
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute(query, params)

    def draft(self, draft_hash=HASH, *, change=CHANGE, state="verified", reason=None,
              replaced_by=None, created=CREATED, proposed: str | None = PROPOSED,
              checked: str | None = CHECKED, commit: str | None = COMMIT):
        self.insert('''INSERT INTO drafts(change_id, code, state, reason, replaced_by, draft_hash, base,
                                          sender, chat, summary, ops_json, created_at, proposed_at, checked_at, "commit")
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (change, "fixture-code", state, reason, replaced_by, draft_hash, BASE,
                     *PRIVATE, created, proposed, checked, commit))

    def approve(self, draft_hash=HASH, base=BASE, *, change=CHANGE, approved=APPROVED, expires=EXPIRES):
        self.insert('''INSERT INTO approvals(change_id, draft_hash, base, provider_id, sender, chat, approved_at, expires_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (change, draft_hash, base, PROVIDER, *PRIVATE[:2], approved, expires))

    def args(self, change=CHANGE):
        return ["--db", str(self.db_path), "--change-id", change]

    def run_report(self, *, change=CHANGE):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = REPORT.main(self.args(change))
        return status, out.getvalue().splitlines(), err.getvalue()

    def assert_verdict(self, expected, *, change=CHANGE):
        status, lines, err = self.run_report(change=change)
        self.assertEqual(err, "")
        self.assertEqual(status, 0 if expected == "BOUND" else 1)
        self.assertEqual(lines[-1], expected)
        return lines

    def test_cli_projects_only_the_requested_change_from_a_quoted_path(self):
        # Wrong URI escaping, cross-change joins or wrong field formatting break this receipt.
        self.draft()
        self.approve()
        self.draft(change="unrelated-change", state="failed")
        self.approve(change="unrelated-change")
        before = self.db_path.read_bytes()
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *self.args()],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        provider_digest = sha256(PROVIDER.encode()).hexdigest()[:12]
        self.assertEqual(result.stdout.splitlines(), [
            f'draft state=verified draft_hash={"a" * 12} base={"c" * 12} '
            f'created_at={CREATED} proposed_at={PROPOSED} checked_at={CHECKED} commit={"e" * 12}',
            f'approval draft_hash={"a" * 12} base={"c" * 12} approved_at={APPROVED} '
            f'expires_at={EXPIRES} provider_id_digest={provider_digest}',
            "BOUND",
        ])
        self.assertEqual(self.db_path.read_bytes(), before)
        # ID is a parameter, not SQL or text in the receipt.
        self.assertEqual(self.assert_verdict("NOT-BOUND none", change="fixture-change' OR 1=1 --"),
                         ["NOT-BOUND none"])

    def test_private_columns_are_not_read_even_if_the_output_would_hide_them(self):
        # A SELECT * plus redaction is insufficient, and a writable connection can mutate the store.
        self.draft()
        self.approve()
        real_connect = sqlite3.connect
        reads = []

        def authorize(action, table, column, _db, _trigger):
            if action == sqlite3.SQLITE_READ:
                reads.append((table, column))
                if column in {"sender", "chat", "summary", "ops_json"}:
                    return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        def guarded_connect(*args, **kwargs):
            db = real_connect(*args, **kwargs)
            with self.assertRaisesRegex(sqlite3.OperationalError, "readonly"):
                db.execute("DELETE FROM drafts")
            db.rollback()
            db.set_authorizer(authorize)
            return db

        with patch.object(REPORT.sqlite3, "connect", guarded_connect):
            status, lines, err = self.run_report()
        self.assertEqual((status, lines[-1], err), (0, "BOUND", ""))
        self.assertIn(("drafts", "draft_hash"), reads)
        self.assertIn(("approvals", "provider_id"), reads)
        for private in (*PRIVATE, PROVIDER, CHANGE, HASH, BASE, COMMIT):
            self.assertNotIn(private, "\n".join(lines) + err)

    def test_old_approval_cannot_match_on_displayed_prefix_or_timestamp_order(self):
        # Latest means highest row_id, even when a later draft has an earlier clock value.
        self.draft(OLD_HASH, created=PROPOSED)
        self.draft(state="proposed", checked=None, commit=None)
        self.approve(OLD_HASH)
        lines = self.assert_verdict("NOT-BOUND hash-mismatch")
        self.assertEqual(len(lines), 4)
        self.assertIn("state=proposed", lines[1])
        self.assertTrue(lines[1].endswith("checked_at=- commit=-"))

    def test_skips_replaced_rows_but_reports_them_and_keeps_plain_rejections(self):
        # A replacement can be failed with a replacement code, or rejected as revised.
        # A rejected row without either marker still represents the stored draft.
        self.draft(state="rejected")
        self.draft(OLD_HASH, state="failed", replaced_by="fixture-new-code")
        self.draft(OLD_HASH, state="rejected", reason="revised")
        self.approve()
        lines = self.assert_verdict("BOUND")
        self.assertEqual(len(lines), 5)

    def test_approval_without_unreplaced_version_is_a_hash_mismatch(self):
        # Neither a dangling approval nor a superseded matching row supplies a candidate.
        self.approve()
        self.assert_verdict("NOT-BOUND hash-mismatch")
        self.draft(state="rejected", replaced_by="fixture-replacement-code")
        self.assert_verdict("NOT-BOUND hash-mismatch")

    def test_wrong_base_cannot_match_on_displayed_prefix(self):
        # Looking only at the hash or comparing the printed base would accept this row.
        self.draft()
        self.approve(base=OTHER_BASE)
        self.assert_verdict("NOT-BOUND base-mismatch")

    def test_two_approvals_are_multiple_even_when_both_match(self):
        # Taking only the newest row or deduplicating the two approvals would bind them.
        self.draft()
        self.approve()
        self.approve()
        lines = self.assert_verdict("NOT-BOUND multiple")
        self.assertEqual(len([line for line in lines if line.startswith("approval ")]), 2)

    def test_yes_before_proposal_not_bound(self):
        # Matching hashes and an unexpired yes are insufficient: use the selected draft's
        # proposal, not its creation or a replaced row's proposal, and compare instants.
        for change, approved, replaced_proposed, expected in (
            ("early", CREATED, CREATED, (1, "NOT-BOUND before-proposal")),
            ("equal", "1999-12-31T19:01:00-05:00", CHECKED, (0, "BOUND")),
        ):
            with self.subTest(change=change):
                self.draft(change=change)
                self.draft(change=change, replaced_by="fixture-replaced", proposed=replaced_proposed)
                self.approve(change=change, approved=approved)
                result = subprocess.run([sys.executable, "-B", str(SCRIPT), *self.args(change)],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.stderr, "")
                self.assertEqual((result.returncode, result.stdout.splitlines()[-1]), expected)

    def test_chronology_requires_a_timezone_on_every_timestamp(self):
        # A missing proposal or naive ISO value must not bind by assuming a timezone.
        for change, proposed, approved, expires in (
            ("missing-proposed", None, APPROVED, EXPIRES),
            ("naive-proposed", PROPOSED[:19], APPROVED, EXPIRES),
            ("naive-approved", PROPOSED, APPROVED[:19], EXPIRES),
            ("naive-expires", PROPOSED, APPROVED, EXPIRES[:19]),
            ("all-naive", PROPOSED[:19], APPROVED[:19], EXPIRES[:19]),
        ):
            with self.subTest(change=change):
                self.draft(change=change, proposed=proposed)
                self.approve(change=change, approved=approved, expires=expires)
                self.assert_verdict("NOT-BOUND invalid-chronology", change=change)

    def test_expiry_is_relative_to_approval_time_not_the_report_clock(self):
        # An approval at expiry is valid; an instant after it isn't, regardless of text order.
        self.draft()
        for approved, expected in (
            (APPROVED, "BOUND"), (EXPIRES, "BOUND"),
            (CHECKED, "NOT-BOUND expired"), ("2000-01-01T00:01:00-01:00", "NOT-BOUND expired"),
        ):
            with self.subTest(approved=approved):
                self.insert("DELETE FROM approvals", ())
                self.approve(approved=approved)
                self.assert_verdict(expected)

    def test_no_approval_is_none_even_if_draft_exists(self):
        # A draft in a terminal state is not itself evidence of approval.
        self.draft()
        self.assert_verdict("NOT-BOUND none")

    def test_missing_store_is_not_created_or_echoed(self):
        # A default SQLite connection creates a missing file before the first query.
        self.db_path.unlink()
        status, lines, err = self.run_report()
        self.assertEqual(status, 1)
        self.assertEqual(lines, [])
        self.assertEqual(err, "error: could not read pilot approval binding\n")
        self.assertFalse(self.db_path.exists())
