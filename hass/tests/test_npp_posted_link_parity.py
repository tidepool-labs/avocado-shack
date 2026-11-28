"""Offline contract tests for the NPP posted-link parity command."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_posted_link_parity.py"
SPEC = importlib.util.spec_from_file_location("npp_posted_link_parity", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
parity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parity)

FIRST = "photo-product-001"
SECOND = "photo-product-002"
SYNTHETIC_SITE = "https://shop.example.invalid"
SYNTHETIC_SHOP = 'const link = `href="?item=${esc(encodeURIComponent(p.id))}#market"`;'
GOLDEN_PREFIX = "hass-gallery-style/golden/"
PASS = "PASS npp_posted_link_parity"
FAIL = "FAIL npp_posted_link_parity"
LIVE_COUNTS = ["products 170", "records 172", "goldens 12"]


def row(product_id, status="active"):
    return {"id": product_id, "name": "Fixture product", "status": status}


def golden(stem, fragment="market"):
    return json.dumps({"card": {"link_to_this": f"{SYNTHETIC_SITE}/?item={stem}#{fragment}"}}).encode()


class NppPostedLinkParityTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.products = self.root / "products.json"
        self.shop = self.root / "shop.js"
        self.write_products(row(FIRST))
        self.shop.write_text(SYNTHETIC_SHOP, encoding="utf-8")
        self.files = {f"{GOLDEN_PREFIX}{FIRST}.json": golden(FIRST)}
        self.replies = {"confirm": {"posted": "Fixture: {url}"}}

    def write_products(self, *records):
        self.products.write_text(json.dumps({"products": records}), encoding="utf-8")

    def run_fixture(self, *, products=None, shop=None, use_real_assets=False, site=SYNTHETIC_SITE,
                    assets_error=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (patch.object(parity, "PRODUCTS", products if products is not None else self.products),
              patch.object(parity, "SHOP", shop if shop is not None else self.shop),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            if use_real_assets:
                code = parity.main([])
            else:
                with (patch.object(parity.publish_live, "URL", SYNTHETIC_SITE),
                      patch.object(parity.reply, "SITE", site),
                      patch.object(parity.npp, "assets", return_value=({}, self.files, self.replies),
                                   side_effect=assets_error)):
                    code = parity.main([])
        return subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())

    def run_with_input(self, name, path):
        return self.run_fixture(products=path) if name == "products" else self.run_fixture(shop=path)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=20)

    def assert_output(self, result, code, lines):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stdout, "\n".join(lines) + "\n")
        self.assertEqual(result.stderr, "")

    def assert_findings(self, result, *reasons):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual([line for line in result.stdout.splitlines() if line.startswith("FAIL ")],
                         [*(f"FAIL {reason}" for reason in reasons), FAIL])
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual(result.stderr, "")

    def test_c1_full_pass(self):
        # Matching sources must return success rather than only printing counts.
        self.assert_output(self.run_fixture(), 0, ["products 1", "records 1", "goldens 1", PASS])

    def test_c2_findings_trailer(self):
        # An early site finding must not suppress independent later findings.
        self.write_products(row(FIRST), row("Fixture Invalid", "inactive"))
        self.files[f"{GOLDEN_PREFIX}{FIRST}.json"] = golden(FIRST, "other")
        self.shop.write_text("// no link", encoding="utf-8")
        self.assert_findings(self.run_fixture(site="https://other.example.invalid"),
                             "site-differs", "posted-link-mismatch 1", "id-refused 1",
                             f"golden-link {FIRST}", "js-link-missing")

    def test_c2_1_input_unsafe(self):
        # Following a symlink to valid content would incorrectly pass.
        for name, target in (("products", self.products), ("shop", self.shop)):
            alias = self.root / f"{name}-alias"
            alias.symlink_to(target)
            for path in (alias, self.root):
                with self.subTest(name=name, symlink=path == alias):
                    self.assert_output(self.run_with_input(name, path), 1,
                                       [f"FAIL input-unsafe {name}", FAIL])

    def test_c2_2_input_too_large(self):
        # Oversize files are classified before decode; exactly the cap is allowed.
        for name, cap, path in (("products", 2_000_000, self.products),
                                ("shop", 1_000_000, self.shop)):
            fixture = self.root / f"{name}-size"
            data = path.read_bytes()
            with self.subTest(name=name):
                fixture.write_bytes(data.ljust(cap, b" "))
                self.assert_output(self.run_with_input(name, fixture), 0,
                                   ["products 1", "records 1", "goldens 1", PASS])
                with fixture.open("ab") as stream:
                    stream.write(b"\xff")
                self.assert_output(self.run_with_input(name, fixture), 1,
                                   [f"FAIL input-too-large {name}", FAIL])

    def test_c2_3_input_unreadable(self):
        # Filesystem, decode and schema errors must not escape or look like drift.
        cases = [
            ("products", "missing", None), ("shop", "missing", None),
            ("products", "utf8", b"\xff"), ("shop", "utf8", b"\xff"),
            ("products", "json", b"{"),
            ("products", "top-level shape", b"[]"),
            ("products", "list shape", b'{"products":{}}'),
            ("products", "record shape", b'{"products":[null]}'),
            ("products", "field shape", b'{"products":[{"id":"valid","name":0,"status":"active"}]}'),
            ("products", "missing field", b'{"products":[{"id":"valid","status":"active"}]}'),
        ]
        for index, (name, label, data) in enumerate(cases):
            with self.subTest(name=name, label=label):
                path = self.root / f"input-{index}"
                if data is not None:
                    path.write_bytes(data)
                self.assert_output(self.run_with_input(name, path), 1,
                                   [f"FAIL input-unreadable {name}", FAIL])

    def test_c2_4_assets_unreadable(self):
        # Neither loader exceptions nor broken golden JSON may leak their text.
        with self.subTest(source="loader"):
            self.assert_findings(self.run_fixture(assets_error=RuntimeError("fixture detail")),
                                 "assets-unreadable")
        with self.subTest(source="golden"):
            self.files[f"{GOLDEN_PREFIX}{FIRST}.json"] = b'{"fixture detail"'
            self.assert_findings(self.run_fixture(), "assets-unreadable")

    def test_c2_5_site_differs(self):
        # An empty active set does not excuse disagreeing site constants.
        self.write_products(row(FIRST, "inactive"))
        self.assert_findings(self.run_fixture(site="https://other.example.invalid"), "site-differs")

    def test_c2_6_posted_link_mismatch(self):
        # A reply template that drops the link affects only exactly-active rows.
        self.write_products(row(FIRST), row(SECOND), row("fixture-inactive", "Active"))
        self.replies["confirm"]["posted"] = "Fixture without a link"
        self.assert_findings(self.run_fixture(), "posted-link-mismatch 2")

    def test_c2_7_id_refused(self):
        # An inactive ID still needs to be accepted; an active refused ID cannot render.
        self.write_products(row("Invalid Active"), row("Invalid Inactive", "inactive"), row(FIRST))
        self.assert_findings(self.run_fixture(), "posted-link-mismatch 1", "id-refused 2")

    def test_c2_8_golden_link(self):
        # Traversal order must be sorted and valid JSON with no link is still drift.
        self.files.clear()
        self.files[f"{GOLDEN_PREFIX}{SECOND}.json"] = b'{"card":{}}'
        self.files[f"{GOLDEN_PREFIX}{FIRST}.json"] = golden(FIRST, "other")
        self.files[f"another-directory/{FIRST}.json"] = b"not json"
        self.assert_findings(self.run_fixture(), f"golden-link {FIRST}", f"golden-link {SECOND}")

    def test_c2_9_js_link_missing(self):
        # A similar anchor with different encoding is not the shop contract.
        self.shop.write_text(SYNTHETIC_SHOP.replace("encodeURIComponent(p.id)", "p.id"), encoding="utf-8")
        self.assert_findings(self.run_fixture(), "js-link-missing")

    def test_c2_10_stem_invalid(self):
        # Even matching links do not legitimize or expose an untrusted asset name.
        for stem in ("fixture\nFAIL marker", "photo-product-1234567", "photo-product-١"):
            with self.subTest(stem=stem):
                self.files = {f"{GOLDEN_PREFIX}{stem}.json": golden(stem)}
                self.assert_output(self.run_fixture(), 1,
                                   ["products 1", "records 1", "goldens 1", "FAIL stem-invalid", FAIL])

    def test_c3_usage_exit_2(self):
        # No positional argument or switch (including --help) is part of this CLI.
        for arg in ("fixture", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("error: unrecognized arguments:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Catch cache, sidecar or rewritten-input regressions in the real checkout.
        def snapshot():
            entries = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (tree, *tree.rglob("*")):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        self.assert_output(self.run_cli(), 0, [*LIVE_COUNTS, PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Products may carry arbitrary text; only counts and fixed labels are emitted.
        self.write_products(row("fixture\nmarker"), row("fixture-hidden", "fixture\nstatus"))
        self.assert_output(self.run_fixture(), 1, ["products 1", "records 2", "goldens 1",
                                                  "FAIL posted-link-mismatch 1", "FAIL id-refused 1", FAIL])

    def test_c6_fixture_pass(self):
        # Fixture counts and real pinned reply assets must coexist in one run.
        shutil.copyfile(ROOT / "storefront-mockup/shop.js", self.shop)
        self.assert_output(self.run_fixture(use_real_assets=True), 0,
                           ["products 1", "records 1", "goldens 12", PASS])

    def test_c7_live_pins(self):
        # The default path checks the checked-in catalog, not synthetic inputs.
        self.assert_output(self.run_cli(), 0, [*LIVE_COUNTS, PASS])
