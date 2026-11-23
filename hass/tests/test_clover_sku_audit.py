"""Offline CLI contract for the Clover SKU audit, using only synthetic caches."""

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


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/clover_sku_audit.py"
SPEC = importlib.util.spec_from_file_location("clover_sku_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
SCHEMA = "CREATE TABLE items (id TEXT PRIMARY KEY, sku TEXT, code TEXT, hidden INTEGER)"
INSERT = "INSERT INTO items VALUES (?, ?, ?, ?)"
PASS = "PASS clover_sku_audit"
FAIL = "FAIL clover_sku_audit"


class CloverSkuAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / "synthetic-state-canary"
        self.state.mkdir()
        self.clover = self.state / "clover"
        self.store = self.clover / "cache.sqlite3"
        self.scratch = self.root / "scratch"
        self.scratch.mkdir()

    def make_cache(self, rows=(), *, wal=False):
        self.clover.mkdir(exist_ok=True)
        with closing(sqlite3.connect(self.store)) as db, db:
            if wal:
                db.execute("PRAGMA journal_mode=WAL")
            db.execute(SCHEMA)
            db.executemany(INSERT, rows)

    def invoke(self, *args, tmpdir=None):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *map(str, args)],
            cwd=self.root,
            env={**os.environ, "TMPDIR": str(tmpdir or self.scratch), "TEMP": str(self.scratch)},
            capture_output=True, text=True, timeout=10,
        )

    def run_audit(self, state=None, **kwargs):
        return self.invoke("--state", state or self.state, **kwargs)

    def assert_report(self, result, status, *lines):
        self.assertEqual(result.returncode, status)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), [*lines, PASS if status == 0 else FAIL])

    def snapshot(self):
        return {
            p.relative_to(self.state): (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
            for p in (self.state, *self.state.rglob("*"))
        }

    def test_c1_full_pass(self):
        # An empty SKU or hidden item must not skew the Hass count or fail the run.
        self.make_cache([
            ("fixture-a", "AS-GEN-FIXTURE-01", "", 0),
            ("fixture-b", "legacy-fixture", "LEGACY-FIXTURE", 1),
            ("fixture-c", "", "", 1),
        ])
        self.assert_report(self.run_audit(), 0, "items 3", "with-sku 2", "hass-sku 1", "hidden-with-sku 1")

    def test_c2_1_unsafe_state(self):
        # Test each path boundary with a symlink and a wrong-kind entry.
        target = self.root / "target"
        target.mkdir()
        for level in ("state", "clover", "store"):
            for symlink in (False, True):
                with self.subTest(level=level, symlink=symlink):
                    state = self.root / f"{level}-{symlink}"
                    clover = state / "clover"
                    path = {"state": state, "clover": clover, "store": clover / self.store.name}[level]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if symlink:
                        path.symlink_to(target if level != "store" else target / "missing")
                    elif level == "store":
                        path.mkdir()
                    else:
                        path.touch()
                    self.assert_report(self.run_audit(state), 1, "FAIL unsafe-state")
        self.assert_report(self.run_audit(self.root / "missing-state"), 1, "FAIL unsafe-state")

    def test_c2_2_duplicate_sku(self):
        # Count groups, not affected rows or extra occurrences; use full case folding.
        skus = ("Straße-fixture", "STRASSE-FIXTURE", "strasse-fixture", "x-fixture", "X-FIXTURE", "", "")
        self.make_cache([(f"fixture-{i}", sku, "", 0) for i, sku in enumerate(skus)])
        self.assert_report(self.run_audit(), 1, "items 7", "with-sku 5", "hass-sku 0", "hidden-with-sku 0",
                           "FAIL duplicate-sku 2")

    def test_c2_3_sku_is_barcode(self):
        # Two matching barcodes count once; a self-only match does not count.
        self.make_cache([
            ("fixture-a", "Straße-fixture", "STRASSE-FIXTURE", 0),
            ("fixture-b", "", "strasse-fixture", 1),
            ("fixture-c", "", "strasse-fixture", 0),
            ("fixture-d", "self-fixture", "SELF-FIXTURE", 0),
            ("fixture-e", "hidden-fixture", "", 1),
            ("fixture-f", "", "HIDDEN-FIXTURE", 0),
        ])
        self.assert_report(self.run_audit(), 1, "items 6", "with-sku 3", "hass-sku 0", "hidden-with-sku 1",
                           "FAIL sku-is-barcode 2")

    def test_c2_4_as_malformed(self):
        # The prefix folds, but the Hass predicate does not; length and sequence also matter.
        skus = ("AS-GEN-FIXTURE-01", "as-gen-fixture-02", "AS-GEN-FIXTURE-00",
                "AS-GEN-ABCDEFGHIJKLMNOPQRST-01", "CAS-FIXTURE", "")
        self.make_cache([(f"fixture-{i}", sku, "", i == 1) for i, sku in enumerate(skus)])
        self.assert_report(self.run_audit(), 1, "items 6", "with-sku 5", "hass-sku 1", "hidden-with-sku 1",
                           "FAIL as-malformed 3")

    def test_c2_5_not_sqlite(self):
        # A corrupt file, incomplete schema, or unsafe recovery sidecar cannot pass silently.
        reason = "FAIL not-sqlite cache.sqlite3"
        columns = ("id", "sku", "code", "hidden")
        for kind in ("corrupt", "no table", *columns, "wal symlink", "journal directory"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(dir=self.root) as directory:
                state = Path(directory)
                clover = state / "clover"
                clover.mkdir()
                store = clover / self.store.name
                if kind == "corrupt":
                    store.write_bytes(b"synthetic invalid database")
                else:
                    with closing(sqlite3.connect(store)) as db, db:
                        if kind in columns:
                            fields = ", ".join(c for c in columns if c != kind)
                            db.execute(f"CREATE TABLE items ({fields})")
                        elif kind != "no table":
                            db.execute(SCHEMA)
                    if kind == "wal symlink":
                        (clover / "cache.sqlite3-wal").symlink_to(state / "missing")
                    if kind == "journal directory":
                        (clover / "cache.sqlite3-journal").mkdir()
                self.assert_report(self.run_audit(state), 1, reason)
                self.assertEqual(list(self.scratch.iterdir()), [])

    def test_c2_6_temp_unavailable(self):
        # If all candidates are unsafe or unusable, do not fall through to an implicit temp root.
        self.make_cache()
        stdout, stderr = io.StringIO(), io.StringIO()
        candidates = (str(self.state), str(self.clover), str(self.root / "missing"))
        before = self.snapshot()
        with (patch.object(AUDIT, "_temp_candidates", return_value=candidates),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            status = AUDIT.main(["--state", str(self.state)])
        self.assertEqual(status, 1)
        self.assertEqual(stdout.getvalue().splitlines(), ["FAIL temp-unavailable", FAIL])
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(self.snapshot(), before)

    def test_c3_usage_exit_2(self):
        # Parser rejections must not become audit findings or echo unknown values.
        for args in ((), ("--state",), ("--state", self.state, "--unknown", self.state)):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(result.stderr.startswith("usage:"))
                self.assertNotIn(str(self.state), result.stderr)

    def test_c4_read_only(self):
        # A direct SQLite open can create and remove transient WAL/SHM sidecars.
        self.make_cache([("fixture-a", "legacy-fixture", "", 0)], wal=True)
        self.assertEqual(set(self.clover.iterdir()), {self.store})
        before = self.snapshot()
        self.assert_report(self.run_audit(), 0, "items 1", "with-sku 1", "hass-sku 0", "hidden-with-sku 0")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_c5_no_private_values(self):
        # All findings together, including a cross-item collision, still print only counts.
        rows = [
            ("synthetic-item-canary-a", "AS-sku-canary", "synthetic-barcode-canary", 0),
            ("synthetic-item-canary-b", "as-SKU-canary", "as-sku-canary", 1),
        ]
        self.make_cache(rows)
        result = self.run_audit()
        for canary in (str(self.state), str(self.clover), str(self.store), *(v for row in rows for v in row[:3])):
            self.assertNotIn(canary.casefold(), (result.stdout + result.stderr).casefold())
        self.assert_report(result, 1, "items 2", "with-sku 2", "hass-sku 0", "hidden-with-sku 1",
                           "FAIL duplicate-sku 1", "FAIL sku-is-barcode 1", "FAIL as-malformed 2")

    def test_c6_absent_pass(self):
        # Both a missing Clover directory and an existing empty one stay untouched.
        for exists in (False, True):
            with self.subTest(clover_exists=exists):
                if exists:
                    self.clover.mkdir()
                before = self.snapshot()
                self.assert_report(self.run_audit(), 0, "cache absent")
                self.assertEqual(self.snapshot(), before)

    def test_c7_hidden_counts(self):
        # Excluding the hidden item would make the visible item's SKU look unique.
        self.make_cache([("fixture-a", "shared-fixture", "", 0), ("fixture-b", "SHARED-FIXTURE", "", 1)])
        self.assert_report(self.run_audit(), 1, "items 2", "with-sku 2", "hass-sku 0", "hidden-with-sku 1",
                           "FAIL duplicate-sku 1")

    def test_c8_wal_rows_counted(self):
        # Opening an immutable/bare copy can silently miss the committed WAL row.
        writer = self.root / "writer.sqlite3"
        self.clover.mkdir()
        with closing(sqlite3.connect(writer)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
            db.execute("PRAGMA wal_autocheckpoint=0")
            db.execute(SCHEMA)
            db.commit()
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.execute(INSERT, ("fixture-wal", "AS-GEN-WAL-FIXTURE-01", "", 1))
            db.commit()
            shutil.copyfile(writer, self.store)
            shutil.copyfile(writer.with_name(writer.name + "-wal"), self.clover / "cache.sqlite3-wal")
        bare = self.root / "bare.sqlite3"
        shutil.copyfile(self.store, bare)
        with closing(sqlite3.connect(bare)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM items").fetchone(), (0,))
        before = self.snapshot()
        self.assert_report(self.run_audit(), 0, "items 1", "with-sku 1", "hass-sku 1", "hidden-with-sku 1")
        self.assertEqual(self.snapshot(), before)
        # SHM is not input, even when it exists in an uncopyable form.
        (self.clover / "cache.sqlite3-shm").mkdir()
        before = self.snapshot()
        self.assert_report(self.run_audit(), 0, "items 1", "with-sku 1", "hass-sku 1", "hidden-with-sku 1")
        self.assertEqual(self.snapshot(), before)

    def test_c9_tmpdir_inside_input(self):
        # Even a cleaned-up temp probe changes the destination directory's mtime.
        self.make_cache()
        nested = self.clover / "nested"
        nested.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(nested)
        before = self.snapshot()
        for tmpdir in (self.state, self.clover, nested, alias):
            with self.subTest(tmpdir=tmpdir.name):
                self.assert_report(self.run_audit(tmpdir=tmpdir), 0,
                                   "items 0", "with-sku 0", "hass-sku 0", "hidden-with-sku 0")
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(list(self.scratch.iterdir()), [])
