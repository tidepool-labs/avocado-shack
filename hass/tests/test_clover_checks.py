from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from hass.clover.checks import register_check, site_check
from hass.clover.mapper import parse_item
from hass.clover.reads import Snapshot
from hass.tests.test_clover_client import NoNetwork


RAW = {
    "id": "FAKEITEMA", "name": "Demo pear", "price": 2459, "priceType": "FIXED",
    "sku": "FAKE-PEAR-SKU", "hidden": False, "itemStock": {"quantity": 73.125},
    "categories": {"elements": [{"id": "FAKECATA", "name": "Fruit"}]},
}
PLAN = {"name": "Demo pear", "price_cents": 2459, "price_type": "FIXED", "unit_name": "",
        "sku": "FAKE-PEAR-SKU", "count": Decimal("73.125"), "category_id": "FAKECATA"}
ITEM = parse_item(RAW)
SITE = {"name": "  DEMO   pear ", "sellingPrice": "24.59 each", "status": "active", "available": "yes"}
LINK = {"cloverId": "FAKEITEMA", "sku": "FAKE-PEAR-SKU"}
DECOY = replace(ITEM, id="FAKEITEMB")


def register(raw=None, *, items=(ITEM,), expected=PLAN):
    snapshot = Snapshot(items, datetime(2026, 1, 1, tzinfo=timezone.utc))
    return register_check(RAW if raw is None else RAW | raw, snapshot, expected)


def site(record=None, *, link=LINK, item=ITEM, **options):
    return site_check(SITE if record is None else SITE | record, link, item, 5, **options)


class CloverChecksTests(NoNetwork):
    def assert_verdict(self, verdict, ok, *findings):
        self.assertIs(verdict.ok, ok)
        self.assertEqual(verdict.findings, findings)

    def test_c1_register_check(self):
        # C1: matching cents alone can miss a priced-by-weight change; a name/SKU collision can target the wrong row.
        weighed = {"priceType": "PER_UNIT", "unitName": "lb"}
        plan = PLAN | {"price_type": "PER_UNIT", "unit_name": "lb", "category_id": None}
        self.assert_verdict(register(weighed | {"categories": None}, expected=plan), True)
        self.assert_verdict(register(weighed | {"unitName": "kg"}, expected=plan), False, "price")
        self.assert_verdict(register(weighed, expected=PLAN), False, "price")
        self.assert_verdict(register({"name": "Demo pear "}), False, "name")
        wrong = {"hidden": True, "name": "Demo apple", "price": 2460, "sku": "FAKE-APPLE-SKU",
                 "itemStock": {"quantity": 0}, "categories": None}
        self.assert_verdict(register(wrong), False, "hidden", "name", "price", "sku", "count", "category")
        self.assert_verdict(register(items=(ITEM, replace(DECOY, name="Other fruit", sku="Demo pear"))),
                            False, "ambiguous-name")
        self.assert_verdict(register(items=(DECOY,)), False, "not-found")

    def test_c2_site_check(self):
        # C2: matching the amount alone can certify a per-kg price; treating every positive count as 'yes' misses 'limited'.
        weighed = replace(ITEM, price_type="PER_UNIT", unit_name="lb", stock=Decimal("5"))
        record = {"sellingPrice": "24.59 per lb", "available": "limited"}
        self.assert_verdict(site(record, item=weighed), True)
        self.assert_verdict(site(record, item=replace(weighed, unit_name="kg")), False, "price-unit")
        self.assert_verdict(site(record | {"available": "yes"}, item=weighed), False, "stock-word")
        self.assert_verdict(site({"available": "no"}, item=replace(ITEM, stock=Decimal("0"))), True)
        self.assert_verdict(site({"available": None}, item=replace(ITEM, hidden=True)),
                            False, "hidden-vs-active", "no-word")
        self.assert_verdict(site({"sellingPrice": "24.59"}), False, "price-unit")
        wrong = {"name": "Demo apple", "sellingPrice": "24.60 per lb", "status": "hidden", "available": None}
        self.assert_verdict(site(wrong, link=LINK | {"cloverId": "FAKEITEMB"}),
                            False, "unlinked", "name", "price", "price-unit", "hidden-vs-active", "no-word")
        self.assert_verdict(site({"available": None}), True, "no-word")

    def test_words_mode_low_count_expects_yes(self):
        # Contract: stock_site publishes 'yes' for a low count unless siteStockWords is 'limited'; a check that
        # always expects 'limited' fails a correctly published count (false 'stock-word') and passes a wrong 'limited'.
        low = replace(ITEM, stock=Decimal("3"))
        self.assert_verdict(site({"available": "yes"}, item=low, words="words"), True)
        self.assert_verdict(site({"available": "limited"}, item=low, words="words"), False, "stock-word")
        # Healthy control: the boundary count equal to the threshold behaves the same; one above is 'yes' anyway.
        self.assert_verdict(site({"available": "yes"}, item=replace(ITEM, stock=Decimal("5")), words="words"), True)

    def test_limited_mode_low_count_expects_limited(self):
        # Contract: 'limited' mode and the default keep today's three-word result, so existing callers do not change.
        low = replace(ITEM, stock=Decimal("3"))
        for options in ({}, {"words": "limited"}):
            with self.subTest(options=options):
                self.assert_verdict(site({"available": "limited"}, item=low, **options), True)
                self.assert_verdict(site({"available": "yes"}, item=low, **options), False, "stock-word")

    def test_words_mode_zero_and_high_counts(self):
        # Contract: only the low band changes; an empty count is still 'no' and a high count still 'yes' in words mode.
        for count, word, other in (("0", "no", "yes"), ("-2", "no", "yes"), ("30", "yes", "no")):
            item = replace(ITEM, stock=Decimal(count))
            with self.subTest(count=count):
                self.assert_verdict(site({"available": word}, item=item, words="words"), True)
                self.assert_verdict(site({"available": other}, item=item, words="words"), False, "stock-word")
        # Hidden and no-count hints stay as they are: no word expected for a missing count.
        self.assert_verdict(site({"available": "yes"}, item=replace(ITEM, stock=None), words="words"),
                            False, "stock-word")
        self.assert_verdict(site({"available": "no"}, item=replace(ITEM, available=False, stock=Decimal("3")),
                                 words="words"), True)

    def test_unknown_words_value_refused(self):
        # Contract: a typo like 'word' must not silently pick a mode and certify the wrong stock word.
        for bad in ("word", "Words", "", None):
            with self.subTest(words=bad), self.assertRaises(ValueError) as caught:
                site(words=bad)
            self.assertEqual(str(caught.exception), "words")

    def test_c3_no_values_in_findings(self):
        # C3: caching the check could open a file or load a token; formatting diffs could leak price, count or SKU.
        with patch("builtins.open") as builtin, patch("io.open") as io, patch("os.open") as os_open:
            till = register({"price": 8463, "itemStock": {"quantity": 68.375}, "sku": "FAKE-OTHER-SKU"})
            web = site({"sellingPrice": "84.63 each", "available": "no"}, link=None)
        for opened in (builtin, io, os_open):
            opened.assert_not_called()
        self.assert_verdict(till, False, "price", "sku", "count")
        self.assert_verdict(web, False, "unlinked", "price", "stock-word")
        for verdict in (till, web):
            self.assertRegex(repr(verdict), r"^Verdict\(ok=False, findings=\('[a-z-]+'(?:, '[a-z-]+')*\)\)$")

    def test_c4_case_table(self):
        # C4: a missing or mislabelled branch can silently clear a failed fact, or make a valid item fail.
        cases = (
            ("register ok", register(), True, ()),
            ("hidden", register({"hidden": True}), False, ("hidden",)),
            ("register name", register({"name": "demo pear"}), False, ("name",)),
            ("register price", register({"price": 2460}), False, ("price",)),
            ("sku", register({"sku": "fake-pear-sku"}), False, ("sku",)),
            ("count", register({"itemStock": {"quantity": 73}}), False, ("count",)),
            ("category id", register({"categories": {"elements": [{"id": "FAKECATB", "name": "Fruit"}]}}),
             False, ("category",)),
            ("missing from cache", register(items=()), False, ("not-found",)),
            ("duplicate in cache", register(items=(ITEM, DECOY)), False, ("ambiguous-name",)),
            ("website ok", site(), True, ()),
            ("wrong link id, matching SKU", site(link=LINK | {"cloverId": "FAKEITEMB"}), False, ("unlinked",)),
            ("website name", site({"name": "Demo apple"}), False, ("name",)),
            ("website price", site({"sellingPrice": "24.60 each"}), False, ("price",)),
            ("website price unit", site({"sellingPrice": "24.59 per lb"}), False, ("price-unit",)),
            ("inactive website", site({"status": "held"}), False, ("hidden-vs-active",)),
            ("stock word", site({"available": "no"}), False, ("stock-word",)),
            ("no word", site({"available": None}), True, ("no-word",)),
        )
        for label, verdict, ok, findings in cases:
            with self.subTest(label=label):
                self.assert_verdict(verdict, ok, *findings)
