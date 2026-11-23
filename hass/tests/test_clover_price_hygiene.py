"""Fixture-only contract tests for the counts-only Clover price report."""

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

from hass.clover.mapper import MAX_PRICE_CENTS


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/clover_price_hygiene.py"
PASS = "PASS clover_price_hygiene"
FAIL = "FAIL clover_price_hygiene"
SCHEMA = "CREATE TABLE items (id TEXT, price_cents INTEGER, price_type TEXT, unit_name TEXT, hidden INTEGER)"
ONE_FIXED = ["items 1", "hidden 0", "price-type FIXED 1",
             "note per-unit-not-lb 0", "note over-typo-guard 0", PASS]


class CloverPriceHygieneTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / "synthetic-state"
        self.clover = self.state / "clover"
        self.clover.mkdir(parents=True)
        self.store = self.clover / "cache.sqlite3"
        self.safe_temp = self.root / "snapshot-parent"
        self.safe_temp.mkdir()

    def invoke(self, *args, tmpdir=None):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            env={**os.environ, "TMPDIR": str(tmpdir or self.safe_temp), "TEMP": str(self.safe_temp)},
            capture_output=True, text=True, timeout=10,
        )

    def run_report(self, state=None, **options):
        return self.invoke("--state", str(self.state if state is None else state), **options)

    def write_cache(self, *rows, store=None, schema=SCHEMA, wal=False):
        with closing(sqlite3.connect(store or self.store)) as db, db:
            if wal:
                db.execute("PRAGMA journal_mode=WAL")
            db.execute(schema)
            if rows:
                db.executemany("INSERT INTO items VALUES (?, ?, ?, ?, ?)", rows)

    def assert_report(self, result, code, last):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [last])
        self.assertEqual(list(self.safe_temp.iterdir()), [])
        return lines

    def assert_findings(self, result, *reasons):
        lines = self.assert_report(result, 1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         [f"FAIL {reason}" for reason in reasons])
        return lines

    def input_tree(self):
        return {
            path: (path.lstat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
            for path in (self.state, *self.state.rglob("*"))
        }

    def test_c1_full_pass(self):
        # Insertion order, hidden filtering, unit aliases or a >= guard would change the report.
        self.write_cache(
            ("sample-a", 111, "PER_UNIT", "  LB ", 0),
            ("sample-b", 112, "PER_UNIT", " LbS", 0),
            ("sample-c", 113, "PER_UNIT", "POUND", 0),
            ("sample-d", 114, "PER_UNIT", "pOuNdS\t", 1),
            ("sample-e", MAX_PRICE_CENTS + 1, "PER_UNIT", "bundle", 1),
            ("sample-f", None, "VARIABLE", "", 0),
            ("sample-g", MAX_PRICE_CENTS, "FIXED", "", 0),
        )
        self.assertEqual(self.assert_report(self.run_report(), 0, PASS), [
            "items 7", "hidden 2", "price-type FIXED 1", "price-type VARIABLE 1",
            "price-type PER_UNIT 5", "note per-unit-not-lb 1", "note over-typo-guard 1", PASS,
        ])

    def test_c2_1_unsafe_state(self):
        # A following stat or exists() alone can miss symlinks, especially dangling ones.
        for component in ("state", "clover", "store"):
            for kind in ("wrong-kind", "symlink", "dangling"):
                with self.subTest(component=component, kind=kind):
                    root = self.root / f"{component}-{kind}"
                    root.mkdir()
                    state = root / "state"
                    clover = state / "clover"
                    store = clover / self.store.name
                    if component != "state":
                        state.mkdir()
                    if component == "store":
                        clover.mkdir()
                    leaf = {"state": state, "clover": clover, "store": store}[component]
                    if kind == "wrong-kind":
                        if component == "store":
                            leaf.mkdir()
                        else:
                            leaf.touch()
                    else:
                        target = root / "target"
                        if kind == "symlink":
                            if component == "store":
                                self.write_cache(store=target)
                            else:
                                target.mkdir()
                        leaf.symlink_to(target)
                    self.assertEqual(self.assert_findings(self.run_report(state), "unsafe-state"),
                                     ["FAIL unsafe-state", FAIL])
        self.assert_findings(self.run_report(self.root / "missing-state"), "unsafe-state")

    def test_c2_2_fixed_no_price(self):
        # NULL, zero and negative each count; a positive fixed price does not.
        self.write_cache(*[(f"sample-{i}", price, "FIXED", "", i % 2)
                           for i, price in enumerate((None, 0, -4, 113))])
        self.assert_findings(self.run_report(), "fixed-no-price 3")

    def test_c2_3_per_unit_no_unit(self):
        # Whitespace-only and absent names are missing, not just non-lb notes.
        self.write_cache(("sample-a", 111, "PER_UNIT", "", 0),
                         ("sample-b", 112, "PER_UNIT", " \t ", 1),
                         ("sample-c", 113, "PER_UNIT", None, 0),
                         ("sample-d", 114, "PER_UNIT", "crate", 0))
        lines = self.assert_findings(self.run_report(), "per-unit-no-unit 3")
        self.assertIn("note per-unit-not-lb 1", lines)

    def test_c2_4_unknown_price_type(self):
        # Reusing the sync coercion would hide unknown types; do not stop at the first finding.
        self.write_cache(("sample-a", 111, "fixed", "", 0),
                         ("sample-b", 112, None, "", 1),
                         ("sample-c", 0, "FIXED", "", 0),
                         ("sample-d", 113, "PER_UNIT", "", 0))
        lines = self.assert_findings(self.run_report(), "fixed-no-price 1",
                                     "per-unit-no-unit 1", "unknown-price-type 2")
        self.assertEqual([line for line in lines if line.startswith("price-type ")],
                         ["price-type FIXED 1", "price-type PER_UNIT 1"])

    def test_c2_5_not_sqlite(self):
        # Opening a SQLite file does not prove its schema; sidecar refusal is independent.
        for kind in ("corrupt", "missing-table", "missing-column", "wal-link", "journal-directory"):
            with self.subTest(kind=kind):
                state = self.root / kind
                clover = state / "clover"
                clover.mkdir(parents=True)
                store = clover / self.store.name
                if kind == "corrupt":
                    store.write_bytes(b"synthetic non-database")
                elif kind == "missing-table":
                    self.write_cache(store=store, schema=SCHEMA.replace("items", "elsewhere"))
                elif kind == "missing-column":
                    self.write_cache(store=store, schema=SCHEMA.replace("unit_name", "other_name"))
                else:
                    self.write_cache(store=store)
                    if kind == "wal-link":
                        store.with_suffix(".sqlite3-wal").symlink_to(clover / "missing")
                    else:
                        store.with_suffix(".sqlite3-journal").mkdir()
                self.assertEqual(self.assert_findings(self.run_report(state), "not-sqlite cache.sqlite3"),
                                 ["FAIL not-sqlite cache.sqlite3", FAIL])

    def test_c2_6_temp_unavailable(self):
        # Ineligible parents must not trigger tempfile's implicit fallback or a SQLite error.
        spec = importlib.util.spec_from_file_location("clover_price_hygiene", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.write_cache(("sample", 111, "FIXED", "", 0))
        out, err = io.StringIO(), io.StringIO()
        with patch.object(module, "_temp_candidates", return_value=(self.clover, self.store)), \
                redirect_stdout(out), redirect_stderr(err):
            code = module.main(["--state", str(self.state)])
        self.assertEqual((code, out.getvalue().splitlines(), err.getvalue()),
                         (1, ["FAIL temp-unavailable", FAIL], ""))

    def test_c3_usage_exit_2(self):
        # Usage errors are not inventory findings and have no stdout terminal marker.
        for args in ((), ("--state",), ("--state", str(self.state), "--unknown")):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # Opening even a checkpointed WAL-mode input can create then remove a sidecar.
        self.write_cache(("sample", 111, "FIXED", "", 0), wal=True)
        self.assertFalse(self.store.with_suffix(".sqlite3-shm").exists())
        before = self.input_tree()
        self.assertEqual(self.assert_report(self.run_report(), 0, PASS), ONE_FIXED)
        self.assertEqual(self.input_tree(), before)

    def test_c5_no_private_values(self):
        # A row dump or a raw error/usage diagnostic can expose values and absolute paths.
        price, unit, item = 987654321, "synthetic-secret-unit", "synthetic-secret-id"
        self.write_cache((item, price, "PER_UNIT", unit, 0))
        result = self.run_report()
        lines = self.assert_report(result, 0, PASS)
        self.assertIn("note per-unit-not-lb 1", lines)
        self.assertIn("note over-typo-guard 1", lines)
        bad_state = self.run_report(self.store)
        self.assert_findings(bad_state, "unsafe-state")
        usage = self.invoke("--state", str(self.state), str(self.store))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for run in (result, bad_state, usage):
            for canary in (str(price), unit, item, str(self.root)):
                self.assertNotIn(canary, run.stdout + run.stderr)

    def test_c6_absent_pass(self):
        # No implicit creation whether the Clover directory exists or not.
        for state in (self.state, self.root / "without-clover"):
            with self.subTest(state=state):
                state.mkdir(exist_ok=True)
                before = (list(state.rglob("*")), state.stat().st_mtime_ns)
                self.assertEqual(self.assert_report(self.run_report(state), 0, PASS), ["cache absent", PASS])
                self.assertEqual((list(state.rglob("*")), state.stat().st_mtime_ns), before)

    def test_c7_variable_ok(self):
        # Applying fixed-price requirements to VARIABLE would refuse an expected NULL.
        self.write_cache(("sample", None, "VARIABLE", "", 0))
        self.assertEqual(self.assert_report(self.run_report(), 0, PASS), [
            "items 1", "hidden 0", "price-type VARIABLE 1",
            "note per-unit-not-lb 0", "note over-typo-guard 0", PASS,
        ])

    def test_c8_wal_rows_counted(self):
        # Copying only the base or using immutable SQLite can quietly lose a committed row.
        writer = self.root / "writer.sqlite3"
        self.write_cache(store=writer, wal=True)
        with closing(sqlite3.connect(writer)) as db:
            db.execute("PRAGMA wal_autocheckpoint=0")
            with db:
                db.execute("INSERT INTO items VALUES ('sample', 111, 'FIXED', '', 0)")
            shutil.copyfile(writer, self.store)
            shutil.copyfile(writer.with_suffix(".sqlite3-wal"), self.store.with_suffix(".sqlite3-wal"))
            base_only = self.root / "base-only.sqlite3"
            shutil.copyfile(writer, base_only)
            with closing(sqlite3.connect(base_only)) as base:
                self.assertEqual(base.execute("SELECT COUNT(*) FROM items").fetchone(), (0,))
        before = self.input_tree()  # There is a WAL, but no SHM file to reuse.
        self.assertEqual(self.assert_report(self.run_report(), 0, PASS), ONE_FIXED)
        self.assertEqual(self.input_tree(), before)
        # A dangling SHM symlink is ignored, not validated or copied.
        self.store.with_suffix(".sqlite3-shm").symlink_to(self.clover / "missing")
        before = self.input_tree()
        self.assertEqual(self.assert_report(self.run_report(), 0, PASS), ONE_FIXED)
        self.assertEqual(self.input_tree(), before)

    def test_c9_tmpdir_inside_input(self):
        # Even a temporary probe file changes directory mtime when it is removed.
        self.write_cache(("sample", 111, "FIXED", "", 0))
        nested = self.clover / "nested-temp"
        nested.mkdir()
        alias = self.root / "temp-alias"
        alias.symlink_to(nested, target_is_directory=True)
        for tmpdir in (self.state, self.clover, nested, alias):
            with self.subTest(tmpdir=tmpdir):
                before = self.input_tree()
                self.assertEqual(self.assert_report(self.run_report(tmpdir=tmpdir), 0, PASS), ONE_FIXED)
                self.assertEqual(self.input_tree(), before)


if __name__ == "__main__":
    unittest.main()
