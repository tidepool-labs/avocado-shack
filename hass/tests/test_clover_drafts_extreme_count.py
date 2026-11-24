"""RF1810-11: absurdly large typed counts are a named refusal, never a decimal traceback.
Run: python3 -B -m unittest hass.tests.test_clover_drafts_extreme_count
"""
import decimal
import unittest

from hass.clover import drafts as d
from hass.tests.test_clover_drafts import CFG, till

EXTREME = ("1e100", "1e1000000", "9" * 100)
# AV1124B-01: exponent text is not a count a person typed, so it is the unreadable-count reply BEFORE any size bound; only plain digits
# can be "too high". Each text -> the reply it must get.
WANT = {"1e100": "could not read that as a count", "1e1000000": "could not read that as a count", "9" * 100: "too high"}


class ExtremeCountTests(unittest.TestCase):
    def test_extreme_stock_set_is_named_refusal(self):
        oil = till()["FAKEITEM00001"]
        for bad in EXTREME:
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(d.DraftRefused, WANT[bad]) as cm:
                    d.build_set_stock(oil, bad, CFG)
                self.assertLess(len(str(cm.exception)), 120)

    def test_extreme_received_is_named_refusal(self):
        oil = till()["FAKEITEM00001"]
        for bad in EXTREME:
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(d.DraftRefused, WANT[bad]) as cm:
                    d.build_received(oil, bad, CFG)
                self.assertLess(len(str(cm.exception)), 120)

    def test_refusal_preserves_caller_decimal_flags(self):
        oil = till()["FAKEITEM00001"]
        for builder in (d.build_set_stock, d.build_received):
            for already_flagged in (False, True):
                with self.subTest(builder=builder.__name__, already_flagged=already_flagged), decimal.localcontext() as ctx:
                    ctx.clear_flags()
                    ctx.flags[decimal.Rounded] = already_flagged
                    before = ctx.flags.copy()
                    for bad in ("1e100", "9" * 100):   # the unreadable-text path and the too-high path both leave the caller's flags alone
                        with self.assertRaisesRegex(d.DraftRefused, WANT[bad]):
                            builder(oil, bad, CFG)
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
