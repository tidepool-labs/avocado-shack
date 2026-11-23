"""Offline CLI contract tests for the Clover name clash report."""

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


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/clover_name_clashes.py"
SCHEMA = "CREATE TABLE items(id TEXT PRIMARY KEY, name TEXT NOT NULL, sku TEXT NOT NULL, hidden INTEGER NOT NULL)"
INSERT = "INSERT INTO items VALUES (?, ?, ?, ?)"
PASS = "PASS clover_name_clashes"
FAIL = "FAIL clover_name_clashes"


class CloverNameClashesTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.state = self.root / "synthetic-state-canary"
        self.state.mkdir()
        self.clover = self.state / "clover"
        self.cache = self.clover / "cache.sqlite3"

    def seed(self, *rows):
        self.clover.mkdir(exist_ok=True)
        with closing(sqlite3.connect(self.cache)) as db, db:
            db.execute(SCHEMA)
            if rows:
                db.executemany(INSERT, rows)

    def invoke(self, *args, env=None):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              cwd=self.root, env=env, capture_output=True, text=True, timeout=10)

    def run_report(self, **kwargs):
        return self.invoke("--state", str(self.state), **kwargs)

    def assert_report(self, result, code, last, *prefix):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), [*prefix, last])

    def input_tree(self):
        return {path.relative_to(self.state): (path.lstat().st_mtime_ns,
                path.read_bytes() if path.is_file() and not path.is_symlink() else None)
                for path in (self.state, *self.state.rglob("*"))}

    def test_c1_full_pass(self):
        # Unique visible names pass, including a name that only warrants a note.
        self.seed(("fixture-a", "Paper Star", "STAR-A", 0),
                  ("fixture-b", "<Gift Tag>", "", 0),
                  ("fixture-c", "Paper Fan", "FAN-C", 1))
        self.assert_report(self.run_report(), 0, PASS,
                           "items 3", "visible 2", "hidden-shadow 0", "note unsafe-name 1")

    def test_c2_1_unsafe_state(self):
        # Following links or treating out-of-shape paths as absent would pass incorrectly.
        for level in ("state", "clover", "cache"):
            for kind in ("symlink", "wrong type"):
                with self.subTest(level=level, kind=kind), tempfile.TemporaryDirectory(dir=self.root) as directory:
                    state = Path(directory) / "state"
                    clover = state / "clover"
                    target = {"state": state, "clover": clover, "cache": clover / self.cache.name}[level]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if kind == "symlink":
                        referent = Path(directory) / "referent"
                        if level == "cache":
                            referent.touch()
                        else:
                            referent.mkdir()
                        target.symlink_to(referent)
                    elif level == "cache":
                        target.mkdir()
                    else:
                        target.touch()
                    self.assert_report(self.invoke("--state", str(state)), 1, FAIL, "FAIL unsafe-state")
        self.assert_report(self.invoke("--state", str(self.root / "missing")), 1, FAIL, "FAIL unsafe-state")

    def test_c2_2_visible_name_clash(self):
        # Count groups, not colliding rows or pairs; unique SKUs don't erase the ambiguity.
        self.seed(*((f"fixture-{i}", name, f"SKU-{i}", 0)
                    for i, name in enumerate(("Paper Star",) * 3 + ("Paper Fan",) * 2)))
        self.assert_report(self.run_report(), 1, FAIL, "items 5", "visible 5", "hidden-shadow 0",
                           "note unsafe-name 0", "FAIL visible-name-clash 2")

    def test_c2_3_clash_without_sku(self):
        # Only visible rows without a SKU inside the ambiguous group count toward this failure.
        self.seed(("fixture-a", "Paper Star", "", 0), ("fixture-b", "Paper Star", "", 0),
                  ("fixture-c", "Paper Star", "STAR-C", 0), ("fixture-d", "Paper Star", "", 1),
                  ("fixture-e", "Paper Fan", "", 0))
        self.assert_report(self.run_report(), 1, FAIL, "items 5", "visible 4", "hidden-shadow 1",
                           "note unsafe-name 0", "FAIL visible-name-clash 1", "FAIL clash-without-sku 2")

    def test_c2_4_not_sqlite(self):
        # A plain file, missing schema, or unsafe sidecar must not look like an empty store.
        for case in ("bad bytes", "no table", "no name", "no sku", "no hidden",
                     "blob name", "wal link", "journal directory"):
            with self.subTest(case=case), tempfile.TemporaryDirectory(dir=self.root) as directory:
                state = Path(directory)
                clover = state / "clover"
                clover.mkdir()
                store = clover / self.cache.name
                if case == "bad bytes":
                    store.write_bytes(b"not a database")
                else:
                    with closing(sqlite3.connect(store)) as db, db:
                        if case == "no table":
                            db.execute("CREATE TABLE unrelated (name TEXT, sku TEXT, hidden INTEGER)")
                        elif case.startswith("no "):
                            missing = case.split()[1]
                            columns = ", ".join(col for col in ("name", "sku", "hidden") if col != missing)
                            db.execute(f"CREATE TABLE items ({columns})")
                        else:
                            db.execute(SCHEMA)
                            if case == "blob name":
                                db.execute(INSERT, ("fixture-a", b"synthetic-blob-name", "", 0))
                    if case == "wal link":
                        store.with_suffix(".sqlite3-wal").symlink_to(state / "missing")
                    if case == "journal directory":
                        store.with_suffix(".sqlite3-journal").mkdir()
                self.assert_report(self.invoke("--state", str(state)), 1, FAIL, "FAIL not-sqlite cache.sqlite3")

    def test_c2_5_temp_unavailable(self):
        # A rejected temp search neither opens the input as a fallback nor looks like corrupt SQLite.
        self.seed()
        spec = importlib.util.spec_from_file_location("clover_name_clashes", SCRIPT)
        assert spec is not None and spec.loader is not None
        report = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(report)
        alias = self.root / "input-alias"
        alias.symlink_to(self.clover)
        before = self.input_tree()
        stdout, stderr = io.StringIO(), io.StringIO()
        candidates = [alias, self.state, self.cache, self.root / "missing"]
        with (patch.object(report, "_temp_candidates", return_value=candidates),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            code = report.main(["--state", str(self.state)])
        self.assert_report(subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue()),
                           1, FAIL, "FAIL temp-unavailable")
        self.assertEqual(self.input_tree(), before)

    def test_c3_usage_exit_2(self):
        # Usage errors belong to argparse, not to the report's finding/last-line protocol.
        for args in ((), ("--state",), ("--state", str(self.state), "--unknown")):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on a usage error.
                self.assertTrue(result.stderr.startswith("usage: "))

    def test_c4_read_only(self):
        # A direct SQLite open can manage sidecars; the report must ignore the original SHM altogether.
        self.seed(("fixture-a", "Paper Star", "STAR-A", 0))
        shm = self.cache.with_suffix(".sqlite3-shm")
        shm.mkdir()  # Copying or validating SHM as an input file would fail.
        before = self.input_tree()
        self.assert_report(self.run_report(), 0, PASS,
                           "items 1", "visible 1", "hidden-shadow 0", "note unsafe-name 0")
        self.assertEqual(self.input_tree(), before)

    def test_c5_no_private_values(self):
        # No raw rows, invalid-name details, or paths in either report stream or argparse diagnostics.
        name = "<synthetic-name-canary>"
        ids = ("synthetic-id-canary-a", "synthetic-id-canary-b")
        sku = "SYNTHETIC-SKU-CANARY"
        self.seed((ids[0], name, sku, 0), (ids[1], name, "", 0))
        result = self.run_report()
        self.assert_report(result, 1, FAIL, "items 2", "visible 2", "hidden-shadow 0", "note unsafe-name 2",
                           "FAIL visible-name-clash 1", "FAIL clash-without-sku 1")
        usage = self.invoke("--state", str(self.state), str(self.cache))
        self.assertEqual(usage.returncode, 2)
        self.assertEqual(usage.stdout, "")
        self.assertTrue(usage.stderr.startswith("usage: "))
        for output in (result.stdout, result.stderr, usage.stdout, usage.stderr):
            for canary in (name, name.strip("<>"), *ids, sku, str(self.root), str(self.state), str(self.cache)):
                self.assertNotIn(canary.casefold(), output.casefold())

    def test_c6_absent_pass(self):
        # Neither missing Clover directory nor an empty one may cause SQLite to create a store.
        for existing_clover in (False, True):
            if existing_clover:
                self.clover.mkdir()
            before = self.input_tree()
            self.assert_report(self.run_report(), 0, PASS, "cache absent")
            self.assertEqual(self.input_tree(), before)

    def test_c7_folding_and_hidden(self):
        # Raw equality misses the visible clash; grouping hidden items introduces a false clash.
        self.seed(("fixture-a", "Blue  Mug", "MUG-A", 0), ("fixture-b", "blue mug", "MUG-B", 0))
        self.assert_report(self.run_report(), 1, FAIL,
                           "items 2", "visible 2", "hidden-shadow 0", "note unsafe-name 0", "FAIL visible-name-clash 1")
        with closing(sqlite3.connect(self.cache)) as db, db:
            db.execute("UPDATE items SET hidden=1 WHERE id=?", ("fixture-b",))
            db.execute(INSERT, ("fixture-c", "Hidden Only", "", 1))
        self.assert_report(self.run_report(), 0, PASS,
                           "items 3", "visible 1", "hidden-shadow 1", "note unsafe-name 0")

    def test_c8_wal_rows_counted(self):
        # A main-file-only copy silently loses the new row, despite an intact baseline schema.
        self.clover.mkdir()
        source = self.root / self.cache.name
        with closing(sqlite3.connect(source)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
            db.execute("PRAGMA wal_autocheckpoint=0")
            with db:
                db.execute(SCHEMA)
                db.execute(INSERT, ("fixture-a", "Paper Star", "STAR-A", 0))
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            baseline = source.read_bytes()
            with db:
                db.execute(INSERT, ("fixture-b", "Paper Fan", "FAN-B", 0))
            self.assertEqual(source.read_bytes(), baseline)
            for suffix in (".sqlite3", ".sqlite3-wal"):
                shutil.copyfile(source.with_suffix(suffix), self.cache.with_suffix(suffix))
        before = self.input_tree()  # Deliberately no input -shm.
        self.assert_report(self.run_report(), 0, PASS,
                           "items 2", "visible 2", "hidden-shadow 0", "note unsafe-name 0")
        self.assertEqual(self.input_tree(), before)

    def test_c9_tmpdir_inside_input(self):
        # Even a transient work directory or tempfile probe changes input directory mtime.
        self.seed(("fixture-a", "Paper Star", "STAR-A", 0))
        nested = self.clover / "nested"
        nested.mkdir()
        fallback = self.root / "safe-temp"
        fallback.mkdir()
        for temp in (self.state, nested):
            with self.subTest(temp=temp):
                before = self.input_tree()
                self.assert_report(self.run_report(env={**os.environ, "TMPDIR": str(temp), "TEMP": str(fallback)}),
                                   0, PASS, "items 1", "visible 1", "hidden-shadow 0", "note unsafe-name 0")
                self.assertEqual(self.input_tree(), before)
                self.assertEqual(list(fallback.iterdir()), [])
