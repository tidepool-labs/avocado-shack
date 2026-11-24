"""HASS-CLOVER-1: item mapping both ways, price-in-cents maths, exact matching. Recorded fixtures and constructed items only.
Run: python3 -B -m unittest hass.tests.test_clover_mapper
"""
import decimal
import unittest
from decimal import Decimal

from hass.clover import mapper as m
from hass.tests.test_clover_client import fixture


def items():
    parsed, skipped = m.parse_items(fixture("items.json")["elements"])
    assert skipped == 0
    return {i.id: i for i in parsed}


def item(**kw):
    base = dict(id="FAKEITEM09999", name="Thing", sku="", code="", price_cents=500, price_type="FIXED", unit_name="", categories=(), tags=(),
                stock=None, stock_modified=None, hidden=False, available=True, modified_time=1)
    return m.CloverItem(**{**base, **kw})


def product(pid="photo-product-900", name="Thing", **kw):
    return m.parse_site_product({"id": pid, "name": name, "brand": "Maker", "category": "pantry", "description": "d", "status": "active", **kw})


class MoneyTests(unittest.TestCase):
    def test_text_to_cents(self):
        for text, cents in (("12.50", 1250), ("$12.50", 1250), ("12.5", 1250), ("12", 1200), ("$ 12", 1200), ("0.05", 5), ("1,000.00", 100000),
                            (" 7.00 ", 700), ("1000", 100000), ("999.99", 99999)):
            with self.subTest(text=text):
                self.assertEqual(m.cents_from_text(text), cents)

    def test_floats_never_touch_the_arithmetic(self):
        self.assertEqual(m.cents_from_text("19.99"), 1999)          # 19.99 * 100 is 1998.9999999999998 as a float
        self.assertEqual(m.cents_from_text("0.29"), 29)             # 0.29 * 100 is 28.999999999999996
        self.assertIs(type(m.cents_from_text("1.10")), int)

    def test_bad_prices_are_refused_in_plain_words(self):
        for text in ("", "abc", "-5", "+5", "12.505", "12.", ".5", "1e3", "0", "0.00", "12,50", "$$5", "1,23", "12 dollars", "NaN", None, 12.5):
            with self.subTest(text=text), self.assertRaises(m.MapError):
                m.cents_from_text(text)
        with self.assertRaisesRegex(m.MapError, r"\$1,000\.01 looks too high"):
            m.cents_from_text("1000.01")
        self.assertEqual(m.cents_from_text("2000", max_cents=300000), 200000)

    def test_format_money(self):
        for cents, text in ((0, "$0.00"), (5, "$0.05"), (150, "$1.50"), (1250, "$12.50"), (123456, "$1,234.56")):
            self.assertEqual(m.format_money(cents), text)
        for bad in (-1, 1.5, "5", True, None):
            with self.assertRaises(m.MapError):
                m.format_money(bad)

    def test_percentage_change_is_exact_and_rounds_half_up(self):
        for old, new, pct in ((1000, 1250, "25.0"), (1000, 800, "-20.0"), (1000, 1001, "0.1"), (3, 4, "33.3"), (3, 2, "-33.3"),
                              (2000, 2001, "0.1"), (1000, 1000, "0.0"), (1, 3, "200.0"), (1250, 1400, "12.0"), (1999, 2999, "50.0")):
            with self.subTest(old=old, new=new):
                self.assertEqual(m.pct_change(old, new), Decimal(pct))
        for old in (0, -5, None, 1.5):
            with self.assertRaises(m.MapError):
                m.pct_change(old, 100)

    def test_quantities(self):
        for q, text in ((12, "12"), (Decimal("12.0"), "12"), (Decimal("7.5"), "7.5"), (Decimal("0"), "0"), (Decimal("2.250"), "2.25"), (Decimal("100"), "100")):
            self.assertEqual(m.format_quantity(q), text)

    # Contract: a printed count never contradicts a nonzero count. Bug caught: rounding to 3 places printed a 0.0004 lb count as '0'
    # next to 'Yes, Saffron: 0 in the till.'; and a tiny negative as '-0'.
    def test_tiny_count_is_not_zero(self):
        for q, text in (("0.0004", "0.0004"), ("-0.0004", "-0.0004"), ("0.00040", "0.0004"), ("0.0005", "0.0005"), ("0.000499", "0.000499"), ("4E-10", "0.0000000004")):
            with self.subTest(q=q):
                self.assertEqual(m.format_quantity(Decimal(q)), text)

    def test_negative_zero_prints_zero(self):
        for q in (Decimal("-0"), Decimal("-0.000"), Decimal("0E-10"), Decimal("0.000")):
            with self.subTest(q=q):
                self.assertEqual(m.format_quantity(q), "0")

    # Bug caught: a count of more than 27 digits made quantize raise decimal.InvalidOperation out of the reply.
    def test_huge_count_does_not_raise(self):
        for q, text in (("1E+30", "1" + "0" * 30), ("-1E+30", "-1" + "0" * 30), ("12345678901234567890123456789.5", "12345678901234567890123456789.5"),
                        ("12345678901234567890123456789.1230", "12345678901234567890123456789.123")):
            with self.subTest(q=q):
                self.assertEqual(m.format_quantity(Decimal(q)), text)

    # Contract: every count the mapper admits (plain form up to MAX_PLAIN_DIGITS) prints as its exact plain digits, never an exponent, never
    # rounded away: nonzero counts below 0.0005 and huge counts alike. Bug caught: a 64-digit cap raised InvalidOperation for 1E+64 / 4E-64
    # (the read crashed); then a lossy exponent fallback printed 4E-300 and 1.2345678901234568E+300 instead of the digits.
    def test_admitted_counts_print_exact_plain_digits_across_the_boundary(self):
        edge = m.MAX_PLAIN_DIGITS
        long_frac = "1." + "234567890" * 33 + "E+300"            # 298 digits, exponent 3: a long, precise, huge count
        for q, text in (("1E+64", "1" + "0" * 64), ("-1E+64", "-1" + "0" * 64), ("4E-64", "0." + "0" * 63 + "4"), ("-4E-64", "-0." + "0" * 63 + "4"),
                        ("1E+255", "1" + "0" * 255), ("1E+256", "1" + "0" * 256), ("1E+257", "1" + "0" * 257),
                        ("4E-300", "0." + "0" * 299 + "4"), ("-4E-300", "-0." + "0" * 299 + "4"),
                        ("1.234567890123456789E+300", "1234567890123456789" + "0" * 282),
                        ("9" * 100, "9" * 100),
                        ("1E+%d" % (edge - 1), "1" + "0" * (edge - 1)),                    # exactly MAX_PLAIN_DIGITS digits: still exact
                        ("4E-%d" % (edge - 1), "0." + "0" * (edge - 2) + "4")):             # 0. and exactly MAX_PLAIN_DIGITS digits after it
            with self.subTest(q=q[:24]):
                self.assertEqual(m.format_quantity(Decimal(q)), text)
        self.assertEqual(m.format_quantity(Decimal(long_frac)), format(Decimal(long_frac), "f"))

    # Contract: past MAX_PLAIN_DIGITS format_quantity refuses before building a string (so a draft refusal never echoes a huge count and a
    # reply never carries one). Bug caught: an uncapped format() building a million-digit string for 1E+1000000.
    def test_count_past_the_boundary_is_refused_not_built(self):
        edge = m.MAX_PLAIN_DIGITS
        for q in ("1E+%d" % edge, "4E-%d" % edge, "-4E-%d" % edge, "1E+1000000", "4E-1000000", "1E+999999999999999999", "9" * (edge + 1)):
            with self.subTest(q=q[:24]), self.assertRaises(decimal.InvalidOperation):
                m.format_quantity(Decimal(q))

    # Healthy control: values the function already formatted correctly stay byte-identical.
    def test_ordinary_counts_unchanged(self):
        for q, text in (("12", "12"), ("12.0", "12"), ("12.5", "12.5"), ("0.001", "0.001"), ("0.0006", "0.001"), ("0.000999", "0.001"), ("-0.0006", "-0.001"), ("-3.5", "-3.5"),
                        ("0.0015", "0.002"), ("100", "100"), ("1E+3", "1000"), ("1234567890123456789012345.6789", "1234567890123456789012345.679")):
            with self.subTest(q=q):
                self.assertEqual(m.format_quantity(Decimal(q)), text)


class NameTests(unittest.TestCase):
    def test_norm_name_ignores_case_spacing_and_curly_quotes_but_not_accents(self):
        self.assertEqual(m.norm_name("  Linn\u2019s   Blueberry\tJam "), m.norm_name("linn's blueberry jam"))
        self.assertNotEqual(m.norm_name("Jalape\u00f1o"), m.norm_name("Jalapeno"))
        self.assertEqual(m.norm_name("\uff21\uff22"), "ab")          # full-width letters fold to plain ones
        self.assertEqual(m.norm_name(None), "")

    def test_clean_name(self):
        self.assertEqual(m.clean_name("  Sunshine   olive  oil "), "Sunshine olive oil")
        self.assertEqual(m.clean_name("two\nlines\tand\u2028more"), "two lines and more")      # line breaks and tabs become one space
        for bad in ("", "   ", None, "a" * 101, "<b>x</b>", "x\u200by", "a\x00b", "{{x}}", "back\\slash", "\u202eevil", 5):
            with self.subTest(bad=repr(bad)[:20]), self.assertRaises(m.MapError):
                m.clean_name(bad)


class ItemMappingTests(unittest.TestCase):
    def test_a_clover_item_is_read_by_whitelist(self):
        oil = items()["FAKEITEM00001"]
        self.assertEqual((oil.name, oil.sku, oil.code, oil.price_cents, oil.price_type), ("Sunshine olive oil", "AS-PAN-SUNSHINE-OLIVE-OIL-01", "0123456789012", 1250, "FIXED"))
        self.assertEqual((oil.stock, oil.stock_modified, oil.hidden, oil.available, oil.modified_time), (Decimal("12.0"), 1794250100000, False, True, 1794250000000))
        self.assertEqual((oil.categories, oil.tags), (("Pantry",), ("Local",)))
        self.assertNotIn("cost", {f for f in oil.__dataclass_fields__})      # the shop's cost never comes in
        self.assertNotIn("700", repr(oil))

    def test_special_items(self):
        got = items()
        self.assertTrue(got["FAKEITEM00004"].hidden)
        self.assertEqual(got["FAKEITEM00004"].stock, Decimal("0.0"))
        tomatoes = got["FAKEITEM00005"]
        self.assertEqual((tomatoes.price_type, tomatoes.unit_name, tomatoes.stock, tomatoes.price_cents), ("PER_UNIT", "lb", Decimal("7.5"), 399))
        free = got["FAKEITEM00006"]
        self.assertEqual((free.price_type, free.price_cents, free.stock, free.stock_modified), ("VARIABLE", None, None, None))
        self.assertEqual(got["FAKEITEM00002"].sku, "")

    # Contract: the till's count is admitted only if it can be printed exactly (plain form up to MAX_PLAIN_DIGITS); a longer one is treated
    # like a count the till did not give (None), so no read ever has to print or sum it. Bug caught: 1E+1000000 admitted, then a reply
    # either raised or built a million-digit string; the boundary itself (1E+999) must still be kept.
    def test_parse_item_admits_counts_up_to_the_print_boundary_only(self):
        edge = m.MAX_PLAIN_DIGITS
        for q, kept in (("1E+64", True), ("4E-300", True), ("1E+%d" % (edge - 1), True), ("4E-%d" % (edge - 1), True),
                        ("1E+%d" % edge, False), ("4E-%d" % edge, False), ("1E+1000000", False), ("4E-999999999999999999", False)):
            with self.subTest(q=q):
                got = m.parse_item({"id": "A1", "name": "N", "itemStock": {"quantity": q}}).stock
                self.assertEqual(got, Decimal(q) if kept else None)

    def test_odd_values_do_not_become_prices_or_counts(self):
        raw = {"id": "A1", "name": "N", "price": True, "itemStock": {"quantity": "x"}, "modifiedTime": -4, "hidden": "yes", "priceType": "WEIRD"}
        got = m.parse_item(raw)
        self.assertEqual((got.price_cents, got.stock, got.modified_time, got.hidden, got.price_type), (None, None, 0, False, "FIXED"))
        for q in (float("nan"), float("inf"), True, [1], {"a": 1}):
            self.assertIsNone(m.parse_item({"id": "A1", "name": "N", "itemStock": {"quantity": q}}).stock)
        self.assertEqual(m.parse_item({"id": "A1", "name": "N", "price": 1.5}).price_cents, None)

    def test_a_bad_row_is_skipped_not_fatal(self):
        good, skipped = m.parse_items([{"id": "A1", "name": "N"}, {"id": "", "name": "x"}, {"name": "no id"}, {"id": "A2"}, "text", None, {"id": "a/b", "name": "x"}])
        self.assertEqual(([i.id for i in good], skipped), (["A1"], 6))

    def test_availability_hint_from_the_count(self):
        got = items()
        for item_id, word in (("FAKEITEM00001", "yes"), ("FAKEITEM00003", "limited"), ("FAKEITEM00004", None), ("FAKEITEM00006", None)):
            self.assertEqual(m.availability_hint(got[item_id], 5), word, item_id)
        self.assertEqual(m.availability_hint(item(stock=Decimal(0)), 5), "no")
        self.assertEqual(m.availability_hint(item(stock=Decimal(5)), 5), "limited")
        self.assertEqual(m.availability_hint(item(stock=Decimal(6)), 5), "yes")
        self.assertEqual(m.availability_hint(item(stock=Decimal(9), available=False), 5), "no")

    def test_categories_both_ways(self):
        cmap = {"pantry": "Pantry", "fruit": "Fruit"}
        self.assertEqual(m.clover_category("pantry", cmap), "Pantry")
        self.assertIsNone(m.clover_category("dairy", cmap))
        self.assertIsNone(m.clover_category("nonsense", {"nonsense": "x"}))
        self.assertEqual(m.site_category(item(categories=("pantry ", "Zzz")), cmap), "pantry")
        self.assertEqual(m.site_category(item(categories=("FRUIT",)), cmap), "fruit")
        self.assertIsNone(m.site_category(item(categories=("Other",)), cmap))


class SiteSideTests(unittest.TestCase):
    def test_site_product_has_no_price_sku_or_count(self):
        p = m.parse_site_product({"id": "photo-product-001", "name": "Hass avocado", "brand": "Avocado Shack", "producerKey": None, "category": "fruit",
                                  "description": "Creamy.", "status": "active", "available": "limited", "image": "x.webp", "displayBrand": "y"})
        self.assertEqual((p.id, p.name, p.brand, p.producer_key, p.category, p.availability, p.status),
                         ("photo-product-001", "Hass avocado", "Avocado Shack", None, "fruit", "limited", "active"))
        for field in ("price", "sku", "stock", "count", "code"):
            self.assertNotIn(field, p.__dataclass_fields__)
        self.assertIsNone(m.parse_site_product({"id": "a", "name": "b", "available": "maybe"}).availability)
        for bad in (None, {}, {"id": 1, "name": "x"}, {"id": "a"}, "x"):
            with self.assertRaises(m.MapError):
                m.parse_site_product(bad)

    def test_create_payload_for_clover(self):
        self.assertEqual(m.create_payload(" Sunshine  olive oil ", 1250, "AS-PAN-X-01"),
                         {"name": "Sunshine olive oil", "price": 1250, "priceType": "FIXED", "sku": "AS-PAN-X-01", "hidden": False})
        for bad in (0, -1, 12.5, "1250", True, None):
            with self.assertRaises(m.MapError):
                m.create_payload("N", bad, "S")


class MatchingTests(unittest.TestCase):
    def test_link_then_sku_then_exact_name(self):
        till = [item(id="I1", name="Renamed in the till", sku="AS-PAN-A-01"), item(id="I2", name="Eggs", sku="EGG12"),
                item(id="I3", name="Honey", sku="AS-PAN-HONEY-01"), item(id="I4", name="Jam"), item(id="I5", name="Only on the till")]
        site = [product("p1", "Original name"), product("p2", "eggs"), product("p3", "Honey"), product("p4", "Jam"), product("p5", "Only on the site")]
        links = {"p1": {"cloverId": "I1", "sku": "AS-PAN-A-01"}, "p3": {"cloverId": "GONE", "sku": "as-pan-honey-01"}}
        got = m.match(site, till, links)
        self.assertEqual({(x.product_id, x.item_id, x.how) for x in got.pairs},
                         {("p1", "I1", "link"), ("p3", "I3", "sku"), ("p2", "I2", "name"), ("p4", "I4", "name")})
        self.assertEqual((got.site_only, got.clover_only, got.ambiguous, got.broken_links), (("p5",), ("I5",), (), ()))

    def test_a_stored_link_beats_a_name_match_whatever_the_product_ids_sort_like(self):
        till = [item(id="I1", name="Eggs")]
        site = [product("a", "Eggs"), product("z", "Free-range dozen")]
        got = m.match(site, till, {"z": {"cloverId": "I1"}})
        self.assertEqual([(x.product_id, x.item_id, x.how) for x in got.pairs], [("z", "I1", "link")])
        self.assertEqual((got.broken_links, got.ambiguous, got.site_only, got.clover_only), ((), (), ("a",), ()))

    def test_a_stored_sku_link_also_beats_a_name_match_on_an_earlier_product(self):
        till = [item(id="I1", name="Eggs", sku="EGG12")]
        site = [product("a", "Eggs"), product("z", "Free-range dozen")]
        got = m.match(site, till, {"z": {"cloverId": "GONE", "sku": "egg12"}})
        self.assertEqual([(x.product_id, x.item_id, x.how) for x in got.pairs], [("z", "I1", "sku")])
        self.assertEqual((got.broken_links, got.ambiguous, got.site_only), ((), (), ("a",)))

    def test_a_link_to_a_vanished_item_with_no_sku_match_is_reported_not_guessed(self):
        got = m.match([product("p1", "Eggs")], [item(id="I2", name="Eggs")], {"p1": {"cloverId": "GONE", "sku": "NOPE"}})
        self.assertEqual((got.pairs, got.broken_links, got.clover_only), ((), ("p1",), ("I2",)))   # not paired by name behind the owner's back

    def test_duplicate_names_are_ambiguous_on_either_side(self):
        got = m.match([product("p1", "Eggs")], [item(id="I1", name="Eggs"), item(id="I2", name="EGGS")])
        self.assertEqual((got.pairs, got.ambiguous, got.site_only), ((), (("p1", ("I1", "I2")),), ()))
        got = m.match([product("p1", "Eggs"), product("p2", "eggs")], [item(id="I1", name="Eggs")])
        self.assertEqual(got.pairs, ())
        self.assertEqual(len(got.ambiguous), 2)

    def test_nothing_fuzzy_pairs(self):
        got = m.match([product("p1", "Sunshine olive oil")], [item(id="I1", name="Sunshine olive oils"), item(id="I2", name="Sunshine Olive Oil 1L")])
        self.assertEqual((got.pairs, got.site_only, got.clover_only), ((), ("p1",), ("I1", "I2")))

    def test_two_links_cannot_claim_one_item(self):
        till = [item(id="I1", name="A")]
        got = m.match([product("p1", "A"), product("p2", "B")], till, {"p1": {"cloverId": "I1"}, "p2": {"cloverId": "I1"}})
        self.assertEqual([x.product_id for x in got.pairs], ["p1"])
        self.assertEqual(got.broken_links, ("p2",))

    def test_matching_is_deterministic(self):
        till = [item(id=f"I{n}", name=f"N{n}") for n in range(20)]
        site = [product(f"p{n}", f"n{n}") for n in range(20)]
        self.assertEqual(m.match(site, till), m.match(list(reversed(site)), list(reversed(till))))

    def test_the_fixture_till_against_a_site(self):
        got = items()
        site = [product("p1", "Hass avocado"), product("p2", "Sunshine olive oil"), product("p3", "Sourdough")]
        res = m.match(site, list(got.values()))
        self.assertEqual({(x.product_id, x.item_id) for x in res.pairs}, {("p1", "FAKEITEM00002"), ("p2", "FAKEITEM00001")})
        self.assertEqual(res.site_only, ("p3",))
        self.assertIn("FAKEITEM00003", res.clover_only)


class ResolveForWritesTests(unittest.TestCase):
    def setUp(self):
        self.till = list(items().values())

    def test_exact_name_or_exact_sku_only(self):
        self.assertEqual(m.resolve_exact("sunshine OLIVE oil", self.till).id, "FAKEITEM00001")
        self.assertEqual(m.resolve_exact("as-pan-sunshine-olive-oil-01", self.till).id, "FAKEITEM00001")
        self.assertEqual(m.resolve_exact("EGG12", self.till).id, "FAKEITEM00003")

    def test_a_near_name_is_never_a_write_target(self):
        for q in ("Sunshine olive", "olive oil", "Sunshine olive oils", "Sunshine olive oi", "Sunshin olive oil", ""):
            with self.subTest(q=q), self.assertRaises(m.NotExact) as ctx:
                m.resolve_exact(q, self.till)
            self.assertIn("exactly", str(ctx.exception))
        with self.assertRaises(m.NotExact) as ctx:
            m.resolve_exact("olive oil", self.till)
        self.assertEqual([i.name for i in ctx.exception.candidates], ["Sunshine olive oil"])    # offered, never chosen

    def test_a_hidden_item_is_reachable_only_by_its_sku(self):
        hidden = item(id="H1", name="Old honey", sku="AS-PAN-OLD-HONEY-01", hidden=True)
        with self.assertRaises(m.NotExact):
            m.resolve_exact("Old honey", [hidden])
        self.assertEqual(m.resolve_exact("AS-PAN-OLD-HONEY-01", [hidden]).id, "H1")

    def test_two_items_with_one_name_ask_for_a_sku(self):
        twins = [item(id="A", name="Eggs", sku="S-1"), item(id="B", name="eggs", sku="S-2")]
        with self.assertRaisesRegex(m.NotExact, "Send its SKU: S-1, S-2") as ctx:
            m.resolve_exact("Eggs", twins)
        self.assertEqual(len(ctx.exception.candidates), 2)

    def test_suggest_is_read_only_help(self):
        self.assertEqual([i.name for i in m.suggest("olive oil", self.till)], ["Sunshine olive oil"])
        self.assertEqual(m.suggest("", self.till), ())
        self.assertEqual(m.suggest("old honey", self.till), ())     # hidden items are not suggested

    def test_plural_and_singular_each_word(self):
        names = ["Hass avocado", "Mixed berry", "Heirloom tomatoes", "Gift boxes", "White peach", "Olive oil"]
        till = [item(id=str(n), name=name) for n, name in enumerate(names)]
        for q, want in (("avocados", "Hass avocado"), ("hass avocados", "Hass avocado"), ("berries", "Mixed berry"), ("tomato", "Heirloom tomatoes"),
                        ("box", "Gift boxes"), ("peaches", "White peach"), ("oils", "Olive oil")):
            with self.subTest(q=q):
                self.assertEqual([i.name for i in m.suggest(q, till)], [want])
        self.assertEqual(m.suggest("green avocados", till), ())      # every word is still required

    def test_cap_order_hidden_and_limits(self):
        till = [item(id=str(n), name=f"Avocado {c}") for n, c in enumerate("gfedcba")] + [item(id="h", name="Avocados hidden", hidden=True)]
        got = m.suggest("avocados", till)
        self.assertEqual([i.name for i in got], [f"Avocado {c}" for c in "abcde"])
        self.assertEqual(len(m.suggest("avocados", till, 2)), 2)
        self.assertEqual(m.suggest("avocados", till, 0), ())
        self.assertEqual(m.suggest("avocados", till, -1), ())
        self.assertEqual(got, m.suggest("avocados", till))

    def test_plural_is_never_a_write_target(self):
        till = [item(id="A", name="Hass avocado", sku="HASS-1")]
        with self.assertRaises(m.NotExact) as ctx:
            m.resolve_exact("avocados", till)
        self.assertEqual([i.name for i in ctx.exception.candidates], ["Hass avocado"])
        self.assertEqual(m.resolve_exact("hass avocado", till).id, "A")


if __name__ == "__main__":
    unittest.main()
