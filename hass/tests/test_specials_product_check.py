"""Fixture-only tests of the weekly-special product report's CLI contract."""

import contextlib
from datetime import date
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass.content_model import MAX_SPECIALS_STORED

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/specials_product_check.py"
TODAY = "2098-06-10"
PASS = "PASS specials_product_check"
FAIL = "FAIL specials_product_check"
TITLE = "Synthetic title canary"
DEAL = "Synthetic deal canary"
NAME = "Synthetic product canary"


def special(sid, **fields):
    return {"id": sid, "title": TITLE, "deal": DEAL, "order": 0,
            "start": "2098-06-01", "end": "2098-06-20", **fields}


def product(pid, status):
    return {"id": pid, "status": status, "name": NAME}


class SpecialsProductCheckTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(prefix="content-path-canary-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.store = self.root / "store.json"

    def fixture(self, *, products=(), **store):
        for name, payload in {
            "products": {"products": list(products)}, "makers": {"makers": {}},
            "community": {}, "store": store,
        }.items():
            (self.root / f"{name}.json").write_text(
                json.dumps({"schemaVersion": 1, **payload}), encoding="utf-8",
            )

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              cwd=self.root, capture_output=True, text=True, timeout=10)

    def check(self, content=None):
        return self.cli("--content", str(self.root if content is None else content), "--today", TODAY)

    def assert_result(self, result, code, *lines):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), list(lines))

    def report(self, stored, *, active=0, upcoming=0, ended=0, unreadable=0):
        return (f"stored {stored} of {MAX_SPECIALS_STORED}", f"active {active}",
                f"upcoming {upcoming}", f"ended {ended}", f"note unreadable-days {unreadable}")

    def test_c1_full_pass(self):
        # Ignoring storage totals or treating an active product as stale breaks a clean run.
        self.fixture(products=[product("sample-live", "active")], specials=[
            special("fixture-live", product="sample-live"),
            special("fixture-future", start="2098-06-18", product="sample-live"),
        ])
        self.assert_result(self.check(), 0, *self.report(2, active=1, upcoming=1), PASS)
        # Absent and empty lists must not emit a storage report.
        for store in ({}, {"specials": []}):
            with self.subTest(store=store):
                self.fixture(**store)
                self.assert_result(self.check(), 0, "specials none", PASS)

    def test_c2_1_unsafe_input(self):
        # A directory check alone follows a symlink to a valid copy.
        self.fixture()
        with TemporaryDirectory() as parent:
            alias = Path(parent) / "fixture-alias"
            alias.symlink_to(self.root, target_is_directory=True)
            for path in (alias, self.store, self.root / "missing"):
                with self.subTest(case=path.name):
                    self.assert_result(self.check(path), 1, "FAIL unsafe-input", FAIL)

    def test_c2_2_content_invalid(self):
        # A store-only reader would miss invalid content in a separate envelope.
        self.fixture()
        for raw in (b'{"schemaVersion": 2}', b'{bad json}', b'\xff'):
            with self.subTest(raw=raw):
                (self.root / "community.json").write_bytes(raw)
                self.assert_result(self.check(), 1, "FAIL content-invalid", FAIL)

    def test_c2_3_special_product_not_active(self):
        # Checking only existence misses hidden/held products; input order isn't ID order.
        self.fixture(products=[product("sample-hidden", "hidden"), product("sample-held", "held"), False],
                     specials=[special("fixture-z", product="sample-hidden"),
                               special("fixture-m", start="2098-06-19", product="sample-held"),
                               special("fixture-a", product="sample-missing"),
                               special("fixture-null", product=None),
                               special("fixture-bad-start", start="2098-02-30", product="sample-hidden"),
                               special("fixture-bad-end", start="2098-06-19", end=None, product="sample-held"),
                               17])
        self.assert_result(self.check(), 1, *self.report(7, active=3, upcoming=1, unreadable=2),
                           "note malformed 2", "special fixture-a product unknown",
                           "special fixture-m product held", "special fixture-null product unknown",
                           "special fixture-z product hidden", "FAIL special-product-not-active 4", FAIL)

    def test_c3_usage_exit_2(self):
        # Turning parser errors into findings or ignoring an invalid date changes the CLI protocol.
        content = ("--content", str(self.root))
        for args in ((), (*content, "--fixture-unknown"), (*content, "--today", "2098-06-31")):
            with self.subTest(case=args[-1] if args else "missing"):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last line on a usage error.
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # Rewriting identical JSON still changes mtime; creating a sidecar changes the inventory.
        self.fixture(specials=[special("fixture-stale", product="sample-missing")])

        def snapshot():
            return {path.relative_to(self.root): (path.stat().st_mtime_ns,
                                                  path.read_bytes() if path.is_file() else None)
                    for path in (self.root, *self.root.rglob("*"))}

        before = snapshot()
        self.assert_result(self.check(), 1, *self.report(1, active=1),
                           "special fixture-stale product unknown", "FAIL special-product-not-active 1", FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # A row dump, traceback or argparse echo can leak content or the copy's location.
        self.fixture(products=[product("sample-hidden", "hidden")], specials=[
            special("fixture-private", product="sample-hidden"),
        ])
        finding = self.check()
        usage = self.cli("--fixture-unknown", str(self.root), "--content", str(self.root))
        for result in (finding, usage):
            for canary in (TITLE, DEAL, NAME, str(self.root)):
                self.assertFalse(canary in result.stdout or canary in result.stderr, "private value leaked")
        self.assert_result(finding, 1, *self.report(1, active=1),
                           "special fixture-private product hidden", "FAIL special-product-not-active 1", FAIL)
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))

    def test_c6_ended_not_finding(self):
        # Reporting every stale reference would alarm on historical specials.
        self.fixture(products=[product("sample-held", "held")], specials=[
            special("fixture-ended", end="2098-06-09", product="sample-held"),
        ])
        self.assert_result(self.check(), 0, *self.report(1, ended=1), PASS)

    def test_c7_last_day_inclusive(self):
        # An exclusive end comparison would miss this stale product on its last day.
        self.fixture(products=[product("sample-held", "held")], specials=[
            special("fixture-last-day", end=TODAY, product="sample-held"),
        ])
        self.assert_result(self.check(), 1, *self.report(1, active=1),
                           "special fixture-last-day product held", "FAIL special-product-not-active 1", FAIL)

    def test_c8_no_product_ok(self):
        # A missing product key is intentional, not unresolvable; omitted --today uses the shop day.
        self.fixture(specials=[special("fixture-standalone")])
        spec = importlib.util.spec_from_file_location("specials_product_check", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        out, err = io.StringIO(), io.StringIO()
        with (patch.object(module.content_model, "shop_today", return_value=date.fromisoformat(TODAY)),
              contextlib.redirect_stdout(out), contextlib.redirect_stderr(err)):
            code = module.main(["--content", str(self.root)])
        self.assertEqual((code, err.getvalue()), (0, ""))
        self.assertEqual(out.getvalue().splitlines(), [*self.report(1, active=1), PASS])
