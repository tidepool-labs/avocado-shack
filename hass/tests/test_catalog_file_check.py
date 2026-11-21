"""Offline CLI contract tests using disposable catalog and content copies."""

from datetime import date
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from hass import content_model, sitegen


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/catalog_file_check.py"
NAME = "Synthetic Private Product Name"
DESCRIPTION = "Synthetic canary description."
HOLD_REASON = "Synthetic canary hold reason."


def product(product_id, status="active"):
    record = {
        "id": product_id, "name": NAME, "description": DESCRIPTION, "producerKey": "test-maker",
        "brand": "Test Maker", "displayBrand": "Test Maker", "category": "fruit",
        "image": f"assets/products/{product_id}.webp", "status": status,
    }
    if status == "held":
        record["hold"] = {
            "reason": HOLD_REASON, "source": "https://example.com/fixture",
            "evidence": "Synthetic evidence", "record": "Synthetic record",
        }
    return record


class CatalogFileCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.content = self.root / "content-canary"
        self.content.mkdir()
        self.catalog = self.root / "catalog-canary.js"
        self.write_content([product("test-active")])
        self.write_catalog([{"id": "test-active"}])

    def write_json(self, name, record):
        (self.content / name).write_text(json.dumps({"schemaVersion": 1, **record}), encoding="utf-8")

    def write_content(self, products):
        self.write_json("products.json", {"products": products})
        self.write_json("makers.json", {"makers": {"test-maker": {
            "name": "Test Maker", "place": "Testville, California", "story": "A synthetic maker story.",
        }}})
        self.write_json("community.json", {
            "club": {"clubName": "Test Club", "organizer": "Test Organizer",
                     "intendedSender": "Test Sender", "emailConnected": False},
            "events": [], "routeIdeas": [],
        })
        self.write_json("store.json", {
            "name": "Test Store", "streetAddress": "1 Test Lane", "town": "Testville, California",
            "hours": ["Monday-Friday 9am-5pm", "Closed Saturday-Sunday"],
            "selection_checked_on": "2026-01-01",
        })

    def write_catalog(self, records, freshness=None):
        if freshness is None:
            freshness = {"selectionCheckedOn": None}
        self.catalog.write_text(f"const catalog={json.dumps(records)};\n"
                                f"const catalogFreshness={json.dumps(freshness)};\n", encoding="utf-8")

    def invoke(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def check(self, catalog=None, content=None):
        return self.invoke("--catalog", str(catalog or self.catalog), "--content", str(content or self.content))

    def assert_run(self, result, status, *lines):
        self.assertEqual(result.returncode, status, result.stderr)
        self.assertEqual(result.stderr, "")
        marker = "PASS" if status == 0 else "FAIL"
        self.assertEqual(result.stdout.splitlines(), [*lines, f"{marker} catalog_file_check"])

    def test_c1_full_pass(self):
        # A required-keys check or omission of optional/renderer fields from the allowlist would reject this.
        self.write_catalog([{"id": "test-active", "imageAlt": "Fixture alt text", "availabilityState": "yes",
                             "availabilityCheckedOn": "2026-01-01"}])
        self.assert_run(self.check(), 0, "records 1", "active 1")

    def test_c2_1_unsafe_input(self):
        # Following symlinks, checking existence alone, or omitting the size cap would admit these inputs.
        symlink_file = self.root / "catalog-link"
        symlink_file.symlink_to(self.catalog)
        symlink_dir = self.root / "content-link"
        symlink_dir.symlink_to(self.content, target_is_directory=True)
        oversized = self.root / "large.js"
        with oversized.open("wb") as handle:
            handle.truncate(5_000_001)
        for label, catalog, content in (
            ("catalog link", symlink_file, self.content), ("catalog directory", self.content, self.content),
            ("content link", self.catalog, symlink_dir), ("content file", self.catalog, self.catalog),
            ("oversized catalog", oversized, self.content),
        ):
            with self.subTest(label=label):
                self.assert_run(self.check(catalog, content), 1, "FAIL unsafe-input")

    def test_c2_2_content_invalid(self):
        # Parsing without validating can admit an unsupported schema; decoding failures must be classified too.
        for raw in (b'{"schemaVersion":2,"products":[]}', b'\xff'):
            with self.subTest(raw=raw):
                (self.content / "products.json").write_bytes(raw)
                self.assert_run(self.check(), 1, "FAIL content-invalid")

    def test_c2_3_catalog_unreadable(self):
        # Prefix-only or line-only parsing can accept broken assignments or the wrong JSON types.
        first = b'const catalog=[{"id":"test-active"}];\n'
        second = b'const catalogFreshness={"selectionCheckedOn":null};\n'
        for raw in (
            first, second, b" " + first + second, first + b" " + second,
            first.replace(b";", b"") + second, first + second.replace(b";", b""),
            first + second + b"// extra\n", b"const catalog=[;\n" + second,
            first + b"const catalogFreshness={;\n", b"const catalog={};\n" + second,
            first + b"const catalogFreshness=[];\n", b"const catalog=[null];\n" + second, b"\xff",
        ):
            with self.subTest(raw=raw):
                self.catalog.write_bytes(raw)
                self.assert_run(self.check(), 1, "FAIL catalog-unreadable")

    def test_c2_4_catalog_extra_field(self):
        # Two forbidden keys on one record must count as one affected record, not two keys.
        self.write_catalog([{"id": "test-active", "status": "active", "otherwiseUnknown": True}])
        self.assert_run(self.check(), 1, "records 1", "active 1", "FAIL catalog-extra-field 1")

    def test_c2_5_catalog_not_active(self):
        # Checking membership in all products rather than active products misses hidden listings.
        self.write_content([product("test-active"), product("beta-hidden", "hidden")])
        self.write_catalog([{"id": "beta-hidden"}, {"id": "test-active"}, {"id": "alpha-unknown"}])
        self.assert_run(self.check(), 1, "records 3", "active 1", "not-active alpha-unknown unknown",
                        "not-active beta-hidden hidden", "FAIL catalog-not-active 2")

    def test_c2_6_catalog_missing(self):
        # Checking only catalog rows misses omitted active products; hidden omissions are allowed.
        self.write_content([product("zeta-active"), product("alpha-active"), product("test-hidden", "hidden")])
        self.write_catalog([])
        self.assert_run(self.check(), 1, "records 0", "active 2", "missing alpha-active", "missing zeta-active",
                        "FAIL catalog-missing 2")

    def test_c2_7_catalog_duplicate(self):
        # Deduplicating up front hides duplicates; count repeated IDs rather than extra rows.
        self.write_catalog([{"id": "test-active"}] * 3)
        self.assert_run(self.check(), 1, "records 3", "active 1", "FAIL catalog-duplicate 1")

    def test_c2_8_freshness_shape(self):
        # A presence-only or subset-only check would accept one of these wrong key sets.
        for freshness in ({}, {"selectionCheckedOn": None, "extra": True}):
            with self.subTest(freshness=freshness):
                self.write_catalog([{"id": "test-active"}], freshness)
                self.assert_run(self.check(), 1, "records 1", "active 1", "FAIL freshness-shape")

    def test_c3_usage_exit_2(self):
        # A custom parser error path must preserve argparse's usage status and stderr/stdout split.
        for args in ((), ("--catalog",), ("--catalog", str(self.catalog), "--content", str(self.content), "--extra")):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage:"))
                self.assertEqual(result.stderr.splitlines()[-1], "catalog_file_check.py: error: invalid arguments (see --help)")

    def test_c4_read_only(self):
        # Rewriting even identical bytes changes mtimes; sidecar or temporary directory creation changes the tree.
        def snapshot():
            return {path.relative_to(self.root): (path.stat().st_mtime_ns,
                                                  path.read_bytes() if path.is_file() else None)
                    for path in [self.root, *self.root.rglob("*")]}

        before = snapshot()
        self.assert_run(self.check(), 0, "records 1", "active 1")
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Leaking raw records, a validator exception, or echoed argv can all expose input values.
        held = product("test-held", "held")
        self.write_content([product("test-active"), held])
        self.write_catalog([{"id": "test-active"}, held])
        findings = self.check()
        self.assert_run(findings, 1, "records 2", "active 1", "not-active test-held held",
                        "FAIL catalog-extra-field 1", "FAIL catalog-not-active 1")
        self.write_json("products.json", {"products": [product(NAME)]})
        invalid = self.check()
        self.assert_run(invalid, 1, "FAIL content-invalid")
        usage = self.invoke("--catalog", str(self.catalog), "--content", str(self.content), str(self.root))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (findings, invalid, usage):
            for canary in (NAME, DESCRIPTION, HOLD_REASON, str(self.root), str(self.content), str(self.catalog)):
                self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_held_listed(self):
        # Treating held as hidden or unknown erases the operator's reason to investigate a stale listing.
        self.write_content([product("test-active"), product("test-held", "held")])
        self.write_catalog([{"id": "test-active"}, {"id": "test-held"}])
        self.assert_run(self.check(), 1, "records 2", "active 1", "not-active test-held held",
                        "FAIL catalog-not-active 1")

    def test_c7_invalid_id_not_printed(self):
        # Unconditionally printing the ID would leak free text; dropping the row would undercount the finding.
        self.write_catalog([{"id": "test-active"}, {"id": NAME}])
        result = self.check()
        self.assert_run(result, 1, "records 2", "active 1", "note invalid-id 1", "FAIL catalog-not-active 1")
        self.assertNotIn(NAME, result.stdout + result.stderr)

    def test_c8_render_round_trip(self):
        # Handcrafted JS alone would not detect drift from the renderer's actual public output.
        active = product("test-active")
        active.update(name="Synthetic Piñata Fruit", available="yes", available_on="2026-01-01")
        self.write_content([active, product("test-held", "held")])
        content = content_model.load_and_validate(self.content, None)
        files = sitegen.render(content, today=date(2026, 1, 1))
        self.catalog.write_bytes(files["storefront-mockup/catalog-products.js"])
        self.assert_run(self.check(), 0, "records 1", "active 1")
