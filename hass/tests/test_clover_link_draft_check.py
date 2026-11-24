"""Exercise the offline draft check on disposable synthetic state and content."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime
import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hass.clover import links, reads

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/clover_link_draft_check.py"
SPEC = importlib.util.spec_from_file_location("clover_link_draft_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)
PASS = "PASS clover_link_draft_check"
FAIL = "FAIL clover_link_draft_check"
ASOF = "2000-01-01T00:00:00+00:00"
NEW_ASOF = "2000-01-02T00:00:00+00:00"
CODE = "fixture-private-code"
ITEMS = (("fixture-till-a", "Fixture private name A", "fixture-sku-a"),
         ("fixture-till-b", "Fixture private name B", "fixture-sku-b"))
PIDS = ("fixture-site-a", "fixture-site-b")
PAIRS = {pid: {"cloverId": item[0], "sku": item[2]} for pid, item in zip(PIDS, ITEMS)}
CONTENT = {"products": [{"id": pid, "name": item[1], "status": "active"}
                        for pid, item in zip(PIDS, ITEMS)]}


class CloverLinkDraftCheckTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="fixture-draft-check-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.state = self.root / "fixture-state"
        self.state.mkdir()
        self.folder = self.state / "clover"
        self.folder.mkdir(mode=0o700)
        self.content = self.root / "fixture-content"
        self.content.mkdir()
        self.scratch = self.root / "scratch"
        self.scratch.mkdir()
        self.products = self.content / "products.json"
        self.draft = self.folder / links.DRAFT
        self.saved = links.table(self.state)
        self.store = self.folder / "cache.sqlite3"
        self.write_json(self.products, CONTENT)
        self.write_json(self.draft, {"code": CODE, "asOf": ASOF, "pairs": PAIRS})
        with closing(sqlite3.connect(self.store)) as db, db:
            db.executescript("CREATE TABLE items(id TEXT, name TEXT, sku TEXT);"
                             "CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);")
            db.executemany("INSERT INTO items VALUES (?, ?, ?)", ITEMS)
            db.execute("INSERT INTO meta VALUES ('asOf', ?)", (ASOF.replace("+00:00", "Z"),))

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")
        path.chmod(0o600)

    def change_db(self, sql, params=()):
        with closing(sqlite3.connect(self.store)) as db, db:
            db.execute(sql, params)

    def argv(self, state=None, content=None):
        return ["--state", str(state or self.state), "--content", str(content or self.content)]

    def cli(self, argv=None, **env):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *(self.argv() if argv is None else argv)],
                              env={**os.environ, "TMPDIR": str(self.scratch), **env},
                              cwd=self.root, capture_output=True, text=True, timeout=10)

    def in_process(self):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = check.main(self.argv())
        return subprocess.CompletedProcess([], status, stdout.getvalue(), stderr.getvalue())

    def assert_report(self, result, code, *lines):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), [*lines, PASS if code == 0 else FAIL])

    def assert_finding(self, reason, *, pairs=True, argv=None, result=None):
        lines = (["pairs 2"] if pairs else []) + [f"FAIL {reason}"]
        self.assert_report(self.cli(argv) if result is None else result, 1, *lines)

    def input_tree(self):
        # Directory mtimes detect transient files even if cleanup removes them.
        paths = [self.state, self.content, *self.state.rglob("*"), *self.content.rglob("*")]
        return {p: (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None) for p in paths}

    def test_c1_full_pass(self):
        # Missing links are empty; normalize cache ISO form before comparing.
        self.assertFalse(self.saved.exists())
        self.assert_report(self.cli(), 0, "pairs 2", "draft current")

    def test_c2_1_unsafe_state(self):
        # A normal open would follow aliases or trust a shared link table.
        alias = self.root / "alias"
        alias.symlink_to(self.state, target_is_directory=True)
        for state in (alias, self.products, self.root / "missing"):
            with self.subTest(state=state.name):
                self.assert_finding("unsafe-state", pairs=False, argv=self.argv(state=state))
        other = self.root / "other-state"
        other.mkdir()
        other_clover = other / "clover"
        other_clover.symlink_to(self.folder, target_is_directory=True)
        self.assert_finding("unsafe-state", pairs=False, argv=self.argv(state=other))
        other_clover.unlink()
        other_clover.touch()
        self.assert_finding("unsafe-state", pairs=False, argv=self.argv(state=other))
        self.folder.chmod(0o755)
        try:
            self.assert_finding("unsafe-state")
        finally:
            self.folder.chmod(0o700)
        self.saved.symlink_to(self.draft)
        self.assert_finding("unsafe-state")
        self.saved.unlink()
        self.saved.mkdir()
        self.assert_finding("unsafe-state")
        self.saved.rmdir()
        self.write_json(self.saved, {})
        self.saved.chmod(0o640)
        self.assert_finding("unsafe-state")
        self.saved.chmod(0o600)
        with patch.object(check.os, "getuid", return_value=os.getuid() + 1):
            # Isolate the links-file owner check from the clover-folder owner check.
            with patch.object(check.cache, "_private_dir", return_value=True):
                self.assert_finding("unsafe-state", result=self.in_process())
        for raw in (b"[]", b"{", b"\xff"):
            self.saved.write_bytes(raw)
            self.assert_finding("unsafe-state")
        self.write_json(self.saved, {})
        original = self.store.with_suffix(".original")
        self.store.rename(original)
        self.store.symlink_to(original)
        self.assert_finding("unsafe-state")
        self.store.unlink()
        self.store.mkdir()
        self.assert_finding("unsafe-state")

    def test_c2_2_unreadable_products(self):
        # Symlinks and valid JSON without a list cannot supply matches.
        original = self.products.with_suffix(".original")
        self.products.rename(original)
        self.assert_finding("unreadable products")
        self.products.symlink_to(original)
        self.assert_finding("unreadable products")
        self.products.unlink()
        self.products.mkdir()
        self.assert_finding("unreadable products")
        self.products.rmdir()
        for raw in (b"\xff", b"{", b"[]", b"{}", b'{"products":{}}'):
            with self.subTest(raw=raw):
                self.products.write_bytes(raw)
                self.assert_finding("unreadable products")

    def test_c2_3_draft_unreadable(self):
        # A dangling link or FIFO must not masquerade as no draft or block.
        self.draft.unlink()
        self.draft.symlink_to(self.root / "missing")
        self.assert_finding("draft-unreadable", pairs=False)
        self.draft.unlink()
        os.mkfifo(self.draft, 0o600)
        self.assert_finding("draft-unreadable", pairs=False)
        self.draft.unlink()
        valid = {"code": CODE, "asOf": ASOF, "pairs": PAIRS}
        for changed in ([], {**valid, "code": 1}, {**valid, "asOf": None},
                        {**valid, "pairs": []}, {**valid, "pairs": {}}, {"pairs": PAIRS}):
            self.write_json(self.draft, changed)
            self.assert_finding("draft-unreadable", pairs=False)
        self.draft.write_bytes(b"\xff")
        self.assert_finding("draft-unreadable", pairs=False)

    def test_c2_4_draft_stale_asof(self):
        # A new pull invalidates approval even when the matches are unchanged.
        self.change_db("UPDATE meta SET value=?", (NEW_ASOF,))
        self.assert_finding("draft-stale asof")

    def test_c2_5_draft_stale_pairs(self):
        # A recreated item with the same SKU is reserved by an existing link;
        # count both a missing suggestion and a changed suggestion value.
        self.write_json(self.saved, {"fixture-other-site": {"cloverId": "fixture-old-till", "sku": ITEMS[0][2]}})
        self.assert_finding("draft-stale pairs 1")
        # A same-name suggestion with a changed value is not the draft's pair.
        self.change_db("UPDATE items SET sku=? WHERE id=?", ("fixture-changed-sku", ITEMS[1][0]))
        self.assert_finding("draft-stale pairs 2")
        self.change_db("UPDATE meta SET value=?", (NEW_ASOF,))
        self.assert_report(self.cli(), 1, "pairs 2", "FAIL draft-stale asof", "FAIL draft-stale pairs 2")

    def test_c2_6_cache_absent(self):
        # No usable timestamp means no snapshot, not a stale comparison.
        for value in ("not-a-time", "2000-01-01T00:00:00", None):
            self.change_db("UPDATE meta SET value=?", (value,))
            self.assert_finding("cache-absent")
        self.change_db("DELETE FROM meta")
        self.assert_finding("cache-absent")
        self.store.unlink()
        self.assert_finding("cache-absent")

    def test_c2_7_not_sqlite(self):
        # Never copy unsafe sidecars; corrupt/missing schema cannot be queried.
        for suffix in ("-wal", "-journal"):
            sidecar = self.store.with_name(self.store.name + suffix)
            sidecar.symlink_to(self.root / "missing")
            self.assert_finding("not-sqlite cache.sqlite3")
            sidecar.unlink()
            sidecar.mkdir()
            self.assert_finding("not-sqlite cache.sqlite3")
            sidecar.rmdir()
        pristine = self.store.read_bytes()
        for statement in ("DROP TABLE items", "DROP TABLE meta", "ALTER TABLE items DROP COLUMN sku",
                          "ALTER TABLE meta RENAME COLUMN value TO wrong"):
            with self.subTest(schema_change=statement):
                self.store.write_bytes(pristine)
                self.change_db(statement)
                self.assert_finding("not-sqlite cache.sqlite3")
                self.assertEqual(list(self.scratch.iterdir()), [])
        self.store.write_bytes(b"not a database")
        self.assert_finding("not-sqlite cache.sqlite3")
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_c2_8_temp_unavailable(self):
        # A realpath alias and a nonexistent candidate must not be selected.
        alias = self.root / "alias"
        alias.symlink_to(self.state, target_is_directory=True)
        before = self.input_tree()
        with patch.object(check, "_temp_candidates", return_value=(alias, self.content, self.root / "missing")):
            self.assert_finding("temp-unavailable", result=self.in_process())
        self.assertEqual(self.input_tree(), before)

    def test_c3_usage_exit_2(self):
        # Argument parsing is not a findings run, even with a private operand.
        for argv in ([], ["--state", str(self.state)], self.argv() + ["--unknown", str(self.content)],
                     ["--state", "--content", str(self.content)]):
            with self.subTest(argv=argv):
                result = self.cli(argv)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(result.stderr.splitlines()[-1].startswith("clover_link_draft_check.py: error:"))

    def test_c4_read_only(self):
        # Live apply would replace links and delete the draft. Even an otherwise
        # read-only live SQLite open can create sidecars in a WAL-mode directory.
        self.write_json(self.saved, {"fixture-unrelated": {"cloverId": "fixture-other-till"}})
        self.change_db("PRAGMA journal_mode=WAL")
        before = self.input_tree()
        self.assert_report(self.cli(), 0, "pairs 2", "draft current")
        self.assertEqual(self.input_tree(), before)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_c5_no_private_values(self):
        # Logging decoded inputs, SQLite paths, or raw parser errors leaks canaries.
        secrets = [CODE, *PIDS, *[value for item in ITEMS for value in item],
                   *map(str, (self.root, self.state, self.folder, self.draft, self.store, self.content, self.products))]
        current = self.cli()
        self.assert_report(current, 0, "pairs 2", "draft current")
        self.write_json(self.saved, {PIDS[0]: PAIRS[PIDS[0]]})
        stale = self.cli()
        self.assert_finding("draft-stale pairs 1", result=stale)
        self.store.write_bytes(b"not a database")
        corrupt = self.cli()
        self.assert_finding("not-sqlite cache.sqlite3", result=corrupt)
        usage = self.cli(self.argv() + ["--unknown", str(self.state)])
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (current, stale, corrupt, usage):
            for secret in secrets:
                self.assertNotIn(secret, result.stdout + result.stderr)

    def test_c6_draft_absent_pass(self):
        # Ensure even attempted cache opens/copies are forbidden on this path.
        self.draft.unlink()
        self.products.unlink()
        self.store.write_bytes(b"not a database")
        with (patch.object(check.sqlite3, "connect", side_effect=AssertionError("opened cache")),
              patch.object(check.shutil, "copyfile", side_effect=AssertionError("copied cache"))):
            self.assert_report(self.in_process(), 0, "draft absent")
            self.folder.rename(self.root / "parked-clover")
            self.assert_report(self.in_process(), 0, "draft absent")

    def test_c7_apply_parity(self):
        # Compare with the unchanged writer on a separate copy, not a mock
        # or a second copy of the checker predicate.
        for index, (stamp, saved, expected, reason) in enumerate((
            (ASOF, {}, "ok", None),
            (NEW_ASOF, {}, "stale", "draft-stale asof"),
            (ASOF, {PIDS[0]: PAIRS[PIDS[0]]}, "stale", "draft-stale pairs 1"),
        )):
            with self.subTest(case=index):
                self.change_db("UPDATE meta SET value=?", (stamp,))
                self.write_json(self.saved, saved)
                copy = self.root / f"apply-{index}"
                shutil.copytree(self.state, copy)
                snapshot = reads.Snapshot(tuple(SimpleNamespace(id=i, name=n, sku=s) for i, n, s in ITEMS),
                                          datetime.fromisoformat(stamp))
                self.assertEqual(links.apply(copy, CODE, snapshot, CONTENT, saved),
                                 (expected, 2 if expected == "ok" else 0))
                self.assertEqual((copy / "clover" / links.DRAFT).exists(), expected != "ok")
                if reason is None:
                    self.assert_report(self.cli(), 0, "pairs 2", "draft current")
                else:
                    self.assert_finding(reason)

    def test_c8_wal_rows_counted(self):
        # A base-file-only copy fails to match item B. SQLite may rebuild SHM
        # in its own disposable copy but must not read the input SHM or create one.
        self.change_db("DELETE FROM items WHERE id=?", (ITEMS[1][0],))
        writer_path = self.root / "wal-writer.sqlite3"
        shutil.copyfile(self.store, writer_path)
        writer_wal = writer_path.with_name(writer_path.name + "-wal")
        input_wal = self.store.with_name(self.store.name + "-wal")
        with closing(sqlite3.connect(writer_path)) as writer:
            self.assertEqual(writer.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
            writer.execute("PRAGMA wal_autocheckpoint=0")
            with writer:
                writer.execute("INSERT INTO items VALUES (?, ?, ?)", ITEMS[1])
            shutil.copyfile(writer_path, self.store)
            self.assert_finding("draft-stale pairs 1")
            self.assertGreater(writer_wal.stat().st_size, 0)
            shutil.copyfile(writer_wal, input_wal)
        shm = self.store.with_name(self.store.name + "-shm")
        self.assertFalse(shm.exists())
        before = self.input_tree()
        self.assert_report(self.cli(), 0, "pairs 2", "draft current")
        self.assertEqual(self.input_tree(), before)
        shm.mkdir()  # A -shm entry is ignored even if not a regular file.
        before = self.input_tree()
        self.assert_report(self.cli(), 0, "pairs 2", "draft current")
        self.assertEqual(self.input_tree(), before)

    def test_c9_tmpdir_inside_input(self):
        # tempfile.gettempdir() may probe its parent with a transient write.
        nested = self.content / "nested"
        nested.mkdir()
        for unsafe in (self.state, nested):
            with self.subTest(location=unsafe.name):
                before = self.input_tree()
                result = self.cli(TMPDIR=str(unsafe), TEMP=str(self.scratch), TMP="")
                self.assert_report(result, 0, "pairs 2", "draft current")
                self.assertEqual(self.input_tree(), before)
                self.assertEqual(list(self.scratch.iterdir()), [])
