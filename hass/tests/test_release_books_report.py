"""Temporary-copy fixtures for the offline release books CLI contract."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/release_books_report.py"
PASS = "PASS release_books_report"
FAIL = "FAIL release_books_report"
DAY = "2040-01-02"
NEXT_DAY = "2040-01-03"
STAMP = DAY + "T09:00:00-08:00"
RETRY = NEXT_DAY + "T09:00:00-08:00"


def change_id(seq):
    return f"chg-{seq:012x}"


def site_sha(seq):
    return f"{seq:040x}"


class ReleaseBooksReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="synthetic-release-copy-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve() / "books"
        self.root.mkdir()
        self.releases = self.root / "releases"
        self.anchor = self.root / "publish.json"

    def write(self, path, data):
        path.write_text(json.dumps(data), encoding="utf-8")
        path.chmod(0o600)

    def write_anchor(self, seq=0):
        self.write(self.anchor, dict(anchor_seq=seq, anchor_at=STAMP,
                                     anchor_site_commit=site_sha(seq), anchor_build_today=None))

    def journal(self, seq, state="intent", kind="change", orig=None, today=DAY,
                before=None, attempts=None, name=None):
        self.releases.mkdir(exist_ok=True)
        record = dict(change_id=change_id(seq), code=f"canary{seq}", kind=kind, orig=orig,
                      chat="fixture-chat-marker", draft_hash="fixture-draft-marker",
                      writer_before="a" * 40, site_before=site_sha(seq - 1 if before is None else before),
                      seq=seq, today=today, at=STAMP, state=state, notified=[],
                      push_attempts=[] if attempts is None else attempts)
        if state in {"live", "unconfirmed", "unknown"}:
            record.update(site_commit=site_sha(seq), writer_after="b" * 40,
                          manifest={"fixture/manifest-marker": "c" * 64})
            if attempts is None:
                record["push_attempts"] = [STAMP]
        self.write(self.releases / (name or f"{record['change_id']}.json"), record)
        return record

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root.parent,
                              capture_output=True, text=True, timeout=10)

    def run_report(self, status=0, *reasons, books=None):
        result = self.cli("--books", str(self.root if books is None else books))
        self.assertEqual(result.returncode, status, (result.stdout, result.stderr))
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], PASS if status == 0 else FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         [f"FAIL {reason}" for reason in reasons])
        return lines

    def test_c1_full_pass(self):
        # Count one pushed journal per shop day, not individual attempts or just landed states.
        self.write_anchor(seq=1)
        self.journal(4, "unknown", today=NEXT_DAY)
        self.journal(1, "live", attempts=[STAMP, RETRY])
        self.journal(3, "unconfirmed", "undo", orig=change_id(99), before=1)
        self.journal(2, "closed", "baseline")
        self.journal(5)
        self.assertEqual(self.run_report(), [
            "journals 5", "state closed 1", "state intent 1", "state live 1",
            "state unconfirmed 1", "state unknown 1", "kind change 3", "kind undo 1",
            "kind baseline 1", "open 3", "unconfirmed 2", f"pushed-day {DAY} 2",
            f"pushed-day {NEXT_DAY} 1", "note undo-orig-missing 1", PASS,
        ])

    def test_c1_books_absent_and_anchor_only(self):
        # No books is not an error and is distinct from an anchor with zero journals.
        self.assertEqual(self.run_report(), ["books absent", PASS])
        self.write_anchor()
        self.assertEqual(self.run_report(), ["journals 0", "open 0", "unconfirmed 0",
                                            "note undo-orig-missing 0", PASS])

    def test_c2_1_unsafe_books(self):
        # Following directory symlinks, or treating a dangling link as absent, can falsely pass.
        alias = self.root.parent / "directory-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        file = self.root.parent / "not-a-directory"
        file.touch()
        missing = self.root.parent / "missing-directory"
        for path in (alias, file, missing):
            with self.subTest(books=path.name):
                self.run_report(1, "unsafe-books", books=path)
        self.releases.touch()
        self.run_report(1, "unsafe-books")
        other = self.root.parent / "other-books"
        other.mkdir()
        releases_alias = other / "releases"
        releases_alias.symlink_to(missing, target_is_directory=True)
        self.run_report(1, "unsafe-books", books=other)
        missing.mkdir()
        self.run_report(1, "unsafe-books", books=other)

    def test_c2_2_bad_journal(self):
        # Count read, schema and filename failures once each; do not stop at the first.
        self.write_anchor()
        self.journal(1)
        self.journal(2, name="mismatched.json")
        self.write(self.releases / f"{change_id(3)}.json", {})
        broken = self.releases / "not-a-journal.txt"
        broken.write_bytes(b"not JSON")
        broken.chmod(0o600)
        self.run_report(1, "bad-journal 3")

    def test_c2_3_anchor_missing(self):
        # Even an empty releases directory needs an anchor; errors can coexist.
        self.releases.mkdir()
        self.run_report(1, "anchor-missing")
        self.write(self.releases / "not-a-journal.json", {})
        self.run_report(1, "bad-journal 1", "anchor-missing")

    def test_c2_4_books_inconsistent(self):
        # An individually valid row with a sequence gap is not a consistent book.
        self.journal(2)
        self.write_anchor()
        self.run_report(1, "books-inconsistent")
        # A valid anchor payload at the wrong mode is refused even without the gap.
        self.write_anchor(seq=1)
        self.anchor.chmod(0o644)
        self.run_report(1, "books-inconsistent")

    def test_c2_5_undone_twice(self):
        # Count distinct original IDs, not all live undo rows or extra attempts.
        self.write_anchor()
        self.journal(1, "live")
        for seq in (2, 3, 4, 5, 6):
            orig = change_id(1 if seq < 5 else 99)
            self.journal(seq, "live", "undo", orig=orig)
        lines = self.run_report(1, "undone-twice 2")
        self.assertIn("note undo-orig-missing 2", lines)

    def test_c3_usage_exit_2(self):
        # Usage failures don't become report findings or echo a private path argument.
        for args in ((), ("--books", str(self.root), "--typo", str(self.root)),
                     ("--books", ""), ("--books",)):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last line on usage errors.
                self.assertTrue(result.stderr.startswith("usage:"))
                self.assertNotIn(str(self.root), result.stderr)

    def test_c4_read_only(self):
        # Accidentally using the live writer can make a lock, replace or touch an input.
        self.write_anchor()
        self.journal(1, "live")
        self.write(self.root / "unrelated.json", {"untouched": True})

        def snapshot():
            return {p.relative_to(self.root): (p.stat().st_mtime_ns,
                                              p.read_bytes() if p.is_file() else None)
                    for p in [self.root, *self.root.rglob("*")]}

        before = snapshot()
        self.run_report()
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Both summaries and errors must redact records and absolute input paths.
        self.write_anchor()
        record = self.journal(1, "live")
        journal_path = self.releases / f"{record['change_id']}.json"
        canaries = [str(p) for p in (self.root, self.releases, self.anchor, journal_path)]
        canaries += [record[k] for k in ("code", "chat", "change_id", "draft_hash",
                                         "site_before", "site_commit", "writer_before", "writer_after")]
        canaries += list(record["manifest"])
        for mode, code, last in ((0o600, 0, PASS), (0o644, 1, FAIL)):
            journal_path.chmod(mode)
            result = self.cli("--books", str(self.root))
            self.assertEqual(result.returncode, code)
            self.assertEqual(result.stdout.splitlines()[-1], last)
            for canary in canaries:
                self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_temp_skipped(self):
        # A corrupt atomic temp file must not be validated or counted as a journal.
        self.write_anchor()
        self.journal(1)
        (self.releases / ".release-fixture").write_bytes(b"partial write")
        self.assertIn("journals 1", self.run_report())

    def test_c7_mode_rule(self):
        # A valid but broadly readable copy cannot bypass the journal reader.
        self.write_anchor()
        self.journal(1)
        (self.releases / f"{change_id(1)}.json").chmod(0o644)
        self.run_report(1, "bad-journal 1")

    def test_c8_one_live_undo_ok(self):
        # A landed but unconfirmed undo must not be counted as a second live undo.
        self.write_anchor()
        self.journal(1, "live")
        self.journal(2, "live", "undo", orig=change_id(1))
        self.journal(3, "unconfirmed", "undo", orig=change_id(1))
        lines = self.run_report()
        self.assertIn("kind undo 2", lines)
        self.assertIn("note undo-orig-missing 0", lines)
