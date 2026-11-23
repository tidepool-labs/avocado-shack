"""Offline CLI contract tests for the Clover price parity report."""

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


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/clover_price_parity.py"
PASS = "PASS clover_price_parity"
FAIL = "FAIL clover_price_parity"
PRODUCT = {"id": "sample-fruit", "status": "active", "sellingPrice": "13.37"}
TILL_ID = "synthetic-clover-private-identifier"
SKU = "synthetic-private-sku"
ROW = (TILL_ID, 1337, "FIXED", "", 0, SKU)
SCHEMA = "CREATE TABLE items(id TEXT PRIMARY KEY, price_cents INTEGER, price_type TEXT, unit_name TEXT, hidden INTEGER, sku TEXT)"
INSERT = "INSERT INTO items VALUES (?, ?, ?, ?, ?, ?)"


class CloverPriceParityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.state = self.root / "state"
        self.clover = self.state / "clover"
        self.clover.mkdir(parents=True, mode=0o700)
        self.content = self.root / "content"
        self.content.mkdir()
        self.products = self.content / "products.json"
        self.links = self.clover / "links.json"
        self.cache = self.clover / "cache.sqlite3"
        self.args = ("--state", str(self.state), "--content", str(self.content))
        self.write_products(PRODUCT)
        self.write_links({PRODUCT["id"]: {"cloverId": TILL_ID, "sku": SKU}})
        self.make_store(self.cache)

    def write_products(self, *products):
        self.products.write_text(json.dumps({"products": products}), encoding="utf-8")

    def write_links(self, links):
        self.links.touch(mode=0o600)
        self.links.write_text(json.dumps(links), encoding="utf-8")

    def make_store(self, path, rows=(ROW,), *, schema=SCHEMA):
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute(schema)
            if rows:
                conn.executemany(INSERT, rows)

    def update_till(self, **fields):
        clause = ", ".join(f"{field} = ?" for field in fields)
        with closing(sqlite3.connect(self.cache)) as conn, conn:
            conn.execute(f"UPDATE items SET {clause}", tuple(fields.values()))

    def invoke(self, args=None, *, env=None):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *(self.args if args is None else args)],
            cwd=self.root, env=env, capture_output=True, text=True, timeout=10,
        )
        return result.returncode, result.stdout, result.stderr

    def assert_report(self, result, *, findings=(), counts=None):
        code, stdout, stderr = result
        self.assertEqual(code, int(bool(findings)), result)
        self.assertEqual(stderr, "")
        expected = [f"FAIL {reason}" for reason in findings] + [FAIL if findings else PASS]
        if counts is not None:
            labels = ("linked", "checked", "note no-site-price", "note till-absent")
            expected[:0] = [f"{label} {count}" for label, count in zip(labels, counts, strict=True)]
        self.assertEqual(stdout.splitlines(), expected)

    def input_tree(self):
        result = {}
        for root in (self.state, self.content):
            for path in (root, *root.rglob("*")):
                st = path.lstat()
                payload = (os.readlink(path) if path.is_symlink() else
                           path.read_bytes() if path.is_file() else None)
                result[path] = (st.st_mode, st.st_mtime_ns, payload)
        return result

    def stage_wal_store(self):
        """Copy while the writer is open; the destination has WAL but no SHM."""
        source = self.root / "wal-source.sqlite3"
        self.make_store(source, rows=())
        with closing(sqlite3.connect(source)) as conn:
            self.assertEqual(conn.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
            conn.execute("PRAGMA wal_autocheckpoint=0")
            with conn:
                conn.execute(INSERT, ROW)
            shutil.copyfile(source, self.cache)
            shutil.copyfile(str(source) + "-wal", str(self.cache) + "-wal")
        # The database alone has the schema but not the deciding row.
        bare = self.root / "bare.sqlite3"
        shutil.copyfile(self.cache, bare)
        with closing(sqlite3.connect(bare)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM items").fetchone(), (0,))

    def test_c1_full_pass(self):
        # Valid unit spellings and free prices pass; only linked active rows count.
        products = [PRODUCT]
        links = {PRODUCT["id"]: {"cloverId": TILL_ID, "sku": SKU}}
        rows: list[tuple[str, int | None, str, str, int, str]] = [
            ("sample-unpriced", None, "VARIABLE", "", 0, SKU),
        ]
        for pid, price, status in (
            ("sample-pound", "0.00 per lb", "active"),
            ("sample-lb", "0.00 per lb", "active"),
            ("sample-lbs", "0.00 per lb", "active"),
            ("sample-each", "0.00 each", "active"),
            ("sample-unpriced", None, "active"),
            ("sample-missing", "0.00", "active"),
            ("sample-held", "0.00", "held"),
        ):
            product = {"id": pid, "status": status}
            if price is not None:
                product["sellingPrice"] = price
            products.append(product)
            links[pid] = {"cloverId": pid, "sku": SKU}
        products.append({**PRODUCT, "id": "sample-unlinked"})
        for unit in ("Lb", "LBS", "Pound"):
            rows.append(("sample-" + unit.casefold(), 0, "PER_UNIT", unit, 0, SKU))
        rows.extend([("sample-each", 0, "FIXED", "", 0, SKU),
                     ("sample-held", None, "VARIABLE", "", 1, "")])
        with closing(sqlite3.connect(self.cache)) as conn, conn:
            conn.executemany(INSERT, rows)
        self.write_products(*products)
        self.write_links(links)
        self.assert_report(self.invoke(), counts=(7, 6, 1, 1))
        # A missing file is not malformed JSON or unsafe state.
        self.links.rename(self.root / "saved-links.json")
        self.assert_report(self.invoke(), counts=(0, 0, 0, 0))

    def test_c2_1_unsafe_state(self):
        # A following stat or permissive link reader would admit these inputs.
        reason = ("unsafe-state",)
        alias = self.root / "alias"
        alias.symlink_to(self.state, target_is_directory=True)
        for bad in (alias, self.root / "absent", self.products):
            with self.subTest(state=bad.name):
                self.assert_report(self.invoke(("--state", str(bad), *self.args[2:])), findings=reason)
        self.links.chmod(0o644)
        self.assert_report(self.invoke(), findings=reason)
        self.links.chmod(0o600)
        for bad in (b"[]", b"{", b"\xff", b'{"sample-fruit": 0}'):
            with self.subTest(links=bad):
                self.links.write_bytes(bad)
                self.assert_report(self.invoke(), findings=reason)
        self.write_links({})
        saved_links = self.links.rename(self.root / "saved-links.json")
        self.links.symlink_to(saved_links)
        self.assert_report(self.invoke(), findings=reason)
        saved_clover = self.clover.rename(self.root / "saved-clover")
        self.assert_report(self.invoke(), findings=reason)
        self.clover.symlink_to(saved_clover, target_is_directory=True)
        self.assert_report(self.invoke(), findings=reason)

    def test_c2_2_unreadable_products(self):
        # An absent, non-regular, undecodable or wrong-shaped catalogue cannot pass.
        reason = ("unreadable products",)
        for bad in (b"\xff", b"{", b"[]", b"{}", b'{"products":{}}'):
            with self.subTest(products=bad):
                self.products.write_bytes(bad)
                self.assert_report(self.invoke(), findings=reason)
        self.write_products({**PRODUCT, "sellingPrice": "13.370"})
        self.assert_report(self.invoke(), findings=reason)
        self.write_products(PRODUCT)
        saved = self.products.rename(self.root / "saved-products.json")
        self.assert_report(self.invoke(), findings=reason)
        self.products.symlink_to(saved)
        self.assert_report(self.invoke(), findings=reason)

    def test_c2_3_price_differs(self):
        # Being present is not enough: even one cent of drift is a finding.
        self.update_till(price_cents=1336)
        self.assert_report(self.invoke(), counts=(1, 1, 0, 0), findings=("price-differs sample-fruit",))

    def test_c2_4_unit_differs(self):
        # Neither type nor unit can substitute for the other on a per-pound item.
        cases = (("13.37 per lb", "FIXED", "lb"),
                 ("13.37 per lb", "PER_UNIT", "kg"),
                 ("13.37 each", "PER_UNIT", "lb"))
        for price, kind, unit in cases:
            with self.subTest(price=price, kind=kind, unit=unit):
                self.write_products({**PRODUCT, "sellingPrice": price})
                self.update_till(price_type=kind, unit_name=unit)
                self.assert_report(self.invoke(), counts=(1, 1, 0, 0), findings=("unit-differs sample-fruit",))

    def test_c2_5_till_no_price(self):
        # NULL is distinct from a differing price (and not a reason to skip the row).
        self.update_till(price_cents=None)
        self.assert_report(self.invoke(), counts=(1, 1, 0, 0), findings=("till-no-price sample-fruit",))

    def test_c2_6_till_hidden(self):
        # A priced item can still be invisible; a missing site price does not waive that.
        self.update_till(hidden=1)
        self.assert_report(self.invoke(), counts=(1, 1, 0, 0), findings=("till-hidden sample-fruit",))
        self.write_products({"id": PRODUCT["id"], "status": "active"})
        self.assert_report(self.invoke(), counts=(1, 1, 1, 0), findings=("till-hidden sample-fruit",))

    def test_c2_7_till_no_sku(self):
        # The saved link's SKU does not make up for an empty register SKU.
        self.update_till(sku="")
        self.assert_report(self.invoke(), counts=(1, 1, 0, 0), findings=("till-no-sku sample-fruit",))

    def test_c2_8_not_sqlite(self):
        # Never create a missing store, follow a sidecar symlink or swallow SQL errors.
        reason = ("not-sqlite cache.sqlite3",)
        for suffix in ("-wal", "-journal"):
            with self.subTest(suffix=suffix):
                sidecar = self.cache.with_name(self.cache.name + suffix)
                sidecar.symlink_to(self.root / "dangling")
                self.assert_report(self.invoke(), findings=reason)
                sidecar.rename(self.root / ("saved" + suffix))
                sidecar.mkdir()
                self.assert_report(self.invoke(), findings=reason)
                sidecar.rename(self.root / ("directory" + suffix))
        saved = self.cache.rename(self.root / "original.sqlite3")
        self.assert_report(self.invoke(), findings=reason)
        self.assertFalse(self.cache.exists())
        self.cache.symlink_to(saved)
        self.assert_report(self.invoke(), findings=reason)
        self.cache.rename(self.root / "alias.sqlite3")
        self.cache.write_bytes(b"not a SQLite store")
        self.assert_report(self.invoke(), findings=reason)
        for index, schema in enumerate(("CREATE TABLE other (id TEXT)",
                                        "CREATE TABLE items (id TEXT, sku TEXT)")):
            with self.subTest(schema=schema):
                self.cache.rename(self.root / f"old-{index}.sqlite3")
                self.make_store(self.cache, rows=(), schema=schema)
                self.assert_report(self.invoke(), findings=reason)

    def test_c2_9_temp_unavailable(self):
        # If every candidate is unsafe/unusable, no generic temp fallback may run.
        spec = importlib.util.spec_from_file_location("clover_price_parity", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stdout, stderr = io.StringIO(), io.StringIO()
        before = self.input_tree()
        with (patch.object(module, "_temp_candidates", return_value=(self.state, self.clover, self.root / "absent")),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            code = module.main(self.args)
        self.assert_report((code, stdout.getvalue(), stderr.getvalue()), findings=("temp-unavailable",))
        self.assertEqual(self.input_tree(), before)

    def test_c3_usage_exit_2(self):
        # Parser errors never enter the report or print its terminal marker.
        for args in ((), self.args[:2], self.args + ("--unknown",), self.args[:3]):
            with self.subTest(args=args):
                code, stdout, stderr = self.invoke(args)
                self.assertEqual((code, stdout), (2, ""))
                self.assertIn("usage:", stderr)
                self.assertNotIn(str(self.root), stderr)

    def test_c4_read_only(self):
        # A direct SQLite open can create SHM or checkpoint WAL, even with no SQL writes.
        self.stage_wal_store()
        before = self.input_tree()
        self.assert_report(self.invoke(), counts=(1, 1, 0, 0))
        self.assertEqual(self.input_tree(), before)

    def test_c5_no_private_values(self):
        # Reporting raw records, foreign IDs, or a parsing traceback leaks fixture data.
        canaries = ("synthetic-message-body", "synthetic-chat-key", "synthetic-sender-key",
                    "synthetic-digest-marker")
        self.write_products({**PRODUCT, **dict(zip(("message", "chat", "sender", "digest"), canaries))})
        self.update_till(price_cents=1299, hidden=1, price_type="PER_UNIT", sku=SKU)
        result = self.invoke()
        self.assert_report(result, counts=(1, 1, 0, 0), findings=(
            "price-differs sample-fruit", "unit-differs sample-fruit", "till-hidden sample-fruit",
        ))
        self.links.write_text(canaries[0], encoding="utf-8")
        refused = self.invoke()
        self.assert_report(refused, findings=("unsafe-state",))
        for canary in (*canaries, TILL_ID, SKU, str(self.state), str(self.content)):
            self.assertNotIn(canary, "".join(result[1:] + refused[1:]))

    def test_c6_no_amounts(self):
        # Neither decimal strings nor raw cents may appear in a discrepancy.
        self.update_till(price_cents=1299)
        result = self.invoke()
        self.assert_report(result, counts=(1, 1, 0, 0), findings=("price-differs sample-fruit",))
        for amount in ("13.37", "1337", "12.99", "1299"):
            self.assertNotIn(amount, "".join(result[1:]))

    def test_c7_wal_rows_counted(self):
        # Dropping the WAL can still open a valid DB, but misses the linked row.
        self.stage_wal_store()
        shm = self.cache.with_name(self.cache.name + "-shm")
        shm.symlink_to(self.root / "nonexistent-shm")  # SHM must not be read or copied.
        before = self.input_tree()
        self.assert_report(self.invoke(), counts=(1, 1, 0, 0))
        self.assertEqual(self.input_tree(), before)

    def test_c8_tmpdir_inside_input(self):
        # A temporary probe or directory later removed still changes the input mtime.
        nested = self.content / "nested"
        nested.mkdir()
        safe = self.root / "safe-temp"
        safe.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(nested, target_is_directory=True)
        for candidate in (self.state, nested, alias):
            with self.subTest(candidate=candidate.name):
                before = self.input_tree()
                env = {**os.environ, "TMPDIR": str(candidate), "TEMP": str(safe)}
                self.assert_report(self.invoke(env=env), counts=(1, 1, 0, 0))
                self.assertEqual(self.input_tree(), before)
                self.assertEqual(list(safe.iterdir()), [])
