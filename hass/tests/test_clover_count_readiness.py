"""Fixture-only contracts for the offline Clover count readiness report."""

from collections import Counter
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
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hass.clover import mapper

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/clover_count_readiness.py"
PASS = "PASS clover_count_readiness"
FAIL = "FAIL clover_count_readiness"
SCHEMA = "CREATE TABLE items (id TEXT PRIMARY KEY, name TEXT, sku TEXT, hidden INTEGER, stock TEXT)"


def product(key, name, status="active"):
    return {"id": key, "name": name, "status": status}


class CloverCountReadinessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.fixture("default")

    def fixture(self, label):
        self.state = self.root / label / "synthetic-state"
        self.folder = self.state / "clover"
        self.folder.mkdir(mode=0o700, parents=True)
        self.content = self.root / label / "synthetic-content"
        self.content.mkdir()
        self.store = self.folder / "cache.sqlite3"
        self.links = self.folder / "links.json"
        self.products = self.content / "products.json"

    def site(self, *products):
        self.products.write_text(json.dumps({"products": products}), encoding="utf-8")

    def link(self, links):
        self.links.write_text(json.dumps(links), encoding="utf-8")
        self.links.chmod(0o600)

    def database(self, *rows, wal=False):
        with closing(sqlite3.connect(self.store)) as db, db:
            if wal:
                db.execute("PRAGMA journal_mode=WAL")
            db.execute(SCHEMA)
            db.executemany("INSERT INTO items VALUES (?, ?, ?, ?, ?)", rows)

    def argv(self):
        return ["--state", str(self.state), "--content", str(self.content)]

    def invoke(self, *extra, argv=None, env=None):
        return subprocess.run([sys.executable, "-B", str(SCRIPT),
                               *(self.argv() if argv is None else argv), *extra],
                              cwd=self.root, capture_output=True, text=True, timeout=10, env=env)

    def assert_report(self, result, code, last):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [last])
        return lines[:-1]

    def assert_finding(self, result, reason):
        lines = self.assert_report(result, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [f"FAIL {reason}"])

    def input_tree(self):
        entries = {}
        for root in (self.state, self.content):
            for path in (root, *root.rglob("*")):
                entries[path] = (path.lstat().st_mtime_ns,
                                 path.read_bytes() if path.is_file() else None)
        return entries

    def test_c1_full_pass(self):
        # NULL must stay distinct from zero; hidden alone is not a finding.
        self.site(product("p-a", "Fixture A"), product("p-b", "Fixture B"),
                  product("p-c", "Fixture C", "held"))
        self.database(("t-a", "Fixture A", "SKU-A", 1, None),
                      ("t-b", "Fixture B", "SKU-B", 1, "-0.00"),
                      ("t-c", "Fixture C", "SKU-C", 0, "-1.25"))
        self.link({"p-b": {"sku": "SKU-B"}, "p-unused": "malformed"})
        self.assertEqual(self.assert_report(self.invoke(), 0, PASS), [
            "note malformed-links 2", "pairs 2", "pairs-by link 0", "pairs-by sku 0",
            "pairs-by name 2", "no-count 1", "hidden-with-count 1",
        ])

    def test_c2_1_unsafe_state(self):
        # Do not mistake unsafe leaves (including broken symlinks) for absence.
        for case in ("state-missing", "state-file", "state-symlink", "folder-file", "folder-symlink",
                     "folder-mode", "store-directory", "store-symlink", "links-directory",
                     "links-symlink", "links-mode", "links-array", "links-json", "links-utf8"):
            with self.subTest(case=case):
                self.fixture(case)
                self.site()
                if case.startswith("state-"):
                    self.state = self.state.with_name("alternate-state")
                    if case.endswith("file"):
                        self.state.touch()
                    elif case.endswith("symlink"):
                        self.state.symlink_to(self.folder.parent, target_is_directory=True)
                elif case in ("folder-file", "folder-symlink"):
                    # Leave the normally private fixture untouched; switch to another state.
                    self.state = self.state.with_name("alternate-state")
                    self.state.mkdir()
                    child = self.state / "clover"
                    if case.endswith("file"):
                        child.touch()
                    else:
                        child.symlink_to(self.folder, target_is_directory=True)
                elif case == "folder-mode":
                    self.folder.chmod(0o750)
                elif case == "store-directory":
                    self.store.mkdir()
                elif case == "store-symlink":
                    self.store.symlink_to("missing-cache")
                elif case == "links-directory":
                    self.links.mkdir(mode=0o700)
                elif case == "links-symlink":
                    self.links.symlink_to("missing-links")
                elif case == "links-mode":
                    self.link({})
                    self.links.chmod(0o640)
                else:
                    self.links.write_bytes({"links-array": b"[]", "links-json": b"{",
                                            "links-utf8": b"\xff"}[case])
                    self.links.chmod(0o600)
                self.assert_finding(self.invoke(), "unsafe-state")

    def test_c2_2_unreadable_products(self):
        # A missing cache must not mask invalid products, nor allow following a symlink.
        for case in ("absent", "symlink", "directory", "utf8", "json", "constant", "object", "list"):
            with self.subTest(case=case):
                self.fixture(case)
                if case == "symlink":
                    target = self.content / "real-products.json"
                    target.write_text('{"products": []}', encoding="utf-8")
                    self.products.symlink_to(target)
                elif case == "directory":
                    self.products.mkdir()
                elif case != "absent":
                    self.products.write_bytes({"utf8": b"\xff", "json": b"{", "object": b"[]",
                                               "constant": b'{"products": [NaN]}',
                                               "list": b'{"products": {}}'}[case])
                self.assert_finding(self.invoke(), "unreadable products")

    def test_c2_3_negative(self):
        # Fractional negatives must not round to zero or count an unpaired item.
        self.site(product("p-a", "Fixture A"))
        self.database(("t-a", "Fixture A", "", 0, "-0.0007"),
                      ("t-b", "Fixture B", "", 0, "-3"))
        self.assert_finding(self.invoke(), "negative 1")

    def test_c2_4_bad_count(self):
        # Decimal accepts non-finite text; neither that nor invalid text is NULL.
        stocks = ("bad-stock-canary", "NaN", "-Infinity", b"123")
        self.site(*(product(f"p-{n}", f"Fixture {n}") for n in range(len(stocks))))
        self.database(*((f"t-{n}", f"Fixture {n}", "", 0, stock)
                        for n, stock in enumerate(stocks)),
                      ("unpaired-t", "Unpaired Fixture", "", 0, "unpaired-invalid"))
        result = self.invoke()
        self.assert_finding(result, "bad-count 4")
        self.assertIn("no-count 0", result.stdout.splitlines())

    def test_c2_5_not_sqlite(self):
        # Reject invalid bytes, missing table/column, and each unsafe recovery sidecar.
        for case in ("bytes", "no-table", "no-stock", "wal-symlink", "journal-directory"):
            with self.subTest(case=case):
                self.fixture(case)
                self.site()
                if case == "bytes":
                    self.store.write_bytes(b"not a database")
                elif case in ("no-table", "no-stock"):
                    sql = "CREATE TABLE unrelated (id TEXT)" if case == "no-table" else SCHEMA.replace(", stock TEXT", "")
                    with closing(sqlite3.connect(self.store)) as db, db:
                        db.execute(sql)
                else:
                    self.database()
                    if case == "wal-symlink":
                        self.store.with_name("cache.sqlite3-wal").symlink_to("missing-wal")
                    else:
                        self.store.with_name("cache.sqlite3-journal").mkdir()
                self.assert_finding(self.invoke(), "not-sqlite cache.sqlite3")

    def test_c2_6_temp_unavailable(self):
        # Reject even a temp alias that resolves inside an input; don't blame SQLite.
        self.site()
        self.database()
        alias = self.root / "temp-alias"
        alias.symlink_to(self.folder, target_is_directory=True)
        spec = importlib.util.spec_from_file_location("clover_count_readiness", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stdout, stderr = io.StringIO(), io.StringIO()
        with (patch.object(module, "_temp_candidates", return_value=[alias, self.root / "absent"]),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            code = module.main(self.argv())
        self.assert_finding(SimpleNamespace(returncode=code, stdout=stdout.getvalue(),
                                            stderr=stderr.getvalue()), "temp-unavailable")

    def test_c3_usage_exit_2(self):
        # Usage is argparse exit 2, not a report finding or a path echo.
        for argv in ([], self.argv()[:2], ["--state", "--content", str(self.content)],
                     [*self.argv(), "--unknown", str(self.content)]):
            with self.subTest(argv=argv):
                result = self.invoke(argv=argv)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line for C3.
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertNotIn(str(self.content), result.stderr)

    def test_c4_read_only(self):
        # Opening even a checkpointed WAL store in place may create shared-memory files.
        self.site(product("p", "Synthetic item"))
        self.link({"p": {"cloverId": "t"}})
        self.database(("t", "Synthetic item", "", 0, "7"), wal=True)
        before = self.input_tree()
        lines = self.assert_report(self.invoke(), 0, PASS)
        self.assertIn("pairs 1", lines)
        self.assertEqual(self.input_tree(), before)
        # A source SHM is neither validated nor copied; SQLite builds its own.
        self.store.with_name("cache.sqlite3-shm").symlink_to("missing-shm")
        before = self.input_tree()
        self.assertEqual(self.assert_report(self.invoke(), 0, PASS), lines)
        self.assertEqual(self.input_tree(), before)

    def test_c5_no_private_values(self):
        # Distinct canaries on success and on two simultaneous findings.
        names = ("Canary Name Alpha", "Canary Name Beta")
        ids = ("Canary-Till-Id-A", "Canary-Till-Id-B")
        skus = ("Canary-Till-Sku-A", "Canary-Till-Sku-B")
        for label, stocks, findings in (
            ("canary-pass", ("15893.017", "14023.045"), []),
            ("canary-fail", ("-93421.109", "Canary-Bad-Stock"), ["FAIL negative 1", "FAIL bad-count 1"]),
        ):
            with self.subTest(case=label):
                self.fixture(label)
                self.site(*(product(f"p-{n}", name) for n, name in enumerate(names)))
                self.database(*((tid, name, sku, 0, stock)
                                for tid, name, sku, stock in zip(ids, names, skus, stocks)))
                result = self.invoke()
                lines = self.assert_report(result, int(bool(findings)), FAIL if findings else PASS)
                self.assertIn("pairs 2", lines)
                self.assertEqual([line for line in lines if line.startswith("FAIL ")], findings)
                for canary in (*names, *ids, *skus, *stocks, str(self.state), str(self.content)):
                    self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_absent_pass(self):
        # First-time users need neither an empty DB nor a clover directory created for them.
        for case in ("empty-clover", "missing-clover"):
            with self.subTest(case=case):
                self.fixture(case)
                if case == "missing-clover":
                    self.state = self.state.with_name("no-clover-state")
                    self.state.mkdir()
                self.site()
                before = self.input_tree()
                self.assertEqual(self.assert_report(self.invoke(), 0, PASS), ["cache absent"])
                self.assertEqual(self.input_tree(), before)

    def test_c7_match_parity(self):
        # Names differ on link/SKU pairs; name normalization and link precedence matter.
        products = [product("p-link", "Web A"), product("p-sku", "Web B"),
                    product("p-name", "Example’s   C")]
        rows = [("t-a", "Register A", "sku-a", 0, "1"),
                ("t-b", "Register B", "sku-b", 0, "2"),
                ("t-c", "example's c", "sku-c", 0, "3")]
        links = {"p-link": {"cloverId": "t-a", "sku": "sku-c"},
                 "p-sku": {"cloverId": "t-stale", "sku": "SKU-B"}}
        self.site(*products)
        self.database(*rows)
        self.link(links)
        direct = mapper.match([SimpleNamespace(**p) for p in products],
                              [SimpleNamespace(id=i, name=n, sku=s) for i, n, s, _, _ in rows], links)
        self.assertEqual(Counter(pair.how for pair in direct.pairs), {"link": 1, "sku": 1, "name": 1})
        lines = self.assert_report(self.invoke(), 0, PASS)
        self.assertIn(f"pairs {len(direct.pairs)}", lines)
        self.assertEqual([line for line in lines if line.startswith("pairs-by ")],
                         ["pairs-by link 1", "pairs-by sku 1", "pairs-by name 1"])

    def test_c8_wal_rows_counted(self):
        # Checkpoint only the schema, then leave a committed match solely in the WAL.
        self.site(product("p", "WAL fixture"))
        source = self.root / "wal-source.sqlite3"
        with closing(sqlite3.connect(source)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA wal_autocheckpoint=0")
            db.execute(SCHEMA)
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            with db:
                db.execute("INSERT INTO items VALUES (?, ?, ?, ?, ?)", ("t", "WAL fixture", "", 1, "7"))
            shutil.copyfile(source, self.store)
            shutil.copyfile(str(source) + "-wal", str(self.store) + "-wal")
        # Verify the fixture really has no row in its base file (copy it without WAL).
        base = self.root / "base-only.sqlite3"
        shutil.copyfile(self.store, base)
        with closing(sqlite3.connect(base)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM items").fetchone(), (0,))
        before = self.input_tree()
        lines = self.assert_report(self.invoke(), 0, PASS)
        self.assertIn("pairs-by name 1", lines)
        self.assertIn("hidden-with-count 1", lines)
        self.assertEqual(self.input_tree(), before)

    def test_c9_tmpdir_inside_input(self):
        # tempfile.gettempdir() can itself write a probe before rejecting an input root.
        self.site(product("p", "Temp fixture"))
        self.database(("t", "Temp fixture", "", 0, None))
        nested = self.content / "nested"
        nested.mkdir()
        safe = self.root / "safe-temp"
        safe.mkdir()
        before = self.input_tree()
        expected = self.assert_report(self.invoke(), 0, PASS)
        for path in (self.state, nested):
            with self.subTest(path=path.name):
                env = dict(os.environ, TMPDIR=str(path), TEMP=str(safe), TMP=str(safe))
                self.assertEqual(self.assert_report(self.invoke(env=env), 0, PASS), expected)
                self.assertEqual(self.input_tree(), before)
                self.assertEqual(list(safe.iterdir()), [])
