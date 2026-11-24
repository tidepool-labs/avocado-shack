"""Offline CLI contracts for the copied stores' release-defined primary keys."""

from contextlib import closing, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hass.inbox import Inbox
from hass.relay import RelayStore

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_keys_preflight.py"


class InstallKeysPreflightTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def store(self, name):
        root = self.root / name
        root.mkdir(mode=0o700)
        if name == "inbox":
            Inbox(root, start_at="2026-01-01T00:00:00+00:00").db.close()
        else:
            RelayStore(root).db.close()
        return root / f"{name}.sqlite3"

    def assert_cli(self, store, path, code, mismatches):
        before = {p.name: p.read_bytes() for p in path.parent.iterdir() if p.is_file()}
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--store", store, str(path)],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (code, f"store={store} mismatches={mismatches}\n", ""))
        self.assertEqual({p.name: p.read_bytes() for p in path.parent.iterdir() if p.is_file()}, before)

    def test_exact_keys_on_both_store_copies(self):
        # Known-good copies must qualify for either store, not just the default constructor.
        for name in ("inbox", "relay"):
            with self.subTest(store=name):
                self.assert_cli(name, self.store(name), 0, 0)

    def test_inbox_same_column_shape_without_primary_key(self):
        # A name/type-only comparison misses this hand-built replacement of inbox.meta.
        path = self.store("inbox")
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript("ALTER TABLE meta RENAME TO old_meta;"
                             "CREATE TABLE meta(name TEXT, value TEXT NOT NULL);"
                             "DROP TABLE old_meta;")
        self.assert_cli("inbox", path, 1, 1)

    def test_relay_reversed_composite_key_and_missing_table(self):
        # Comparing sets (or column declaration order) misses the reversed picture key;
        # only comparing shared tables misses the absent receipt key.
        path = self.store("relay")
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript("DROP TABLE picture; DROP TABLE card_receipt;"
                             "CREATE TABLE picture(relay_id INTEGER NOT NULL, idx INTEGER NOT NULL,"
                             " sha256 TEXT NOT NULL, size INTEGER NOT NULL, data BLOB, PRIMARY KEY(idx, relay_id));")
        self.assert_cli("relay", path, 1, 2)

    def test_refuses_unreadable_copy_and_symlink_sidecar(self):
        # Using only the main file would accept the valid DB with the invalid sidecar.
        path = self.store("inbox")
        empty = self.root / "empty"
        empty.touch()
        path.with_name(path.name + "-wal").symlink_to(empty)
        invalid = self.root / "bad.sqlite3"
        invalid.write_bytes(b"synthetic non-database")
        for refused in (path, invalid):
            with self.subTest(copy=refused.name):
                self.assert_cli("inbox", refused, 1, "unknown")

    def test_keyless_reference_does_not_qualify(self):
        # An all() over no reviewed keys must not turn a regression in reference creation into a pass.
        path = self.store("inbox")
        with patch.object(sys, "path", sys.path.copy()):
            from scripts.hass import install_keys_preflight

        def keyless(root, *, start_at):
            db = sqlite3.connect(root / "inbox.sqlite3")
            db.execute("CREATE TABLE sample(name TEXT)")
            return SimpleNamespace(db=db)

        out, err = StringIO(), StringIO()
        with patch("hass.inbox.Inbox", side_effect=keyless), redirect_stdout(out), redirect_stderr(err):
            code = install_keys_preflight.main(["--store", "inbox", str(path)])
        self.assertEqual((code, out.getvalue(), err.getvalue()), (1, "store=inbox mismatches=unknown\n", ""))
