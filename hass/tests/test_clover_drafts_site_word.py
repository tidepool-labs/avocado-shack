"""AV1124B-01: a till count draft sets the website stock word the stock sync would publish, and count text stays exact.
Run: python3 -B -m unittest hass.tests.test_clover_drafts_site_word
Contract protected: hass.clover.drafts._site_op follows hass.stock_site word() in 'limited' mode ('words' mode unchanged), an undo restores the
journalled word, '-0' is 0, and _qty refuses count text Decimal reads but a person did not mean (underscore, exponent, non-ASCII digits).
Names, counts and words are made up."""
import dataclasses
import unittest
from decimal import Decimal

from hass.clover import drafts as d
from hass.tests.test_clover_drafts import CFG
from hass.tests.test_clover_mapper import item, product

LIMITED = dataclasses.replace(CFG, site_stock_words="limited", low_stock_threshold=5)


def oil(stock):
    return item(id="O", name="Oil", sku="S1", stock=Decimal(stock))


def site_op(count_from, count_to, word, config=LIMITED, **kw):
    """The site op a count change draft carries: (word set, or None)."""
    dr = d.build_set_stock(oil(count_from), count_to, config, site_product=product("p", "Oil", available=word, **kw))
    return dr, (dr.site_ops[0]["args"]["available"] if dr.site_ops else None)


class LimitedModeTests(unittest.TestCase):
    def test_limited_mode_low_count_marks_limited(self):
        for count_from, word in ((0, "no"), (30, "yes")):    # was sold out / was well stocked
            with self.subTest(count_from=count_from):
                dr, got = site_op(count_from, 3, word)
                self.assertEqual(got, "limited")
                self.assertIn("Website: marks Oil as Limited", dr.render("c1"))
                self.assertEqual(dr.after["site"], {"id": "p", "available": "limited"})
        self.assertEqual(site_op(30, 5, "yes")[1], "limited")        # the threshold itself is still low
        self.assertIsNone(site_op(0, 3, "limited")[1])               # already says it

    def test_limited_mode_back_above_threshold_marks_yes(self):
        self.assertEqual(site_op(3, 30, "limited")[1], "yes")
        self.assertEqual(site_op(5, 6, "limited")[1], "yes")          # one over the threshold
        self.assertEqual(site_op(0, 30, "no")[1], "yes")              # healthy control: the old behaviour for a restock
        self.assertIsNone(site_op(3, 30, "yes")[1])

    def test_limited_mode_zero_marks_no(self):
        self.assertEqual(site_op(30, 0, "yes")[1], "no")              # healthy control
        self.assertEqual(site_op(3, 0, "limited")[1], "no")
        self.assertIsNone(site_op(3, 0, "no")[1])

    def test_limited_mode_leaves_unwordable_products_alone(self):
        self.assertIsNone(site_op(0, 3, "no", status="hidden")[1])    # only an active product
        self.assertIsNone(site_op(0, 3, None)[1])                     # no word on the card: leave it (as in words mode)
        self.assertEqual(site_op(3, 0, None)[1], "no")
        dr = d.build_set_stock(oil(0), 3, LIMITED)                    # no site product at all
        self.assertEqual(dr.site_ops, ())

    def test_words_mode_unchanged(self):
        dr, got = site_op(0, 3, "no", CFG)
        self.assertEqual(got, "yes")                                  # words mode: any count above 0 is 'yes'
        self.assertIn("  Website: marks Oil as Available today (same yes; the site shows a word, never a count)", dr.lines)
        self.assertEqual(site_op(30, 3, "yes", CFG)[0].site_ops, ())   # no 'limited' word in words mode
        self.assertEqual(site_op(30, 0, "yes", CFG)[1], "no")         # healthy control
        self.assertEqual(site_op(0, 30, "no", CFG)[1], "yes")

    def test_undo_restores_journalled_word(self):
        dr, got = site_op(30, 3, "no")          # a stale 'no' on a stocked item: the draft sets 'limited', journals 'no'
        self.assertEqual((got, dr.before["site"]["available"]), ("limited", "no"))
        after = oil(3)
        undo = d.build_undo(dr.to_dict(), after, LIMITED, site_product=product("p", "Oil", available="limited"))
        self.assertEqual(undo.site_ops[0]["args"], {"id": "p", "available": "no"})   # recomputing for count 30 would say 'yes'


class CountTextTests(unittest.TestCase):
    def test_negative_zero_is_zero_and_undo_works(self):
        for zero in ("-0", Decimal("-0"), "-0.0"):
            with self.subTest(zero=repr(zero)):
                dr = d.build_set_stock(oil(4), zero, CFG)
                self.assertIn("  Count: 4 -> 0", dr.lines)
                self.assertEqual((dr.after, dr.requests[0]["json"]), ({"stock": "0"}, {"quantity": 0}))
                undo = d.build_undo(dr.to_dict(), oil(0), CFG)
                self.assertIn("  Count: 0 -> 4", undo.lines)

    def test_odd_count_text_refused_and_plain_text_read(self):
        for bad in ("1_0", "1e1", "1E1", "\u0661\u0662", "1\u0662", "0x10"):
            for build in (d.build_set_stock, d.build_received):
                with self.subTest(bad=bad, build=build.__name__), self.assertRaisesRegex(d.DraftRefused, "I could not read that as a count"):
                    build(oil(4), bad, CFG)
        for text, want in (("7", 7), ("7.0", 7), (" 7 ", 7)):
            with self.subTest(text=text):
                self.assertEqual(d.build_set_stock(oil(4), text, CFG).requests[0]["json"], {"quantity": want})
        weighed = item(id="W", name="Dates", sku="S2", price_type="PER_UNIT", unit_name="lb", stock=Decimal(4))
        self.assertEqual(d.build_set_stock(weighed, "7.25", CFG).requests[0]["json"], {"quantity": 7.25})


if __name__ == "__main__":
    unittest.main()
