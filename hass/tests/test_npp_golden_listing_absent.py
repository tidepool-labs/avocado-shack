"""NPP acceptance runner: a golden case starts from the catalog as it was before its product was listed.

Each golden case (1-12) replays the owner first listing a product that is live today; the case's ``golden`` names
that product's own catalog row (``photo-product-NNN``). The runner's sandbox copied today's catalog, so the product
was already there and the real duplicate guard rightly asked "That looks like an existing listing. Do you want to add
another?" whenever the owner named it exactly as listed (case 7, "Dried mushrooms"), and the case could never pass.

Contract: for a golden view the runner removes exactly that one row from the sandbox products.json and from the
sandbox's frozen migration baseline, in one signed commit before the conversation starts; the migration check still
passes; the duplicate guard no longer sees the product; every other product, maker and file is unchanged. A view
without a golden changes nothing, and a golden whose row is missing or repeated fails loudly instead of silently
running against the wrong catalog. Production code and the repository's own catalog are never touched.
Fixtures only: no model, network or private recording.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_npp = _load("npp_run_golden_listing_absent_under_test", ROOT / "hass" / "tests" / "npp" / "run_npp.py")
from hass import migration_check  # noqa: E402
from hass.npp import missing  # noqa: E402
from hass.tests.test_catalog_ops import CatalogRepo  # noqa: E402
from hass.tests.test_editor import git  # noqa: E402

CASE7 = ROOT / "hass" / "tests" / "npp" / "cases" / "case-07-golden-dried-mushrooms.json"


def _products(wt):
    return json.loads((Path(wt) / "hass" / "content" / "products.json").read_text("utf-8"))["products"]


def _baseline(wt):
    return json.loads((Path(wt) / "hass" / "content" / "migration-baseline.json").read_text("utf-8"))


class GoldenListingAbsent(unittest.TestCase):
    def setUp(self):
        self.repo = CatalogRepo()
        self.addCleanup(self.repo._tmp.cleanup)
        self.wt = self.repo.wt
        self.view = json.loads(CASE7.read_text("utf-8"))
        self.pid = Path(self.view["golden"]).stem

    def test_case7_golden_row_is_in_todays_catalog_and_trips_the_duplicate_guard(self):
        products = _products(self.wt)
        row = [p for p in products if p["id"] == self.pid]
        self.assertEqual(len(row), 1)
        self.assertEqual(missing._duplicates("Dried Mushrooms", products, {}, None), ("catalog",))

    def test_removes_exactly_the_golden_row_in_one_signed_commit(self):
        before_products, before_base = _products(self.wt), _baseline(self.wt)
        head = git(self.wt, "rev-parse", "HEAD").strip()
        self.assertEqual(run_npp.golden_listing_absent(self.wt, self.view, git), self.pid)
        after_products, after_base = _products(self.wt), _baseline(self.wt)
        self.assertEqual(after_products, [p for p in before_products if p["id"] != self.pid])
        self.assertEqual(len(after_products), len(before_products) - 1)
        self.assertEqual(after_base["listings"]["ids"], [i for i in before_base["listings"]["ids"] if i != self.pid])
        self.assertEqual(after_base["listings"]["count"], before_base["listings"]["count"] - 1)
        self.assertEqual({k: v for k, v in after_base.items() if k != "listings"},
                         {k: v for k, v in before_base.items() if k != "listings"})
        self.assertEqual(git(self.wt, "rev-list", "--count", f"{head}..HEAD").strip(), "1")
        changed = set(git(self.wt, "show", "--name-only", "--format=", "HEAD").split())
        self.assertTrue({"hass/content/migration-baseline.json", "hass/content/products.json"} <= changed)
        generated = changed - {"hass/content/migration-baseline.json", "hass/content/products.json"}
        self.assertIn("storefront-mockup/catalog-products.js", generated)  # the site follows the catalog
        self.assertTrue(all(p.startswith("storefront-mockup/") for p in generated), generated)
        self.assertIn("Signed-off-by:", git(self.wt, "log", "-1", "--format=%B"))
        self.assertEqual(git(self.wt, "status", "--porcelain").strip(), "")

    def test_sandbox_still_passes_the_migration_check_and_the_guard_no_longer_fires(self):
        run_npp.golden_listing_absent(self.wt, self.view, git)
        failures, _ = migration_check.run_checks(self.wt)
        self.assertEqual(failures, [])
        self.assertEqual(missing._duplicates("Dried Mushrooms", _products(self.wt), {}, None), ())
        # Another live product is still a duplicate: only the golden's own row went.
        other = next(p for p in _products(self.wt) if p.get("status") == "active")
        self.assertEqual(missing._duplicates(other["name"], _products(self.wt), {}, None), ("catalog",))

    def test_repository_catalog_is_untouched(self):
        repo_products = (ROOT / "hass" / "content" / "products.json").read_bytes()
        run_npp.golden_listing_absent(self.wt, self.view, git)
        self.assertEqual((ROOT / "hass" / "content" / "products.json").read_bytes(), repo_products)

    def test_view_without_golden_changes_nothing(self):
        head = git(self.wt, "rev-parse", "HEAD").strip()
        before = _products(self.wt)
        view = {k: v for k, v in self.view.items() if k != "golden"}
        self.assertIsNone(run_npp.golden_listing_absent(self.wt, view, git))
        self.assertEqual(git(self.wt, "rev-parse", "HEAD").strip(), head)
        self.assertEqual(_products(self.wt), before)

    def test_missing_or_repeated_golden_row_fails_loudly(self):
        head = git(self.wt, "rev-parse", "HEAD").strip()
        with self.assertRaises(ValueError):
            run_npp.golden_listing_absent(self.wt, {**self.view, "golden": "hass-gallery-style/golden/no-such.json"}, git)
        path = Path(self.wt) / "hass" / "content" / "products.json"
        data = json.loads(path.read_text("utf-8"))
        row = next(p for p in data["products"] if p["id"] == self.pid)
        path.write_text(json.dumps({**data, "products": [*data["products"], row]}, indent=2) + "\n", "utf-8")
        with self.assertRaises(ValueError):
            run_npp.golden_listing_absent(self.wt, self.view, git)
        self.assertEqual(git(self.wt, "rev-parse", "HEAD").strip(), head)

    def test_every_golden_case_names_exactly_one_catalog_row(self):
        products = _products(self.wt)
        goldens = [c for c in run_npp.load_cases().values() if c.get("golden")]
        self.assertEqual(len(goldens), 12)
        for case in goldens:
            with self.subTest(case=case["id"]):
                pid = Path(case["golden"]).stem
                self.assertEqual(sum(p["id"] == pid for p in products), 1)


if __name__ == "__main__":
    unittest.main()
