"""RF1939-5 tests: product and maker add/edit refuse a text over its TEXT_LIMITS limit, naming the field and limit.

Runs the production op registry on a throwaway writer repo (test_catalog_ops.CatalogRepo); nothing touches the checkout.
"""

import unittest

from hass.tests.test_catalog_ops import NEW, CatalogTestCase

PID = "photo-product-001"
MAKER = {"key": "Test Farm", "name": "Test Farm", "place": "Somewhere, California", "story": "Grows things.",
         "url": "https://example.com/about"}
PRODUCT_LIMITS = {"name": 80, "brand": 60, "displayBrand": 60, "description": 600}
MAKER_LIMITS = {"name": 80, "place": 60, "story": 600}


class CatalogLimitTests(CatalogTestCase):
    def assertLong(self, repo, reason, *ops):
        result = self.assertRejected(repo, "refused", *ops)
        self.assertEqual(result.get("reason"), reason, result)

    def test_product_add_refuses_each_over_limit_brand_field(self):
        repo = self.repo()
        for field in ("brand", "displayBrand"):
            with self.subTest(field=field):
                self.assertLong(repo, f"{field} is longer than 60 characters",
                                ("product.add", {**NEW, field: "a" * 61}))

    def test_product_add_refused_before_twin_check(self):
        repo = self.repo()
        self.assertLong(repo, "name is longer than 80 characters", ("product.add", {**NEW, "name": "a" * 81}))
        repo.run(("product.add", NEW))
        added_id = repo.products()[-1]["id"]
        self.assertLong(repo, "description is longer than 600 characters",  # a twin that is also too long
                        ("product.add", {**NEW, "description": "a" * 601}))
        twin = self.assertRejected(repo, "refused", ("product.add", NEW))
        self.assertEqual(twin["reason"], f"{added_id} already has this name and brand; edit it instead")

    def test_boundaries_accepted_and_one_over_refused(self):
        repo = self.repo()
        for field, limit in PRODUCT_LIMITS.items():
            with self.subTest(op="product.edit", field=field):
                self.assertLong(repo, f"{field} is longer than {limit} characters",
                                ("product.edit", {"id": PID, field: "a" * (limit + 1)}))
                repo.run(("product.edit", {"id": PID, field: "b" * limit}))
        repo.run(("product.add", {**NEW, **{f: "c" * n for f, n in PRODUCT_LIMITS.items()}}))
        for field, limit in MAKER_LIMITS.items():
            with self.subTest(op="maker.add", field=field):
                self.assertLong(repo, f"{field} is longer than {limit} characters",
                                ("maker.add", {**MAKER, field: "a" * (limit + 1)}))
        repo.run(("maker.add", {**MAKER, **{f: "d" * n for f, n in MAKER_LIMITS.items()}}))
        for field, limit in MAKER_LIMITS.items():
            with self.subTest(op="maker.edit", field=field):
                self.assertLong(repo, f"{field} is longer than {limit} characters",
                                ("maker.edit", {"key": "Test Farm", field: "a" * (limit + 1)}))
                repo.run(("maker.edit", {"key": "Test Farm", field: "e" * limit}))

    def test_maker_refusals_leave_makers_unchanged(self):
        repo = self.repo()
        self.assertLong(repo, "place is longer than 60 characters", ("maker.add", {**MAKER, "place": "a" * 61}))
        self.assertNotIn("Test Farm", repo.makers())
        repo.run(("maker.add", MAKER))
        before = repo.makers()
        self.assertLong(repo, "story is longer than 600 characters",
                        ("maker.edit", {"key": "Test Farm", "story": "a" * 601}))
        self.assertEqual(repo.makers(), before)

    def test_first_field_in_order_is_named(self):
        repo = self.repo()
        self.assertLong(repo, "brand is longer than 60 characters",
                        ("product.add", {**NEW, "description": "a" * 601, "brand": "a" * 61, "displayBrand": "a" * 61}))
        self.assertLong(repo, "place is longer than 60 characters",
                        ("maker.add", {**MAKER, "story": "a" * 601, "place": "a" * 61}))
        self.assertLong(repo, "name is longer than 80 characters",
                        ("maker.add", {**MAKER, "story": "a" * 601, "place": "a" * 61, "name": "a" * 81}))

    def test_long_key_keeps_its_reply_and_goes_first(self):
        repo = self.repo()
        self.assertLong(repo, "maker key is longer than 64 characters",
                        ("maker.add", {**MAKER, "key": "k" * 65, "name": "a" * 81}))

    def test_image_alt_limit_is_unchanged(self):
        repo = self.repo()
        alt = "a" * 200
        repo.run(("product.add", {**NEW, "imageAlt": alt}))
        added = repo.products()[-1]
        self.assertEqual(added["imageAlt"], alt)
        result = self.assertRejected(repo, "invalid", ("product.edit", {"id": added["id"], "imageAlt": alt + "a"}))
        self.assertTrue(result["problems"], result)
        self.assertTrue(all("imageAlt" in p for p in result["problems"]), result)


if __name__ == "__main__":
    unittest.main()
