"""Offline CLI contracts for the Clover inventory preview."""

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

from hass.clover import cache

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/clover_sku_preview.py"
SPEC = importlib.util.spec_from_file_location("clover_sku_preview", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
preview = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preview)
PASS = "PASS clover_sku_preview"
FAIL = "FAIL clover_sku_preview"


def product(pid, name="Blue Mug", category="pantry", status="active", **extra):
    return dict(id=pid, name=name, category=category, status=status, **extra)


def item(iid, name, sku="", *, code="", hidden=False):
    return (iid, name, sku, code, None, "VARIABLE", "", "[]", "[]", hidden, True, None, None, 0)


class CloverSkuPreviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / "state"
        self.clover = self.state / "clover"
        self.clover.mkdir(parents=True)
        self.store = self.clover / "cache.sqlite3"
        self.links = self.clover / "links.json"
        self.content = self.root / "content"
        self.content.mkdir()
        self.products = self.content / "products.json"
        self.safe_temp = self.root / "safe-temp"
        self.safe_temp.mkdir()
        self.write_products(product("one"))
        self.seed_store()

    def write_products(self, *products):
        self.products.write_text(json.dumps({"products": products}), encoding="utf-8")

    def write_links(self, links):
        self.links.write_text(json.dumps(links), encoding="utf-8")
        self.links.chmod(0o600)

    def insert_items(self, db, rows):
        db.executemany("INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        db.commit()

    def seed_store(self, *rows):
        with closing(sqlite3.connect(self.store)) as db:
            db.executescript(cache.SCHEMA)
            self.insert_items(db, rows)

    def args(self, state=None, content=None):
        return ["--state", str(state or self.state), "--content", str(content or self.content)]

    def invoke(self, argv=None):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *(self.args() if argv is None else argv)],
            capture_output=True, text=True, cwd=self.root, timeout=10,
        )
        return result.returncode, result.stdout.splitlines(), result.stderr

    def invoke_main(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = preview.main(self.args())
        return status, out.getvalue().splitlines(), err.getvalue()

    def assert_result(self, result, code, last):
        status, lines, stderr = result
        self.assertEqual(status, code, (lines, stderr))
        self.assertTrue(lines)
        self.assertEqual(lines[-1], last)
        self.assertEqual(stderr, "")
        return lines[:-1]

    def assert_finding(self, result, reason):
        lines = self.assert_result(result, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [f"FAIL {reason}"])
        return lines

    def input_snapshot(self):
        paths = [self.state, self.content, *self.state.rglob("*"), *self.content.rglob("*")]
        return {p: (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None) for p in paths}

    def test_c1_full_pass(self):
        # Filter by link key and active status, and don't reserve this preview's own proposals.
        self.write_links({"linked": {"cloverId": "synthetic-linked-item"}})
        self.seed_store(item("twin", "  GOLD   MUG "), item("reserved", "Other", code="as-pan-blue-mug-01"))
        self.write_products(
            product("one"), product("two", "Blue and Mug"), product("three", "Blue & Mug"),
            product("four", "Green Mug"), product("five", "Gold Mug"), product("six", "!!!"),
            product("seven", category="unsupported"), product("linked"),
            product("hidden", status="hidden"), product("held", status="held"),
        )
        self.assertEqual(self.assert_result(self.invoke(), 0, PASS), [
            "sku one AS-PAN-BLUE-MUG-02", "sku two AS-PAN-BLUE-MUG-02", "sku three AS-PAN-BLUE-MUG-02",
            "sku four AS-PAN-GREEN-MUG-01", "note till-twin five", "note name-refused six",
            "note category-unsupported seven", "unlinked 7", "previewed 4", "note same-preview-sku 1",
        ])
        # A startup-time copy of CATEGORIES would still accept pantry here.
        with patch.object(preview.mapper, "CATEGORIES", ()):
            lines = self.assert_result(self.invoke_main(), 0, PASS)
        self.assertIn("note category-unsupported one", lines)
        self.assertIn("previewed 0", lines)

    def test_c2_1_unsafe_state(self):
        # Checking is_dir alone can follow state/clover links; ordinary JSON opens ignore file permissions.
        alias = self.root / "state-alias"
        alias.symlink_to(self.state, target_is_directory=True)
        for state in (alias, self.store, self.root / "absent"):
            with self.subTest(state=state.name):
                self.assert_finding(self.invoke(self.args(state=state)), "unsafe-state")
        for kind in ("symlink", "file"):
            with self.subTest(clover=kind):
                state = self.root / kind
                state.mkdir()
                target = state / "clover"
                if kind == "symlink":
                    target.symlink_to(self.clover, target_is_directory=True)
                else:
                    target.touch()
                self.assert_finding(self.invoke(self.args(state=state)), "unsafe-state")
        self.links.symlink_to(self.root / "absent-links")
        self.assert_finding(self.invoke(), "unsafe-state")
        self.links.unlink()
        self.links.mkdir()
        self.assert_finding(self.invoke(), "unsafe-state")
        self.links.rmdir()
        self.write_links({})
        self.links.chmod(0o644)
        self.assert_finding(self.invoke(), "unsafe-state")
        self.links.chmod(0o600)
        for raw in (b"[]", b"{", b"\xff"):
            with self.subTest(raw=raw):
                self.links.write_bytes(raw)
                self.assert_finding(self.invoke(), "unsafe-state")

    def test_c2_2_unreadable_products(self):
        # An absent, linked, malformed or wrong-shaped catalog must not pass as empty.
        self.products.unlink()
        self.assert_finding(self.invoke(), "unreadable products")
        target = self.root / "other-products.json"
        target.write_text('{"products": []}', encoding="utf-8")
        self.products.symlink_to(target)
        self.assert_finding(self.invoke(), "unreadable products")
        self.products.unlink()
        for raw in (b"\xff", b"{", b"[]", b"{}", b'{"products":{}}'):
            with self.subTest(raw=raw):
                self.products.write_bytes(raw)
                self.assert_finding(self.invoke(), "unreadable products")

    def test_c2_3_sku_exhausted(self):
        # SkuExhausted is a MapError subclass but must fail, and other products still run.
        self.seed_store(*(item(f"taken-{n}", "Other", f"AS-PAN-BLUE-MUG-{n:02d}") for n in range(1, 100)))
        self.write_products(product("one"), product("two", "Green Mug"))
        self.assertEqual(self.assert_finding(self.invoke(), "sku-exhausted one"), [
            "FAIL sku-exhausted one", "sku two AS-PAN-GREEN-MUG-01",
            "unlinked 2", "previewed 1", "note same-preview-sku 0",
        ])

    def test_c2_4_not_sqlite(self):
        # Validate per-leaf type and schema even when no rows exist.
        reason = "not-sqlite cache.sqlite3"
        for suffix in ("-wal", "-journal"):
            sidecar = self.clover / (self.store.name + suffix)
            for kind in ("symlink", "directory"):
                with self.subTest(suffix=suffix, kind=kind):
                    if kind == "symlink":
                        sidecar.symlink_to(self.store)
                    else:
                        sidecar.mkdir()
                    self.assert_finding(self.invoke(), reason)
                    if kind == "symlink":
                        sidecar.unlink()
                    else:
                        sidecar.rmdir()
        target = self.root / "valid-store"
        self.store.rename(target)
        self.assert_finding(self.invoke(), reason)
        self.store.symlink_to(target)
        self.assert_finding(self.invoke(), reason)
        self.store.unlink()
        self.store.mkdir()
        self.assert_finding(self.invoke(), reason)
        self.store.rmdir()
        with closing(sqlite3.connect(self.store)) as db:
            db.execute("CREATE TABLE unrelated (id TEXT)")
            self.assert_finding(self.invoke(), reason)
            db.execute("CREATE TABLE items (id TEXT)")
            self.assert_finding(self.invoke(), reason)
        self.store.write_bytes(b"not a database")
        self.assert_finding(self.invoke(), reason)

    def test_c2_5_temp_unavailable(self):
        # Exhausting safe parents is neither a SQLite failure nor permission to write in an input.
        before = self.input_snapshot()
        with patch.object(preview, "_temp_candidates", return_value=[self.store, self.state, self.clover, self.content]):
            self.assert_finding(self.invoke_main(), "temp-unavailable")
        self.assertEqual(self.input_snapshot(), before)

    def test_c3_usage_exit_2(self):
        # CLI misuse must be owned by argparse, before any findings are emitted.
        for argv in ([], ["--state"], self.args() + ["--unknown", str(self.content)]):
            with self.subTest(argv=argv):
                status, lines, err = self.invoke(argv)
                self.assertEqual((status, lines), (2, []))  # No last stdout line exists.
                self.assertTrue(err.startswith("usage:"))
                self.assertNotIn(str(self.root), err)

    def test_c4_read_only(self):
        # Opening the original in WAL mode can create then remove sidecars even with no WAL rows.
        with closing(sqlite3.connect(self.store)) as db:
            db.execute("PRAGMA journal_mode=WAL").fetchone()
        self.write_links({})
        before = self.input_snapshot()
        with patch.object(preview, "_temp_candidates", return_value=[self.safe_temp]):
            self.assert_result(self.invoke_main(), 0, PASS)
        self.assertEqual(self.input_snapshot(), before)
        self.assertEqual(list(self.safe_temp.iterdir()), [])

    def test_c5_no_private_values(self):
        # Report fields only, not raw records, exception detail or input paths on success or refusal.
        canaries = ("synthetic message canopy", "synthetic-chat-canary", "synthetic-sender-canary",
                    "SYNTHETICPRIVATEITEM", "a7" * 32)
        message, chat, sender, item_id, digest = canaries
        self.seed_store(item(item_id, "Blue Mug", code=digest))
        self.write_products(product("one", description=message, chat=chat, sender=sender))
        self.write_links({"unused": {"cloverId": item_id, "digest": digest}})
        passed = self.invoke()
        self.assertIn("note till-twin one", self.assert_result(passed, 0, PASS))
        self.products.write_text(f'{{"description": "{message}",', encoding="utf-8")
        refused = self.invoke()
        self.assert_finding(refused, "unreadable products")
        for _, lines, stderr in (passed, refused):
            for canary in (*canaries, str(self.state), str(self.content), str(self.root)):
                self.assertNotIn(canary, "\n".join(lines) + stderr)

    def test_c6_hidden_twin_rule(self):
        # A hidden item is not a twin but still occupies its SKU number.
        self.seed_store(item("synthetic-hidden", "Blue Mug", "AS-PAN-BLUE-MUG-01", hidden=True))
        self.assertEqual(self.assert_result(self.invoke(), 0, PASS), [
            "sku one AS-PAN-BLUE-MUG-02", "unlinked 1", "previewed 1", "note same-preview-sku 0",
        ])

    def test_c7_wal_rows_counted(self):
        # A base-file-only or immutable read would miss a committed visible twin.
        source = self.root / "wal-source.sqlite3"
        with closing(sqlite3.connect(source)) as db:
            db.executescript(cache.SCHEMA)
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
            db.execute("PRAGMA wal_autocheckpoint=0")
            self.insert_items(db, [item("wal-twin", "Blue Mug")])
            shutil.copyfile(source, self.store)
            self.assertIn("sku one AS-PAN-BLUE-MUG-01", self.assert_result(self.invoke(), 0, PASS))
            shutil.copyfile(str(source) + "-wal", str(self.store) + "-wal")
        self.assertFalse(self.store.with_name(self.store.name + "-shm").exists())
        before = self.input_snapshot()
        self.assertEqual(self.assert_result(self.invoke(), 0, PASS), [
            "note till-twin one", "unlinked 1", "previewed 0", "note same-preview-sku 0",
        ])
        self.assertEqual(self.input_snapshot(), before)

    def test_c8_tmpdir_inside_input(self):
        # tempfile's implicit parent probe can leave no file yet change a directory's mtime.
        nested = self.clover / "nested"
        nested.mkdir()
        alias = self.root / "tmp-alias"
        alias.symlink_to(nested, target_is_directory=True)
        for path in (self.state, nested, alias, self.content):
            with self.subTest(tmpdir=path.name):
                before = self.input_snapshot()
                with patch.dict(os.environ, {"TMPDIR": str(path), "TEMP": str(self.safe_temp), "TMP": ""}):
                    self.assertEqual(self.assert_result(self.invoke(), 0, PASS), [
                        "sku one AS-PAN-BLUE-MUG-01", "unlinked 1", "previewed 1", "note same-preview-sku 0",
                    ])
                self.assertEqual(self.input_snapshot(), before)
                self.assertEqual(list(self.safe_temp.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
