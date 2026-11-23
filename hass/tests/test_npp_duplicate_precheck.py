"""Fixture-only contract tests for the offline duplicate precheck CLI."""

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


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_duplicate_precheck.py"
SPEC = importlib.util.spec_from_file_location("npp_duplicate_precheck", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
precheck = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(precheck)

PASS = "PASS npp_duplicate_precheck"
FAIL = "FAIL npp_duplicate_precheck"


class DuplicatePrecheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="precheck-canary-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        self.content = self.inputs / "content"
        self.content.mkdir()
        self.state = self.inputs / "state"
        self.state.mkdir()
        self.cache = self.state / "clover" / "cache.sqlite3"
        self.names = self.inputs / "names.txt"
        self.names.write_text("Fresh Quill\n", encoding="utf-8")
        self.write_content()
        env = patch.dict(os.environ, {"TMPDIR": str(self.root)})
        env.start()
        self.addCleanup(env.stop)

    def write_content(self, products=(), makers=None):
        for filename, data in (("products", list(products)), ("makers", makers or {})):
            (self.content / f"{filename}.json").write_text(json.dumps({filename: data}), encoding="utf-8")

    def create_cache(self, *names, path=None):
        path = self.cache if path is None else path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE items(name TEXT)")
            db.executemany("INSERT INTO items VALUES (?)", [(name,) for name in names])

    def args(self, *, content=None, names=None, state=None):
        args = ["--content", str(content or self.content), "--names", str(names or self.names)]
        return args if state is None else [*args, "--state", str(state)]

    def invoke(self, **options):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = precheck.main(self.args(**options))
        return rc, stdout.getvalue(), stderr.getvalue()

    def cli(self, args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                                capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout, result.stderr

    def assert_report(self, result, code, *lines):
        rc, stdout, stderr = result
        self.assertEqual(rc, code)
        self.assertEqual(stdout, "\n".join((*lines, PASS if code == 0 else FAIL)) + "\n")
        self.assertEqual(stderr, "")

    def snapshot_inputs(self):
        return {path.relative_to(self.inputs): (path.stat().st_mtime_ns,
                                                path.read_bytes() if path.is_file() else None)
                for path in (self.inputs, *self.inputs.rglob("*"))}

    def test_c1_full_pass(self):
        # Skipped rows must not consume numbers; twins alone must not fail the run.
        self.names.write_bytes("# generated\r\n\r\nFresh Quill\r\nSample Petal\r\n".encode())
        self.write_content([{"name": "Fable-Spindle"}, {"name": "fáble—spindle"},
                            {"name": "Held Spool", "status": "held"},
                            {"name": "held spool", "status": "held"},
                            {"name": "Mixed Bobbin"}, {"name": "mixed bobbin", "status": "held"}],
                           {"sample petal": {"name": "Sample Petal", "hidden": True}})
        self.assert_report(self.cli(self.args()), 0, "candidate 1 none", "candidate 2 none", "catalog-twins 1")

    def test_c2_1_bad_names(self):
        # Refuse missing, symlinked, non-UTF-8, and effectively empty inputs.
        invalid = {"absent": self.inputs / "absent", "symlink": self.inputs / "alias",
                   "encoding": self.inputs / "encoding", "comments": self.inputs / "comments"}
        invalid["symlink"].symlink_to(self.names)
        invalid["encoding"].write_bytes(b"Synthetic\xff\n")
        invalid["comments"].write_text("# Synthetic\n  \t\n", encoding="utf-8")
        for case, path in invalid.items():
            with self.subTest(case=case):
                self.assert_report(self.invoke(names=path), 1, "FAIL bad-names")

    def test_c2_2_unreadable_content(self):
        # Reject malformed wrappers and bad records before passing them to Hass.
        for key, bad_shapes in (("products", (b"{}", b'{"products":{}}', b'{"products":[null]}',
                                             b'{"products":[{}]}', b'{"products":[{"name":false}]}')),
                                ("makers", (b"{}", b'{"makers":[]}', b'{"makers":{"fixture":null}}',
                                            b'{"makers":{"fixture":{}}}',
                                            b'{"makers":{"fixture":{"name":false}}}'))):
            good = {"products": b'{"products":[]}', "makers": b'{"makers":{}}'}
            other = "makers" if key == "products" else "products"
            for i, raw in enumerate((None, "symlink", b"\xff", b"[", b"[]", *bad_shapes)):
                with self.subTest(key=key, case=i):
                    directory = self.inputs / f"{key}-{i}"
                    directory.mkdir()
                    (directory / f"{other}.json").write_bytes(good[other])
                    path = directory / f"{key}.json"
                    if raw == "symlink":
                        path.symlink_to(self.content / path.name)
                    elif raw is not None:
                        path.write_bytes(raw)
                    self.assert_report(self.invoke(content=directory), 1, "FAIL unreadable content")

    def test_c2_3_identity_refused(self):
        # Internal line separators must reach identity_text, not split into two names.
        self.names.write_text("# heading\nFable\u2028Bobbin\n---\nFresh Quill\n", encoding="utf-8")
        self.assert_report(self.invoke(), 1, "candidate 1 refused", "FAIL identity-refused 1",
                           "candidate 2 refused", "FAIL identity-refused 2", "candidate 3 none", "catalog-twins 0")

    def test_c2_4_duplicate(self):
        # A three-way hit has ordered sources and only one duplicate finding.
        self.names.write_text("Fable-Spindle\nMock Bobbin\n", encoding="utf-8")
        self.write_content([{"name": "Fáble—Spindle"}],
                           {"key": {"name": "fable-spindle"}, "mock bobbin": {"name": "Sample Petal"}})
        self.create_cache("fABLE-spindle")
        self.assert_report(self.invoke(state=self.state), 1, "candidate 1 catalog,makers,clover", "FAIL duplicate 1",
                           "candidate 2 makers", "FAIL duplicate 2", "catalog-twins 0")

    def test_c2_5_held_match(self):
        # A held match is reported even when an active record also triggers duplicate.
        self.write_content([{"name": "Fresh Quill"}, {"name": "FRESH QUÍLL", "status": "held"}])
        self.assert_report(self.invoke(), 1, "candidate 1 catalog,held", "FAIL duplicate 1",
                           "FAIL held-match 1", "catalog-twins 0")

    def test_c2_6_unsafe_state(self):
        # lstat must reject links and wrong file types at all three state levels.
        for part in ("state", "clover", "cache"):
            for kind in ("symlink", "wrong-type"):
                with self.subTest(part=part, kind=kind):
                    state = self.inputs / f"{part}-{kind}"
                    clover = state / "clover"
                    path = {"state": state, "clover": clover, "cache": clover / self.cache.name}[part]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if kind == "symlink":
                        path.symlink_to(self.root / "nonexistent")
                    elif part == "cache":
                        path.mkdir()
                    else:
                        path.touch()
                    self.assert_report(self.invoke(state=state), 1, "FAIL unsafe-state")
        self.assert_report(self.invoke(state=self.inputs / "missing-state"), 1, "FAIL unsafe-state")

    def test_c2_7_not_sqlite(self):
        # Opening a database alone doesn't prove it has the required table and column.
        cases = ("corrupt", "no-table", "no-column", "wal-link", "wal-dir", "journal-link", "journal-dir")
        for case in cases:
            with self.subTest(case=case):
                state = self.inputs / case
                store = state / "clover" / self.cache.name
                store.parent.mkdir(parents=True)
                if case == "corrupt":
                    store.write_bytes(b"fixture bytes, not SQLite")
                elif case in ("no-table", "no-column"):
                    with closing(sqlite3.connect(store)) as db:
                        db.execute("CREATE TABLE other(name TEXT)" if case == "no-table"
                                   else "CREATE TABLE items(other TEXT)")
                else:
                    self.create_cache(path=store)
                    suffix, kind = case.split("-")
                    sidecar = store.with_name(f"{store.name}-{suffix}")
                    if kind == "link":
                        sidecar.symlink_to(self.root / "nonexistent")
                    else:
                        sidecar.mkdir()
                self.assert_report(self.invoke(state=state), 1, "FAIL not-sqlite cache.sqlite3")

    def test_c2_8_temp_unavailable(self):
        # Failure to allocate a safe parent is not a database failure or a write under state.
        self.create_cache("Fresh Quill")
        before = self.snapshot_inputs()
        with patch.object(precheck, "_temp_candidates", return_value=[self.state, self.cache.parent,
                                                                      self.root / "nonexistent"]):
            self.assert_report(self.invoke(state=self.state), 1, "FAIL temp-unavailable")
        self.assertEqual(self.snapshot_inputs(), before)

    def test_c3_usage_exit_2(self):
        # Invalid invocations must stop at argparse, not produce a partial report.
        for args in ([], self.args() + ["--unknown"], self.args() + ["--state"]):
            with self.subTest(case=len(args)):
                rc, stdout, stderr = self.cli(args)
                self.assertEqual(rc, 2)
                self.assertEqual(stdout.splitlines(), [])  # no last stdout line
                self.assertTrue(stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # A direct SQLite open can create transient SHM/WAL files, even with query_only.
        self.create_cache("Fresh Quill")
        with closing(sqlite3.connect(self.cache)) as db:
            db.execute("PRAGMA journal_mode=WAL").fetchone()
        before = self.snapshot_inputs()
        scratch_entries = set(self.root.iterdir())
        self.assert_report(self.invoke(state=self.state), 1, "candidate 1 clover", "FAIL duplicate 1", "catalog-twins 0")
        self.assertEqual(self.snapshot_inputs(), before)
        self.assertEqual(set(self.root.iterdir()), scratch_entries)

    def test_c5_no_private_values(self):
        # Scan both streams for each source and absolute paths, including error paths.
        candidate, product, maker, till = "Fable-Spindle", "Fáble—Spindle", "FABLE-SPINDLE", "fable-spindle"
        self.names.write_text(candidate + "\n", encoding="utf-8")
        self.write_content([{"name": product}], {"synthetic": {"name": maker}})
        self.create_cache(till)
        result = self.cli(self.args(state=self.state))
        self.assert_report(result, 1, "candidate 1 catalog,makers,clover", "FAIL duplicate 1", "catalog-twins 0")
        absent = self.inputs / "absent-canary"
        invalid = self.cli(self.args(names=absent))
        self.assert_report(invalid, 1, "FAIL bad-names")
        usage = self.cli([*self.args(), str(absent)])
        self.assertEqual(usage[:2], (2, ""))
        report = "".join(r[1] + r[2] for r in (result, invalid, usage))
        for value in (candidate, product, maker, till, self.root, self.content, self.names,
                      self.state, self.cache, absent):
            self.assertNotIn(str(value), report)

    def test_c6_held_gap(self):
        # Counting a held-only name as catalog would incorrectly predict a question.
        products = [{"name": "Frésh—Quill", "status": "held"}]
        self.write_content(products)
        self.names.write_text("fresh-quill\n", encoding="utf-8")
        self.assert_report(self.invoke(), 1, "candidate 1 held", "FAIL held-match 1", "catalog-twins 0")
        self.assertEqual(precheck._duplicates("Fresh-Quill", products, {}, None), ())

    def test_c7_clover_source(self):
        # Absent cache is optional; the same name hits only when --state supplies it.
        for clover_exists in (False, True):
            with self.subTest(clover_exists=clover_exists):
                if clover_exists:
                    self.cache.parent.mkdir()
                before = self.snapshot_inputs()
                self.assert_report(self.invoke(state=self.state), 0, "candidate 1 none", "catalog-twins 0")
                self.assertEqual(self.snapshot_inputs(), before)
        self.create_cache("Fresh Quill")
        self.assert_report(self.invoke(), 0, "candidate 1 none", "catalog-twins 0")
        self.assert_report(self.invoke(state=self.state), 1, "candidate 1 clover", "FAIL duplicate 1", "catalog-twins 0")

    def test_c8_wal_rows_counted(self):
        # A base-only or immutable open misses the WAL row; SHM must never be read/copied.
        source = self.root / self.cache.name
        self.create_cache(path=source)
        self.cache.parent.mkdir()
        with closing(sqlite3.connect(source)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
            db.execute("PRAGMA wal_autocheckpoint=0")
            db.execute("INSERT INTO items VALUES ('Fresh Quill')")
            db.commit()
            for suffix in ("", "-wal"):
                shutil.copyfile(source.with_name(source.name + suffix), self.cache.with_name(self.cache.name + suffix))
        base = self.root / "base-only.sqlite3"
        shutil.copyfile(self.cache, base)
        with closing(sqlite3.connect(base)) as base_only:
            self.assertEqual(list(base_only.execute("SELECT name FROM items")), [])
        before = self.snapshot_inputs()
        self.assert_report(self.invoke(state=self.state), 1, "candidate 1 clover", "FAIL duplicate 1", "catalog-twins 0")
        self.assertEqual(self.snapshot_inputs(), before)
        shm = self.cache.with_name(self.cache.name + "-shm")
        shm.symlink_to(self.root / "nonexistent")
        self.assert_report(self.invoke(state=self.state), 1, "candidate 1 clover", "FAIL duplicate 1", "catalog-twins 0")
        self.assertTrue(shm.is_symlink())

    def test_c9_tmpdir_inside_input(self):
        # Even a transient scratch directory or tempfile probe changes parent mtime.
        self.create_cache("Fresh Quill")
        for enclosing in (self.content, self.names.parent, self.state):
            child = enclosing / "nested"
            child.mkdir()
            alias = self.root / f"alias-{enclosing.name}"
            alias.symlink_to(child)
            for location in (enclosing, child, alias):
                with self.subTest(directory=enclosing.name, location=location.name):
                    before = self.snapshot_inputs()
                    with patch.dict(os.environ, {"TMPDIR": str(location), "TEMP": str(self.root)}):
                        self.assert_report(self.cli(self.args(state=self.state)), 1, "candidate 1 clover",
                                           "FAIL duplicate 1", "catalog-twins 0")
                    self.assertEqual(self.snapshot_inputs(), before)
