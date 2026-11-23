"""Offline contract tests using only synthetic Clover cache copies."""

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

from hass.clover.cache import COLUMNS, SCHEMA


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/clover_cache_diff.py"
PASS = "PASS clover_cache_diff"
FAIL = "FAIL clover_cache_diff"
META = {
    "environment": "synthetic-env-canary",
    "merchantId": "synthetic-till-canary",
    "schema": "synthetic-schema-canary",
    "asOf": "2030-01-01T12:00:00+00:00",
}
EARLIER = "2030-01-01T13:00:00+02:00"  # Later wall time, earlier instant.
ITEM = dict(
    id="synthetic-id-canary", name="synthetic-name-canary", sku="synthetic-sku-canary",
    code="synthetic-code-canary", price_cents=987654321, price_type="FIXED",
    unit_name="synthetic-unit", category_ids='["fake-group"]', categories='["Fake Group"]',
    hidden=0, available=1, stock="876543210", stock_modified=101, modified_time=102,
)
EDITS = dict(
    name="synthetic-rename", sku="synthetic-new-sku", code="synthetic-new-code",
    price_cents=987654322, price_type="VARIABLE", unit_name="synthetic-new-unit",
    category_ids="[]", categories="[]", hidden=1, available=0,
)


def insert(db, item):
    cols = ", ".join(COLUMNS)
    marks = ", ".join("?" for _ in COLUMNS)
    db.execute(f"INSERT INTO items ({cols}) VALUES ({marks})", [item[key] for key in COLUMNS])


def store(path, items=(ITEM,), *, wal=False, **meta):
    with closing(sqlite3.connect(path)) as db, db:
        if wal:
            db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)
        db.executemany("INSERT INTO meta VALUES (?, ?)", (META | meta).items())
        for item in items:
            insert(db, item)


def tree_state(*folders):
    return {
        path: (path.lstat().st_mtime_ns,
               os.readlink(path) if path.is_symlink() else None if path.is_dir() else path.read_bytes())
        for folder in folders for path in (folder, *folder.rglob("*"))
    }


class CloverCacheDiffTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.before = self.root / "before" / "cache.sqlite3"
        self.after = self.root / "after" / "cache.sqlite3"
        self.scratch = self.root / "scratch"
        for folder in (self.before.parent, self.after.parent, self.scratch):
            folder.mkdir()
        self.args = ["--before", str(self.before), "--after", str(self.after)]

    def run_cli(self, *args, tmpdir=None):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *(args or self.args)],
            cwd=self.root, env=os.environ | {
                "TMPDIR": str(tmpdir or self.scratch), "TEMP": str(self.scratch),
            }, capture_output=True, text=True, timeout=10,
        )

    def assert_outcome(self, result, code, last):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [last])
        self.assertEqual(list(self.scratch.iterdir()), [])
        return lines[:-1]

    def assert_findings(self, result, *findings):
        lines = self.assert_outcome(result, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], list(findings))
        return [line for line in lines if not line.startswith("FAIL ")]

    def test_c1_full_pass(self):
        # An unchanged catalog must print all zero lines in the operator's order.
        store(self.before)
        store(self.after, asOf="2030-01-01T13:00:00+00:00")
        self.assertEqual(self.assert_outcome(self.run_cli(), 0, PASS), [
            "before-items 1", "after-items 1", "added 0", "removed 0",
            "changed name 0", "changed sku 0", "changed code 0", "changed price_cents 0",
            "changed price_type 0", "changed unit_name 0", "changed category_ids 0",
            "changed categories 0", "changed hidden 0", "changed available 0", "stock-changed 0",
        ])

    def test_c2_1_unsafe_input(self):
        # Following a leaf symlink or opening a missing path could read/create a wrong store.
        for which in ("before", "after"):
            for kind in ("missing", "directory", "symlink"):
                with self.subTest(which=which, kind=kind), tempfile.TemporaryDirectory(dir=self.root) as tmp:
                    bad = Path(tmp) / "cache.sqlite3"
                    other = Path(tmp) / "other.sqlite3"
                    store(other)
                    if kind == "directory":
                        bad.mkdir()
                    elif kind == "symlink":
                        bad.symlink_to(other)
                    paths = {"before": other, "after": other, which: bad}
                    result = self.run_cli("--before", str(paths["before"]), "--after", str(paths["after"]))
                    self.assertEqual(self.assert_findings(result, f"FAIL unsafe-input {which}"), [])
                    if kind == "missing":
                        self.assertFalse(bad.exists())

    def test_c2_2_different_till(self):
        # Comparing only the merchant would miss an environment or schema mismatch.
        store(self.before)
        store(self.after)
        for key in ("environment", "merchantId", "schema"):
            with self.subTest(key=key):
                with closing(sqlite3.connect(self.after)) as db, db:
                    db.execute("UPDATE meta SET value=? WHERE key=?", ("other-synthetic-value", key))
                self.assert_findings(self.run_cli(), "FAIL different-till")
                with closing(sqlite3.connect(self.after)) as db, db:
                    db.execute("UPDATE meta SET value=? WHERE key=?", (META[key], key))

    def test_c2_3_reversed(self):
        # String or naive time comparison gets the offset case wrong.
        store(self.before)
        store(self.after, asOf=EARLIER)
        self.assert_findings(self.run_cli(), "FAIL reversed")
        for value in ("2030-01-01T10:00:00", "unparseable", "2030-01-01T10:00:00-02:00"):
            with self.subTest(value=value):
                with closing(sqlite3.connect(self.after)) as db, db:
                    db.execute("UPDATE meta SET value=? WHERE key='asOf'", (value,))
                self.assert_outcome(self.run_cli(), 0, PASS)

    def test_c2_4_till_changed(self):
        # Field counters count independently, but total counts each matched item only once.
        second = ITEM | {"id": "synthetic-second-id"}
        store(self.before, (ITEM, second, ITEM | {"id": "synthetic-removed-id"}))
        store(self.after, (second | {"name": "synthetic-second-rename"}, ITEM | EDITS,
                           ITEM | {"id": "synthetic-added-id"}))
        self.assertEqual(self.assert_findings(self.run_cli(), "FAIL till-changed 4"), [
            "before-items 3", "after-items 3", "added 1", "removed 1",
            "changed name 2", "changed sku 1", "changed code 1", "changed price_cents 1",
            "changed price_type 1", "changed unit_name 1", "changed category_ids 1",
            "changed categories 1", "changed hidden 1", "changed available 1", "stock-changed 0",
        ])

    def test_c2_5_not_sqlite(self):
        # Open/query errors and unsafe sidecars must not disclose paths or become passes.
        store(self.before)
        for ddl in (None, "DROP TABLE items", "DROP TABLE meta", "ALTER TABLE items DROP COLUMN modified_time",
                    "ALTER TABLE meta DROP COLUMN value"):
            with self.subTest(ddl=ddl), tempfile.TemporaryDirectory(dir=self.root) as tmp:
                bad = Path(tmp) / self.after.name
                if ddl is None:
                    bad.write_bytes(b"not a database\n" * 100)
                else:
                    store(bad)
                    with closing(sqlite3.connect(bad)) as db, db:
                        db.execute(ddl)
                self.assertEqual(self.assert_findings(
                    self.run_cli("--before", str(self.before), "--after", str(bad)),
                    "FAIL not-sqlite after",
                ), [])
        store(self.after)
        for path in (self.before, self.after):
            for suffix in ("-wal", "-journal"):
                with self.subTest(side=path.parent.name, suffix=suffix):
                    sidecar = path.with_name(path.name + suffix)
                    sidecar.symlink_to(self.root / "no-such-target")
                    try:
                        self.assertEqual(self.assert_findings(
                            self.run_cli(), f"FAIL not-sqlite {path.parent.name}",
                        ), [])
                    finally:
                        sidecar.unlink()

    def test_c2_6_temp_unavailable(self):
        # Exhaustion is a temp failure, not a DB failure or permission to write beside it.
        store(self.before)
        store(self.after)
        spec = importlib.util.spec_from_file_location("clover_cache_diff", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        baseline = tree_state(self.before.parent, self.after.parent)
        with (patch.object(module, "_temp_candidates", return_value=[self.before.parent, self.root / "absent"]),
              redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err):
            code = module.main(self.args)
        self.assertEqual((code, out.getvalue().splitlines(), err.getvalue()), (1, ["FAIL temp-unavailable", FAIL], ""))
        self.assertEqual(tree_state(self.before.parent, self.after.parent), baseline)

    def test_c3_usage_exit_2(self):
        # Usage errors must not reach the comparison or echo path/unknown argument text.
        for args in (self.args[:2], [*self.args, "--unknown", str(self.before)], ["--before", "--after", str(self.after)]):
            with self.subTest(args=len(args)):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line for argparse errors.
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertNotIn(str(self.root), result.stderr)

    def test_c4_read_only(self):
        # Opening a WAL-mode source can create sidecars; the supplied SHM must also be ignored.
        store(self.before, wal=True)
        store(self.after, wal=True)
        self.assertFalse(self.before.with_name(self.before.name + "-wal").exists())
        self.assertFalse(self.before.with_name(self.before.name + "-shm").exists())
        self.after.with_name(self.after.name + "-shm").symlink_to(self.root / "no-such-target")
        baseline = tree_state(self.before.parent, self.after.parent)
        self.assert_outcome(self.run_cli(), 0, PASS)
        self.assertEqual(tree_state(self.before.parent, self.after.parent), baseline)

    def test_c5_no_private_values(self):
        # Exercise several findings together so no diagnostic can echo row or metadata values.
        store(self.before)
        store(self.after, (ITEM | EDITS | {"stock": "876543211"},),
              environment="synthetic-other-environment", merchantId="synthetic-other-merchant", asOf=EARLIER)
        result = self.run_cli()
        self.assert_findings(result, "FAIL different-till", "FAIL reversed", "FAIL till-changed 1")
        for value in (
            *META.values(), *[ITEM[key] for key in ("id", "name", "sku", "code", "price_cents", "stock")],
            EDITS["name"], EDITS["sku"], EDITS["code"], EDITS["price_cents"], "876543211",
            "synthetic-other-environment", "synthetic-other-merchant", EARLIER, self.before, self.after,
        ):
            self.assertNotIn(str(value), result.stdout + result.stderr)

    def test_c6_stock_only_pass(self):
        # Count-only and stock-time-only changes both count, but a sync-only timestamp does not.
        second = ITEM | {"id": "synthetic-second-id"}
        third = ITEM | {"id": "synthetic-third-id"}
        fourth = ITEM | {"id": "synthetic-fourth-id"}
        store(self.before, (ITEM, second, third, fourth))
        store(self.after, (ITEM | {"stock": "876543211"}, second | {"stock_modified": 201},
                           third | {"stock": None, "stock_modified": 202}, fourth | {"modified_time": 203}))
        lines = self.assert_outcome(self.run_cli(), 0, PASS)
        self.assertIn("stock-changed 3", lines)
        self.assertFalse(any("till-changed" in line for line in lines))

    def test_c7_added_item(self):
        # Hidden items still count as additions; their fields aren't matched-row changes.
        store(self.before)
        store(self.after, (ITEM, ITEM | {"id": "synthetic-hidden-id", "hidden": 1}))
        lines = self.assert_findings(self.run_cli(), "FAIL till-changed 1")
        self.assertIn("added 1", lines)
        self.assertIn("changed hidden 0", lines)

    def test_c8_wal_rows_counted(self):
        # No checkpoint and no copied SHM: opening only the main file would miss the addition.
        writer = self.root / "writer.sqlite3"
        store(writer, wal=True)
        shutil.copyfile(writer, self.before)
        with closing(sqlite3.connect(writer)) as db:
            db.execute("PRAGMA wal_autocheckpoint=0")
            insert(db, ITEM | {"id": "synthetic-wal-id"})
            db.commit()
            shutil.copyfile(writer, self.after)
            shutil.copyfile(str(writer) + "-wal", str(self.after) + "-wal")
        self.assertEqual(self.before.read_bytes(), self.after.read_bytes())
        self.assertFalse(self.after.with_name(self.after.name + "-shm").exists())
        baseline = tree_state(self.before.parent, self.after.parent)
        lines = self.assert_findings(self.run_cli(), "FAIL till-changed 1")
        self.assertEqual(lines[:4], ["before-items 1", "after-items 2", "added 1", "removed 0"])
        self.assertEqual(tree_state(self.before.parent, self.after.parent), baseline)

    def test_c9_tmpdir_inside_input(self):
        # A temp dir created and then removed inside either input still changes the directory mtime.
        store(self.before)
        store(self.after)
        nested = self.after.parent / "nested"
        nested.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(nested, target_is_directory=True)
        baseline = tree_state(self.before.parent, self.after.parent)
        for candidate in (self.before.parent, nested, alias):
            with self.subTest(candidate=candidate.name):
                lines = self.assert_outcome(self.run_cli(tmpdir=candidate), 0, PASS)
                self.assertEqual(lines[:4], ["before-items 1", "after-items 1", "added 0", "removed 0"])
                self.assertEqual(tree_state(self.before.parent, self.after.parent), baseline)
