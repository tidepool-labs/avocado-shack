"""RF1810-11: absurdly large typed counts are a named refusal, never a decimal traceback.
Run: python3 -B -m unittest hass.tests.test_clover_drafts_extreme_count
"""
import dataclasses
import decimal
import unittest

from hass.clover import drafts as d
from hass.tests.test_clover_drafts import CFG, till

EXTREME = ("1e100", "1e1000000", "9" * 100)


class ExtremeCountTests(unittest.TestCase):
    def test_extreme_stock_set_is_named_refusal(self):
        oil = till()["FAKEITEM00001"]
        for bad in EXTREME:
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(d.DraftRefused, "too high") as cm:
                    d.build_set_stock(oil, bad, CFG)
                self.assertLess(len(str(cm.exception)), 120)

    def test_extreme_received_is_named_refusal(self):
        oil = till()["FAKEITEM00001"]
        for bad in EXTREME:
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(d.DraftRefused, "too high") as cm:
                    d.build_received(oil, bad, CFG)
                self.assertLess(len(str(cm.exception)), 120)

    # Bug caught: item.stock + got overflowed (decimal.Overflow) when the till's own count was past the decimal range (1E+2000000).
    def test_received_on_a_huge_till_count_is_a_named_refusal_not_an_overflow(self):
        oil = till()["FAKEITEM00001"]
        for raw in ("1E+1000", "1E+2000000", "1E+999999999999999999"):
            huge = dataclasses.replace(oil, stock=decimal.Decimal(raw))
            with self.subTest(raw=raw), self.assertRaisesRegex(d.DraftRefused, "too high") as cm:
                d.build_received(huge, "1", CFG)
            self.assertLess(len(str(cm.exception)), 120)

    # A typed fraction with a very long tail is named, not echoed back (the reply stays short).
    def test_long_typed_fraction_for_a_whole_item_is_refused_without_echo(self):
        oil = till()["FAKEITEM00001"]
        for bad in ("0." + "0" * 3000 + "1", "1." + "7" * 3000, "4e-2000"):
            with self.subTest(bad=bad[:20]), self.assertRaisesRegex(d.DraftRefused, "whole items") as cm:
                d.build_set_stock(oil, bad, CFG)
            self.assertLess(len(str(cm.exception)), 120)

    def test_refusal_preserves_caller_decimal_flags(self):
        oil = till()["FAKEITEM00001"]
        for builder in (d.build_set_stock, d.build_received):
            for already_flagged in (False, True):
                with self.subTest(builder=builder.__name__, already_flagged=already_flagged), decimal.localcontext() as ctx:
                    ctx.clear_flags()
                    ctx.flags[decimal.Rounded] = already_flagged
                    before = ctx.flags.copy()
                    with self.assertRaisesRegex(d.DraftRefused, "too high"):
                        builder(oil, "1e100", CFG)
                    self.assertEqual(ctx.flags, before)

    def test_ordinary_limit_and_control_unchanged(self):
        oil = till()["FAKEITEM00001"]
        with self.assertRaisesRegex(d.DraftRefused, "100001 looks too high for one item"):
            d.build_set_stock(oil, CFG.max_stock + 1, CFG)
        self.assertEqual(d.build_set_stock(oil, 7, CFG).requests[0]["json"], {"quantity": 7})
        self.assertEqual(d.build_set_stock(oil, CFG.max_stock, CFG).requests[0]["json"], {"quantity": CFG.max_stock})

    def test_other_numeric_guards_and_context_survive(self):
        oil = till()["FAKEITEM00001"]
        before = decimal.getcontext().copy()
        for bad, pat in (("-1", "less than 0"), ("NaN", "less than 0"), ("inf", "less than 0"), ("2.5", "whole items")):
            with self.subTest(bad=bad), self.assertRaisesRegex(d.DraftRefused, pat):
                d.build_set_stock(oil, bad, CFG)
        for bad in EXTREME:
            with self.assertRaises(d.DraftRefused):
                d.build_set_stock(oil, bad, CFG)
        after = decimal.getcontext()
        self.assertEqual((before.prec, before.Emax, before.Emin), (after.prec, after.Emax, after.Emin))


if __name__ == "__main__":
    unittest.main()
