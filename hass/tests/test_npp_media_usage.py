"""Exercise the offline CLI with disposable media and SQLite fixtures only."""

from contextlib import closing, redirect_stderr, redirect_stdout
import hashlib
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

from hass.npp.receipt import RECEIPT_MAX


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_media_usage.py"
SPEC = importlib.util.spec_from_file_location("npp_media_usage", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
usage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(usage)

JOB = "faac0001"
FOLDER_ONLY = "faac0002"
ROW_ONLY = "faac0003"
PNG = b"\x89PNG\r\n\x1a\nsynthetic-card-payload"
STORE = "conversation.sqlite3"
PASS = "PASS npp_media_usage"
FAIL = "FAIL npp_media_usage"


class NppMediaUsageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.media = self.root / "media-copy-canary"
        self.media.mkdir()
        self.npp = self.media / "npp"
        self.npp.mkdir()
        self.state = self.root / "state-copy-canary"
        self.state.mkdir()
        self.store = self.state / STORE
        self.scratch = self.root / "snapshot-parent"
        self.scratch.mkdir()

    def invoke(self, *args, **env):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *map(str, args)],
            cwd=self.root, capture_output=True, text=True, timeout=10,
            env={**os.environ, "TMPDIR": str(self.scratch), **env},
        )
        return result.returncode, result.stdout.splitlines(), result.stderr

    def report(self, *, state=False, **env):
        extra = ("--state", self.state) if state else ()
        return self.invoke("--media", self.media, *extra, **env)

    def assert_report(self, result, code, last):
        actual_code, lines, stderr = result
        self.assertEqual(stderr, "")
        self.assertEqual(actual_code, code)
        self.assertTrue(lines)
        self.assertEqual(lines[-1], last)
        self.assertEqual(lines.count("deletes 0"), 1)
        return lines

    def assert_finding(self, result, *findings):
        lines = self.assert_report(result, 1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         [f"FAIL {reason}" for reason in findings])
        return lines

    def folder(self, job_id=JOB):
        path = self.npp / job_id
        path.mkdir()
        return path

    def card(self, folder, data=PNG, *, digest=None):
        path = folder / f"card-{digest or hashlib.sha256(data).hexdigest()}.png"
        path.write_bytes(data)
        return path

    def create_store(self, *job_ids, wal=False):
        with closing(sqlite3.connect(self.store)) as db, db:
            if wal:
                db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE npp_jobs (job_id TEXT PRIMARY KEY)")
            db.executemany("INSERT INTO npp_jobs VALUES (?)", [(job,) for job in job_ids])

    def input_snapshot(self):
        snapshot = {}
        for root in (self.media, self.state):
            for path in (root, *root.rglob("*")):
                snapshot[path] = (path.lstat().st_mtime_ns,
                                  path.read_bytes() if path.is_file() else None)
        return snapshot

    def test_c1_full_pass(self):
        # Full CLI report: folder counts aren't row counts, and both join directions matter.
        folder = self.folder()
        receipt = b'{"fixture":true}\n'
        (folder / "receipt.json").write_bytes(receipt)
        self.card(folder)
        (folder / "staging").mkdir()
        self.folder(FOLDER_ONLY)
        (self.npp / "unrelated-file").touch()
        (self.npp / "faac0005").symlink_to(folder, target_is_directory=True)
        self.create_store(JOB, ROW_ONLY, "faac0004")
        counts = ["jobs 2", "receipts 1", "cards 1", f"bytes {len(receipt) + len(PNG)}",
                  "note no-receipt 1", "note other-names 2"]
        self.assertEqual(self.assert_report(self.report(), 0, PASS),
                         counts + ["deletes 0", PASS])
        self.assertEqual(self.assert_report(self.report(state=True), 0, PASS),
                         counts + ["note folder-without-job 1", "note job-without-folder 2",
                                   "deletes 0", PASS])

    def test_c2_1_no_npp_dir(self):
        # An absent subtree is not a successful empty scan.
        self.npp.rmdir()
        self.assert_finding(self.report(), "no-npp-dir")

    def test_c2_2_unsafe_npp_dir(self):
        # is_dir/exists alone would admit directory links or misclassify dangling links.
        self.npp.rmdir()
        self.npp.write_bytes(b"not a directory")
        self.assert_finding(self.report(), "unsafe-npp-dir")
        self.npp.unlink()
        self.npp.symlink_to(self.state, target_is_directory=True)
        self.assert_finding(self.report(), "unsafe-npp-dir")
        self.npp.unlink()
        self.npp.symlink_to(self.root / "missing-target", target_is_directory=True)
        self.assert_finding(self.report(), "unsafe-npp-dir")
        media_link = self.root / "media-link"
        media_link.symlink_to(self.media, target_is_directory=True)
        self.assert_finding(self.invoke("--media", media_link), "unsafe-npp-dir")
        plain_file = self.root / "plain-file"
        plain_file.touch()
        self.assert_finding(self.invoke("--media", plain_file), "unsafe-npp-dir")

    def test_c2_3_bad_artifact(self):
        # Named receipts count even when invalid; only regular files contribute bytes.
        malformed = b"[]"
        oversized = b" " * (RECEIPT_MAX + 1)
        (self.folder() / "receipt.json").write_bytes(malformed)
        (self.folder(FOLDER_ONLY) / "receipt.json").write_bytes(oversized)
        (self.folder(ROW_ONLY) / "receipt.json").mkdir()
        folder = self.folder("faac0004")
        target = self.root / "valid-receipt"
        target.write_bytes(b"{}")
        (folder / "receipt.json").symlink_to(target)
        lines = self.assert_finding(self.report(), "bad-artifact 4")
        self.assertIn("note no-receipt 0", lines)
        self.assertIn("receipts 4", lines)
        self.assertIn(f"bytes {len(malformed) + len(oversized)}", lines)

    def test_c2_4_not_sqlite(self):
        # Do not create a missing store, accept a broken schema, or follow a store/sidecar link.
        reason = f"not-sqlite {STORE}"
        self.assert_finding(self.report(state=True), reason)
        self.assertFalse(self.store.exists())
        self.store.mkdir()
        self.assert_finding(self.report(state=True), reason)
        self.store.rmdir()
        self.store.write_bytes(b"not SQLite")
        self.assert_finding(self.report(state=True), reason)
        self.store.unlink()
        with closing(sqlite3.connect(self.store)) as db:
            db.execute("CREATE TABLE unrelated (job_id TEXT)")
            self.assert_finding(self.report(state=True), reason)
            db.execute("CREATE TABLE npp_jobs (wrong_column TEXT)")
            self.assert_finding(self.report(state=True), reason)
        self.store.unlink()
        self.create_store()
        target = self.root / "original-store"
        self.store.rename(target)
        self.store.symlink_to(target)
        self.assert_finding(self.report(state=True), reason)
        self.store.unlink()
        target.rename(self.store)
        for suffix in ("-wal", "-journal"):
            with self.subTest(suffix=suffix):
                sidecar = self.store.with_name(STORE + suffix)
                sidecar.symlink_to(self.root / "missing-target")
                self.assert_finding(self.report(state=True), reason)
                sidecar.unlink()
                sidecar.mkdir()
                self.assert_finding(self.report(state=True), reason)
                sidecar.rmdir()
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_c2_5_temp_unavailable(self):
        # An ineligible temp parent is not a database error and must not be used.
        self.create_store()
        stdout, stderr = io.StringIO(), io.StringIO()
        before = self.input_snapshot()
        with patch.object(usage, "_temp_candidates", return_value=[self.state, self.store]), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = usage.main(["--media", str(self.media), "--state", str(self.state)])
        self.assert_finding((code, stdout.getvalue().splitlines(), stderr.getvalue()), "temp-unavailable")
        self.assertEqual(self.input_snapshot(), before)

    def test_c3_usage_exit_2(self):
        # Parser errors must not produce either a PASS or a report finding.
        for args in ((), ("--media",), ("--media", self.media, "--unknown", self.state)):
            with self.subTest(args=args):
                code, lines, stderr = self.invoke(*args)
                self.assertEqual(code, 2)
                self.assertEqual(lines, [])  # No last stdout line for usage errors.
                self.assertTrue(stderr.splitlines()[-1].startswith("npp_media_usage.py: error:"))
                self.assertNotIn(str(self.root), stderr)

    def test_c4_read_only(self):
        # A direct SQLite open of a closed WAL-mode DB can leave transient sidecars.
        (self.folder() / "receipt.json").write_bytes(b"{}\n")
        self.create_store(JOB, wal=True)
        before = self.input_snapshot()
        lines = self.assert_report(self.report(state=True), 0, PASS)
        self.assertIn("note folder-without-job 0", lines)
        self.assertEqual(self.input_snapshot(), before)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_c5_no_private_values(self):
        # Exercise names, contents, and both success and error reporting, not just receipt parsing.
        payload = {"message": "canary-message-fixture", "chat": "canary-chat-fixture",
                   "sender": "canary-sender-fixture"}
        folder = self.folder()
        receipt = folder / "receipt.json"
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        card = self.card(folder)
        other = "canary-other-name-fixture"
        (folder / other).touch()
        with closing(sqlite3.connect(self.store)) as db, db:
            db.execute("CREATE TABLE npp_jobs (job_id TEXT, chat TEXT, sender TEXT)")
            db.execute("INSERT INTO npp_jobs VALUES (?, ?, ?)", (ROW_ONLY, payload["chat"], payload["sender"]))
        passed = self.report(state=True)
        self.assert_report(passed, 0, PASS)
        receipt.write_bytes(b"[" + receipt.read_bytes() + b"]")
        self.store.write_text(payload["message"], encoding="utf-8")
        failed = self.report(state=True)
        self.assert_finding(failed, "bad-artifact 1", f"not-sqlite {STORE}")
        for _, lines, stderr in (passed, failed):
            streams = "\n".join(lines) + stderr
            for canary in (*payload.values(), JOB, ROW_ONLY, card.name[5:-4], other,
                           str(self.media), str(self.state), str(self.root)):
                self.assertNotIn(canary, streams)

    def test_c6_bad_card_counted(self):
        # A wrong hash fails validation but still takes up media space.
        self.card(self.folder(), digest=hashlib.sha256(PNG + b"different").hexdigest())
        lines = self.assert_finding(self.report(), "bad-artifact 1")
        self.assertIn("jobs 1", lines)
        self.assertIn("cards 1", lines)
        self.assertIn(f"bytes {len(PNG)}", lines)

    def test_c7_wal_rows_counted(self):
        # Copy the committed frames while the writer is still open; don't copy its SHM.
        self.folder()
        writer = self.root / "writer.sqlite3"
        with closing(sqlite3.connect(writer)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA wal_autocheckpoint=0")
            db.execute("CREATE TABLE npp_jobs (job_id TEXT)")
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
            base = writer.read_bytes()
            db.execute("INSERT INTO npp_jobs VALUES (?)", (JOB,))
            db.commit()
            self.assertEqual(writer.read_bytes(), base)
            shutil.copyfile(writer, self.store)
            wal = writer.with_name(writer.name + "-wal")
            self.assertGreater(wal.stat().st_size, 0)
            shutil.copyfile(wal, self.state / (STORE + "-wal"))
        for shm_present in (False, True):
            with self.subTest(shm_present=shm_present):
                if shm_present:
                    # Even a non-file SHM entry must be ignored, not validated or copied.
                    (self.state / (STORE + "-shm")).mkdir()
                before = self.input_snapshot()
                lines = self.assert_report(self.report(state=True), 0, PASS)
                self.assertIn("note folder-without-job 0", lines)
                self.assertIn("note job-without-folder 0", lines)
                self.assertEqual(self.input_snapshot(), before)

    def test_c8_tmpdir_inside_input(self):
        # A write-then-remove during temp probing still changes an input directory's mtime.
        self.folder()
        self.create_store(JOB)
        nested = self.media / "nested"
        nested.mkdir()
        alias = self.root / "nested-alias"
        alias.symlink_to(nested, target_is_directory=True)
        before = self.input_snapshot()
        for candidate in (self.state, nested, alias):
            with self.subTest(candidate=candidate.name):
                result = self.report(state=True, TMPDIR=str(candidate), TEMP=str(self.scratch))
                lines = self.assert_report(result, 0, PASS)
                self.assertIn("note folder-without-job 0", lines)
                self.assertEqual(self.input_snapshot(), before)
                self.assertEqual(list(self.scratch.iterdir()), [])
