"""Offline CLI contract for the Clover journal undo map."""

from contextlib import closing, redirect_stderr, redirect_stdout
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


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/clover_journal_undo_map.py"
PASS = "PASS clover_journal_undo_map"
FAIL = "FAIL clover_journal_undo_map"
SCHEMA = """CREATE TABLE changes(
    code TEXT PRIMARY KEY, draft TEXT, sender TEXT, chat TEXT,
    expires REAL, status TEXT, day TEXT, result TEXT
)"""


def draft(change_id, kind="set_price", **fields):
    return json.dumps({"kind": kind, "change_id": change_id, **fields})


class CloverJournalUndoMapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / "synthetic-private-state"
        self.clover = self.state / "clover"
        self.store = self.clover / "journal.sqlite3"
        self.state.mkdir()

    def seed(self, db, rows):
        db.execute(SCHEMA)
        db.executemany(
            "INSERT INTO changes(code, draft, sender, chat, status) VALUES(?, ?, ?, ?, ?)",
            [(f"synthetic-code-{index}", payload, "synthetic-sender", "synthetic-chat", status)
             for index, (payload, status) in enumerate(rows)],
        )
        db.commit()

    def journal(self, *rows, wal=False):
        self.clover.mkdir()
        with closing(sqlite3.connect(self.store)) as db:
            if wal:
                self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
            self.seed(db, rows)

    def run_cli(self, *args, env=None):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            env=env, capture_output=True, text=True, timeout=10,
        )
        return result.returncode, result.stdout, result.stderr

    def run_report(self, state=None, env=None):
        return self.run_cli("--state", str(self.state if state is None else state), env=env)

    def assert_report(self, result, *expected, success=True):
        status, stdout, stderr = result
        self.assertEqual(status, 0 if success else 1, stderr)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout.splitlines(), [*expected, PASS if success else FAIL])

    def fingerprint(self):
        return {p.relative_to(self.state): (p.stat().st_mtime_ns, None if p.is_dir() else p.read_bytes())
                for p in (self.state, *self.state.rglob("*"))}

    def test_c1_full_pass(self):
        # Catch sorting by count/name, echoing unknown kinds, and counting non-stock/null lookalikes.
        self.journal(
            (draft("hide", "set_hidden", undo_of="create"), "applied"),
            (draft("synthetic-unknown", "synthetic-new-kind"), "applied"),
            (draft("price"), "applied"),
            (draft("nonfirst", "set_stock", before={"stock": "7"}), "applied"),
            (draft("first", "set_stock", undo_of=None, before={"stock": None}), "applied"),
            (draft("stock-undo", "set_stock", undo_of="nonfirst", before={"stock": None}), "applied"),
            (draft("sku", "set_sku", before={"stock": None}), "applied"),
            (draft("create", "create_item"), "applied"),
            (draft("unshaped", "set_stock", before={}), "applied"),
        )
        self.assert_report(
            self.run_report(), "applied 9", "applied-kind create_item 1", "applied-kind set_price 1",
            "applied-kind set_stock 4", "applied-kind set_sku 1", "applied-kind set_hidden 1",
            "applied-kind other 1", "undo-applied 2", "undone 2", "first-count 1",
        )

    def test_c2_1_unsafe_state(self):
        # lstat must refuse each leaf type rather than following links or treating them as absent.
        alias = self.root / "state-alias"
        alias.symlink_to(self.state, target_is_directory=True)
        regular = self.root / "regular-file"
        regular.touch()
        for state in (alias, str(alias) + "/", regular, self.root / "missing"):
            with self.subTest(state=state):
                self.assert_report(self.run_report(state), "FAIL unsafe-state", success=False)
        for location in (self.clover, self.store):
            for symlink in (False, True):
                with self.subTest(location=location.name, symlink=symlink):
                    if symlink:
                        location.symlink_to(self.root / "missing")
                    elif location == self.clover:
                        location.touch()
                    else:
                        location.mkdir()
                    self.assert_report(self.run_report(), "FAIL unsafe-state", success=False)
                    if location.is_symlink() or location.is_file():
                        location.unlink()
                    else:
                        location.rmdir()
            if location == self.clover:
                self.clover.mkdir()

    def test_c2_2_bad_draft(self):
        # Validate all statuses before aggregating; malformed rows cannot rescue an orphan.
        self.journal(
            ("synthetic-invalid-json", "applied"), ("[]", "draft"),
            ('{"kind": 0, "change_id": "bad-target"}', "applied"),
            ('{"kind": "set_price", "change_id": null}', "draft"),
            ('{"kind": "set_price", "change_id": "invalid", "before": NaN}', "applied"),
            (draft("undo", undo_of="bad-target"), "applied"),
        )
        self.assert_report(
            self.run_report(), "applied 1", "applied-kind set_price 1", "undo-applied 1",
            "undone 0", "first-count 0", "FAIL bad-draft 5", "FAIL orphan-undo 1", success=False,
        )

    def test_c2_3_orphan_undo(self):
        # An existing draft target is not orphaned, but cannot count as undone.
        self.journal(
            (draft("draft-target"), "draft"), (draft("known-undo", undo_of="draft-target"), "applied"),
            (draft("orphan-one", undo_of="missing-one"), "applied"),
            (draft("orphan-two", undo_of="missing-two"), "applied"),
            (draft("pending-orphan", undo_of="missing-three"), "draft"),
        )
        self.assert_report(
            self.run_report(), "applied 3", "applied-kind set_price 3", "undo-applied 3",
            "undone 0", "first-count 0", "FAIL orphan-undo 2", success=False,
        )

    def test_c2_4_double_undo(self):
        # Three undos of one original count as one duplicate target, not two extra undos.
        self.journal(
            (draft("target"), "applied"),
            *((draft(f"undo-{index}", undo_of="target"), "applied") for index in range(3)),
        )
        self.assert_report(
            self.run_report(), "applied 4", "applied-kind set_price 4", "undo-applied 3",
            "undone 1", "first-count 0", "FAIL double-undo 1", success=False,
        )

    def test_c2_5_not_sqlite(self):
        # Opening a SQLite file is not enough: prepare the real SELECT and reject unsafe sidecars.
        self.clover.mkdir()
        reason = "FAIL not-sqlite journal.sqlite3"
        self.store.write_bytes(b"synthetic not a database")
        self.assert_report(self.run_report(), reason, success=False)
        for index, schema in enumerate(("CREATE TABLE unrelated(dummy)",
                                        "CREATE TABLE changes(status)",
                                        "CREATE TABLE changes(draft)")):
            with self.subTest(schema=schema):
                state = self.root / f"schema-{index}"
                clover = state / "clover"
                clover.mkdir(parents=True)
                with closing(sqlite3.connect(clover / self.store.name)) as db:
                    db.execute(schema)
                self.assert_report(self.run_report(state), reason, success=False)
        # Use a valid store so these fail at sidecar validation, not SQL preparation.
        with closing(sqlite3.connect(self.root / "valid.sqlite3")) as db:
            self.seed(db, [])
        shutil.copyfile(self.root / "valid.sqlite3", self.store)
        wal = self.store.with_suffix(".sqlite3-wal")
        wal.symlink_to(self.root / "missing")
        self.assert_report(self.run_report(), reason, success=False)
        wal.unlink()
        self.store.with_suffix(".sqlite3-journal").mkdir()
        self.assert_report(self.run_report(), reason, success=False)

    def test_c2_6_temp_unavailable(self):
        # If all candidates are missing or overlap the input, no tempfile fallback is allowed.
        self.journal()
        spec = importlib.util.spec_from_file_location("undo_map", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(module, "_temp_candidates", return_value=[self.root / "missing", self.state]),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            status = module.main(["--state", str(self.state)])
        self.assert_report((status, stdout.getvalue(), stderr.getvalue()), "FAIL temp-unavailable", success=False)

    def test_c3_usage_exit_2(self):
        # Usage errors are argparse failures, not report findings or attempted state reads.
        for args in ((), ("--state",), ("--state", str(self.state), "--unknown")):
            with self.subTest(args=args):
                status, stdout, stderr = self.run_cli(*args)
                self.assertEqual((status, stdout), (2, ""))
                self.assertIn("usage:", stderr)

    def test_c4_read_only(self):
        # Even mode=ro can touch a WAL-mode directory to create SQLite sidecars.
        self.journal((draft("only"), "applied"), wal=True)
        before = self.fingerprint()
        self.assertEqual(set(before), {Path("."), Path("clover"), Path("clover/journal.sqlite3")})
        self.assert_report(self.run_report(), "applied 1", "applied-kind set_price 1",
                           "undo-applied 0", "undone 0", "first-count 0")
        self.assertEqual(self.fingerprint(), before)

    def test_c5_no_private_values(self):
        # Neither error context nor arbitrary journal strings belong in either output stream.
        self.journal(
            (draft("synthetic-change-id", "synthetic-private-kind", undo_of="synthetic-missing-id",
                   label="synthetic-label", lines=["synthetic-preview-line"],
                   before={"stock": "synthetic-before"}, after={"stock": "synthetic-after"}), "applied"),
            ("synthetic-invalid-json", "draft"),
        )
        result = self.run_report()
        self.assert_report(result, "applied 1", "applied-kind other 1", "undo-applied 1", "undone 0",
                           "first-count 0", "FAIL bad-draft 1", "FAIL orphan-undo 1", success=False)
        # Extra positional arguments can otherwise be echoed by argparse.
        usage = self.run_cli("--state", str(self.state), str(self.state))
        self.assertEqual(usage[:2], (2, ""))
        for canary in (
            "synthetic-code-0", "synthetic-change-id", "synthetic-private-kind", "synthetic-missing-id",
            "synthetic-label", "synthetic-preview-line", "synthetic-before", "synthetic-after",
            "synthetic-sender", "synthetic-chat", "synthetic-invalid-json", str(self.state),
        ):
            self.assertNotIn(canary, result[1] + result[2] + usage[1] + usage[2])

    def test_c6_absent_pass(self):
        # An absent Clover directory or absent database needs no initialization.
        self.assert_report(self.run_report(), "journal absent")
        self.assertEqual(list(self.state.iterdir()), [])
        self.clover.mkdir()
        before = self.fingerprint()
        self.assert_report(self.run_report(), "journal absent")
        self.assertEqual(self.fingerprint(), before)

    def test_c7_only_applied_undoes(self):
        # A prepared but unapplied undo must not change either undo total.
        self.journal((draft("target"), "applied"), (draft("pending-undo", undo_of="target"), "draft"))
        self.assert_report(self.run_report(), "applied 1", "applied-kind set_price 1",
                           "undo-applied 0", "undone 0", "first-count 0")

    def test_c8_wal_rows_counted(self):
        # Checkpoint the empty schema, then copy a committed row that exists only in the WAL.
        source = self.root / "wal-source.sqlite3"
        self.clover.mkdir()
        with closing(sqlite3.connect(source)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
            db.execute("PRAGMA wal_autocheckpoint=0")
            self.seed(db, [])
            self.assertEqual(db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0], 0)
            main_bytes = source.read_bytes()
            db.execute("INSERT INTO changes(draft, status) VALUES(?, 'applied')", (draft("wal-only"),))
            db.commit()
            self.assertEqual(source.read_bytes(), main_bytes)
            shutil.copyfile(source, self.store)
            shutil.copyfile(source.with_suffix(".sqlite3-wal"), self.store.with_suffix(".sqlite3-wal"))
        before = self.fingerprint()
        self.assertFalse(self.store.with_suffix(".sqlite3-shm").exists())
        self.assert_report(self.run_report(), "applied 1", "applied-kind set_price 1",
                           "undo-applied 0", "undone 0", "first-count 0")
        self.assertEqual(self.fingerprint(), before)
        # A dangling SHM sidecar must be ignored, not validated or copied.
        shm = self.store.with_suffix(".sqlite3-shm")
        shm.symlink_to(self.root / "missing")
        self.assert_report(self.run_report(), "applied 1", "applied-kind set_price 1",
                           "undo-applied 0", "undone 0", "first-count 0")
        self.assertTrue(shm.is_symlink())

    def test_c9_tmpdir_inside_input(self):
        # Directory mtime catches transient writes from tempfile's own writability probe.
        self.journal()
        nested = self.clover / "nested"
        nested.mkdir()
        alias = self.root / "temp-alias"
        alias.symlink_to(nested, target_is_directory=True)
        fallback = self.root / "fallback"
        fallback.mkdir()
        for temp in (self.state, nested, alias):
            with self.subTest(temp=temp):
                before = self.fingerprint()
                env = {**os.environ, "TMPDIR": str(temp), "TEMP": str(fallback)}
                self.assert_report(self.run_report(env=env), "applied 0", "undo-applied 0", "undone 0",
                                   "first-count 0")
                self.assertEqual(self.fingerprint(), before)
                self.assertEqual(list(fallback.iterdir()), [])
