"""Fixture-only acceptance tests for the offline Clover category report."""

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


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/clover_category_readiness.py"
PASS = "PASS clover_category_readiness"
FAIL = "FAIL clover_category_readiness"


class CloverCategoryReadinessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.map_dir, self.till_dir, self.content, self.scratch = (
            self.root / name for name in ("map", "till", "content", "scratch")
        )
        for directory in (self.map_dir, self.till_dir, self.content, self.scratch):
            directory.mkdir()
        self.mapping = self.map_dir / "map.json"
        self.cache = self.till_dir / "cache.sqlite3"
        self.write_json(self.mapping, {"fruit": "Mock Orchard"})
        self.products({"category": "fruit", "status": "active"})
        self.make_cache(self.cache, [(["Mock Orchard"], 0)])

    @staticmethod
    def write_json(path, document):
        path.write_text(json.dumps(document), encoding="utf-8")

    def products(self, *records):
        self.write_json(self.content / "products.json", {"products": list(records)})

    @staticmethod
    def make_cache(path, rows=(), *, wal=False):
        with closing(sqlite3.connect(path)) as db:
            if wal:
                db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE items (categories TEXT, hidden INTEGER)")
            db.executemany("INSERT INTO items VALUES (?, ?)",
                           [(json.dumps(names), hidden) for names, hidden in rows])
            db.commit()

    def args(self, *, mapping=None, cache=None, content=None):
        return ["--category-map", str(mapping or self.mapping), "--cache", str(cache or self.cache),
                "--content", str(content or self.content)]

    def invoke(self, argv=None, *, temp=None):
        env = dict(os.environ, TMPDIR=str(temp or self.scratch), TEMP=str(self.scratch), TMP="")
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *(self.args() if argv is None else argv)],
                              cwd=self.root, env=env, capture_output=True, text=True, timeout=10)

    def assert_result(self, result, code, *findings):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [FAIL if code else PASS])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(findings))
        return lines

    def input_state(self):
        inputs = (self.map_dir, self.till_dir, self.content)
        paths = [path for directory in inputs for path in (directory, *directory.rglob("*"))]
        return {path: (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
                for path in paths}

    def test_c1_full_pass(self):
        # Exact shelf counts catch inactive listings, substring matching, and duplicate till tags.
        self.products({"category": "fruit", "status": "active"},
                      {"category": "fruit", "status": "active"},
                      {"category": "fruit", "status": "held"},
                      {"category": "dairy", "status": "hidden"},
                      {"category": "general", "status": "active"})
        self.write_json(self.mapping, {"fruit": "Mock Orchard", "general": "Mock Counter",
                                      "dairy": "Mock Unused"})
        cache = self.till_dir / "full.sqlite3"
        self.make_cache(cache, [(["  ＭＯＣＫ  ORCHARD  ", "mock orchard", "Mock Counter"], 0),
                                (["Mock Orchard Extra"], 0), (["Mock Orchard"], 1),
                                (["mock orchard"], 0)])
        self.assertEqual(self.assert_result(self.invoke(self.args(cache=cache)), 0), [
            "shelf fruit products 2", "shelf fruit mapped yes", "shelf fruit till-items 2",
            "shelf general products 1", "shelf general mapped yes", "shelf general till-items 1",
            "note till-engine-unsupported general", PASS,
        ])

    def test_c2_1_bad_category_map(self):
        # Reject unsafe leaves and invalid map shape, keys, value type and length.
        cases = {"syntax": b"{", "encoding": b"\xff", "array": b"[]", "key": b'{"other":"Mock"}',
                 "type": b'{"fruit":7}', "empty": b'{"fruit":""}',
                 "length": json.dumps({"fruit": "x" * 101}).encode()}
        for name, raw in cases.items():
            (self.map_dir / name).write_bytes(raw)
        (self.map_dir / "symlink").symlink_to(self.mapping)
        for name in (*cases, "missing", "symlink"):
            with self.subTest(name=name):
                self.assert_result(self.invoke(self.args(mapping=self.map_dir / name)), 1, "FAIL bad-category-map")

    def test_c2_2_unreadable_products(self):
        # A readable but wrong-shaped document must not look like an empty catalog.
        for name, raw in (("missing", None), ("symlink", None), ("encoding", b"\xff"),
                          ("syntax", b"{"), ("array", b"[]"), ("no-products", b"{}"),
                          ("wrong-type", b'{"products":{}}')):
            with self.subTest(name=name):
                content = self.content / name
                content.mkdir()
                products = content / "products.json"
                if name == "symlink":
                    products.symlink_to(self.content / "products.json")
                elif raw is not None:
                    products.write_bytes(raw)
                self.assert_result(self.invoke(self.args(content=content)), 1, "FAIL unreadable products")

    def test_c2_3_unmapped(self):
        # Report each active shelf once, not once per listing, and never count an unmapped shelf at the till.
        self.products({"category": "fruit", "status": "active"},
                      {"category": "fruit", "status": "active"},
                      {"category": "dairy", "status": "active"},
                      {"category": "bread", "status": "held"})
        self.write_json(self.mapping, {})
        lines = self.assert_result(self.invoke(), 1, "FAIL unmapped fruit", "FAIL unmapped dairy")
        self.assertEqual(lines, ["shelf fruit products 2", "shelf fruit mapped no", "FAIL unmapped fruit",
                                 "shelf dairy products 1", "shelf dairy mapped no", "FAIL unmapped dairy", FAIL])

    def test_c2_4_not_sqlite(self):
        # Invalid bytes/schema and unsafe leaves must not be opened as empty caches.
        for name in ("missing", "directory", "symlink", "corrupt", "no-table", "no-categories",
                     "no-hidden", "wal-symlink", "journal-directory"):
            with self.subTest(name=name):
                directory = self.till_dir / name
                directory.mkdir()
                store = directory / self.cache.name
                if name == "directory":
                    store.mkdir()
                elif name == "symlink":
                    store.symlink_to(self.cache)
                elif name == "corrupt":
                    store.write_bytes(b"synthetic non-database")
                elif name.startswith("no-"):
                    with closing(sqlite3.connect(store)) as db:
                        table = {"no-table": "unrelated (n)", "no-categories": "items (hidden)",
                                 "no-hidden": "items (categories)"}[name]
                        db.execute(f"CREATE TABLE {table}")
                elif name.startswith(("wal-", "journal-")):
                    shutil.copyfile(self.cache, store)
                    if name == "wal-symlink":
                        store.with_name(store.name + "-wal").symlink_to(directory / "absent")
                    else:
                        store.with_name(store.name + "-journal").mkdir()
                self.assert_result(self.invoke(self.args(cache=store)), 1, "FAIL not-sqlite cache.sqlite3")

    def test_c2_5_temp_unavailable(self):
        # An otherwise valid database must not be touched when all scratch candidates are unsafe.
        spec = importlib.util.spec_from_file_location("clover_category_readiness", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stdout, stderr = io.StringIO(), io.StringIO()
        before = self.input_state()
        with patch.object(module, "_temp_candidates", return_value=[self.till_dir, self.root / "absent"]), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = module.main(self.args())
        result = subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())
        self.assert_result(result, 1, "FAIL temp-unavailable")
        self.assertEqual(self.input_state(), before)

    def test_c3_usage_exit_2(self):
        # Usage errors must not be turned into report findings or expose stray path arguments.
        for argv in ([], self.args() + ["--unknown", str(self.root)], self.args()[:-1],
                     self.args() + [f"--help={self.root}"]):
            result = self.invoke(argv)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout.splitlines()[-1:], [])
            self.assertIn("usage:", result.stderr)
            self.assertNotIn(str(self.root), result.stderr)

    def test_c4_read_only(self):
        # A direct SQLite open may create sidecars even for a checkpointed WAL-mode store.
        cache = self.till_dir / "checkpointed.sqlite3"
        self.make_cache(cache, [(["Mock Orchard"], 0)], wal=True)
        before = self.input_state()
        self.assert_result(self.invoke(self.args(cache=cache)), 0)
        self.assertEqual(self.input_state(), before)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_c5_no_private_values(self):
        # Report only counts and fixed errors, never source values or private paths.
        canaries = ["synthetic-message-canary", "synthetic-chat-canary", "synthetic-sender-canary",
                    "synthetic-full-id-canary", "ab01" * 16, "Mock Private Category"]
        text, chat, sender, identifier, digest, category = canaries
        self.products({"category": "fruit", "status": "active", "message": text, "chat": chat,
                       "sender": sender, "id": identifier, "digest": digest})
        self.write_json(self.mapping, {"fruit": category})
        cache = self.till_dir / "privacy.sqlite3"
        self.make_cache(cache, [([category, text], 0)])
        good = self.invoke(self.args(cache=cache))
        self.assertIn("shelf fruit till-items 1", self.assert_result(good, 0))
        self.write_json(self.mapping, {identifier: category})
        (self.content / "products.json").write_bytes(f'{{"{text}":'.encode())
        broken = self.invoke(self.args(cache=self.till_dir / "missing.sqlite3"))
        self.assert_result(broken, 1, "FAIL bad-category-map", "FAIL unreadable products",
                           "FAIL not-sqlite missing.sqlite3")
        for value in (*canaries, str(self.mapping), str(cache), str(self.content), str(self.root)):
            self.assertNotIn(value, good.stdout + good.stderr + broken.stdout + broken.stderr)

    def test_c6_zero_till_items_informational(self):
        # A mapped category with only a hidden match is not a readiness failure.
        cache = self.till_dir / "hidden.sqlite3"
        self.make_cache(cache, [(["Mock Orchard"], 1), (["Other category"], 0)])
        self.assertIn("shelf fruit till-items 0", self.assert_result(self.invoke(self.args(cache=cache)), 0))

    def test_c7_wal_rows_counted(self):
        # Immutable opens or main-file-only copies silently miss committed WAL rows.
        source = self.root / "wal-source.sqlite3"
        self.make_cache(source, wal=True)
        snapshot = self.till_dir / "wal-copy.sqlite3"
        with closing(sqlite3.connect(source)) as db:
            db.execute("PRAGMA wal_autocheckpoint=0")
            db.execute("INSERT INTO items VALUES (?, 0)", (json.dumps(["Mock Orchard"]),))
            db.commit()
            shutil.copyfile(source, snapshot)
            shutil.copyfile(source.with_name(source.name + "-wal"), snapshot.with_name(snapshot.name + "-wal"))
        self.assertFalse(snapshot.with_name(snapshot.name + "-shm").exists())
        before = self.input_state()
        lines = self.assert_result(self.invoke(self.args(cache=snapshot)), 0)
        self.assertIn("shelf fruit till-items 1", lines)
        self.assertEqual(self.input_state(), before)

    def test_c8_tmpdir_inside_input(self):
        # Even transient tempfile probes in an input tree would change a directory mtime.
        for directory in (self.map_dir, self.till_dir, self.content):
            nested = directory / "nested"
            nested.mkdir()
            alias = self.root / (directory.name + "-alias")
            alias.symlink_to(nested, target_is_directory=True)
            for candidate in (directory, nested, alias):
                with self.subTest(candidate=candidate):
                    before = self.input_state()
                    self.assertIn("shelf fruit till-items 1", self.assert_result(self.invoke(temp=candidate), 0))
                    self.assertEqual(self.input_state(), before)
                    self.assertEqual(list(self.scratch.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
