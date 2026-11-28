"""HASS-CLOVER-1: read answers from a snapshot, the staleness label and the unreachable behaviour. Recorded fixtures only.
Run: python3 -B -m unittest hass.tests.test_clover_reads
"""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from hass.clover import mapper, reads
from hass.tests.test_clover_mapper import item, items

PT = reads.PACIFIC
NOW = datetime(2026, 11, 9, 15, 30, tzinfo=PT)               # Monday 3:30 pm Pacific


def snap(minutes_old=5, extra=()):
    return reads.Snapshot(tuple(items().values()) + tuple(extra), NOW - timedelta(minutes=minutes_old))


class FreshnessTests(unittest.TestCase):
    def test_states_and_labels(self):
        for minutes, state, label in ((0, "fresh", ""), (20, "fresh", ""), (21, "stale", "(till count as of 3:09 pm)"), (360, "stale", "(till count as of 9:30 am)"),
                                      (23 * 60, "stale", "(till count as of Sun 4:30 pm)")):
            with self.subTest(minutes=minutes):
                self.assertEqual(reads.freshness(snap(minutes), NOW), (state, label))
        state, label = reads.freshness(snap(25 * 60), NOW)
        self.assertEqual(state, "too-old")
        self.assertIn("since Sun 2:30 pm", label)
        self.assertIn("will not quote a count that old", label)

    def test_unreachable_says_so_and_dates_the_count(self):
        state, label = reads.freshness(snap(10), NOW, reachable=False)
        self.assertEqual(state, "unreachable")
        self.assertEqual(label, "I can't reach the till right now. The last count I have is from 3:20 pm, so treat it as old.")

    def test_timezone_is_pacific_whatever_the_clock_says(self):
        utc = datetime(2026, 11, 9, 23, 30, tzinfo=timezone.utc)            # 3:30 pm Pacific (PST, UTC-8)
        self.assertEqual(reads.when(utc, utc), "3:30 pm")
        self.assertEqual(reads.when(datetime(2026, 11, 9, 8, 5, tzinfo=PT), NOW), "8:05 am")
        self.assertEqual(reads.when(datetime(2026, 11, 9, 0, 5, tzinfo=PT), NOW), "12:05 am")
        self.assertEqual(reads.when(datetime(2026, 11, 9, 12, 0, tzinfo=PT), NOW), "12:00 pm")


class HowManyTests(unittest.TestCase):
    def test_a_fresh_exact_answer_has_no_label(self):
        self.assertEqual(reads.how_many("sunshine olive oil", snap(), NOW), "Sunshine olive oil: 12 in the till.")
        self.assertEqual(reads.how_many("EGG12", snap(), NOW), "Eggs, dozen: 2 in the till.")
        self.assertEqual(reads.how_many("heirloom tomatoes", snap(), NOW), "Heirloom tomatoes: 7.5 in the till.")

    def test_an_older_answer_is_labelled(self):
        self.assertEqual(reads.how_many("hass avocado", snap(90), NOW), "Hass avocado: 40 in the till. (till count as of 2:00 pm)")

    def test_unreachable_puts_the_warning_first(self):
        got = reads.how_many("hass avocado", snap(90), NOW, reachable=False)
        self.assertTrue(got.startswith("I can't reach the till right now."))
        self.assertTrue(got.endswith("Hass avocado: 40 in the till."))

    def test_too_old_quotes_nothing(self):
        got = reads.how_many("hass avocado", snap(30 * 60), NOW)
        self.assertNotIn("40", got)
        self.assertIn("will not quote", got)
        self.assertNotIn("40", reads.how_many("hass avocado", snap(30 * 60), NOW, reachable=False))

    def test_untracked_hidden_and_unknown(self):
        self.assertEqual(reads.how_many("market special (ring up price)", snap(), NOW), "Market special (ring up price): the till keeps no count.")
        self.assertEqual(reads.how_many("old honey jar", snap(), NOW), "Old honey jar: 0 in the till. It is hidden on the till.")
        self.assertEqual(reads.how_many("wombat", snap(), NOW), "I can't find anything like that in the till.")

    def test_a_near_name_is_a_suggestion_never_a_silent_pick(self):
        self.assertEqual(reads.how_many("olive oil", snap(), NOW), "I can't find exactly that. The closest is Sunshine olive oil: 12 in the till.")
        two = snap(extra=[item(id="X1", name="Olive oil, Greek", stock=Decimal(3))])
        self.assertEqual(reads.how_many("olive oil", two, NOW), "I can't find exactly that. Did you mean Olive oil, Greek, Sunshine olive oil?")

    def test_two_exact_items_ask_for_a_sku(self):
        two = snap(extra=[item(id="X1", name="hass AVOCADO", sku="S-9", stock=Decimal(1))])
        got = reads.how_many("hass avocado", two, NOW)
        self.assertIn("More than one item is called that", got)
        self.assertIn("SKU none", got)
        self.assertIn("SKU S-9", got)

    # Contract: reads answer for every count the mapper admits (spec: exact digits for huge and tiny counts; never a traceback). Bug caught:
    # a length cap in format_quantity raised InvalidOperation out of in_stock / how_many / low_stock for 1E+64 and 4E-64, and a lossy
    # fallback printed 4E-300 as '4E-300'.
    def test_in_stock_answers_for_huge_and_tiny_counts(self):
        edge = Decimal("1E+%d" % (mapper.MAX_PLAIN_DIGITS - 1))
        for raw, shown in (("1E+64", "1" + "0" * 64), ("4E-64", "0." + "0" * 63 + "4"), ("-4E-64", None), ("4E-300", "0." + "0" * 299 + "4"),
                           ("1.234567890123456789E+300", "1234567890123456789" + "0" * 282), (str(edge), "1" + "0" * (int(edge.adjusted()))), ):
            with self.subTest(raw=raw[:24]):
                s = snap(extra=[item(id="X9", name="Saffron", stock=Decimal(raw))])
                got = reads.in_stock("saffron", s, NOW)
                if shown is None:
                    self.assertEqual(got, "No, Saffron is sold out in the till.")    # negative: sold out, no number printed
                else:
                    self.assertEqual(got, f"Yes, Saffron: {shown} in the till.")
                self.assertTrue(reads.how_many("saffron", s, NOW).startswith("Saffron: "))
                self.assertIn("Saffron", reads.low_stock(s, NOW, Decimal("1E+1000")))

    # Contract: a count past the plain-digit boundary is still the till's count: answered in bounded exponent form, never "the till keeps no
    # count"; zero of any exponent is sold out. Bug caught: admission by plain length reported 1E+1000 and 0E-1000 as untracked.
    def test_counts_past_the_plain_digit_boundary_and_zero_exponents_answer_truthfully(self):
        edge = mapper.MAX_PLAIN_DIGITS
        for raw, got in (("1E+%d" % edge, "Yes, Saffron: 1E+%d in the till." % edge), ("1E+1000", "Yes, Saffron: 1E+1000 in the till."),
                         ("4E-1000", "Yes, Saffron: 4E-1000 in the till."), ("1.5E+2000000", "Yes, Saffron: 1.5E+2000000 in the till."),
                         ("4E-999999999999999999", "Yes, Saffron: 4E-999999999999999999 in the till."),
                         ("1E+999999999999999999", "Yes, Saffron: 1E+999999999999999999 in the till."),
                         ("0E-1000", "No, Saffron is sold out in the till."), ("0E+1000", "No, Saffron is sold out in the till."),
                         ("-0E+999999999999999999", "No, Saffron is sold out in the till.")):
            with self.subTest(raw=raw):
                s = snap(extra=[mapper.parse_item({"id": "X9", "name": "Saffron", "itemStock": {"quantity": raw}})])
                self.assertEqual(reads.in_stock("saffron", s, NOW), got)
                self.assertNotIn("keeps no count", reads.how_many("saffron", s, NOW))
                self.assertIn("Saffron", reads.low_stock(s, NOW, Decimal("1E+999999999999999999")))


def mugs(n, minutes_old=5):
    """n synthetic till items sharing one name, SKUs S0.., counts 0.. (made up)."""
    mug = [item(id=f"M{k}", name="Blue mug", sku=f"S{k}", stock=Decimal(k)) for k in range(n)]
    return reads.Snapshot(tuple(mug), NOW - timedelta(minutes=minutes_old))


def shown(n):
    return "; ".join(f"Blue mug (SKU S{k}): {k} in the till" for k in range(n)) + "."


class SameNameListTests(unittest.TestCase):
    """Contract: a same-name answer never hides that it stopped at five items (Mike must not act on a list he thinks is complete)."""
    ASKS = (("how_many", lambda s, **kw: reads.how_many("blue mug", s, NOW, **kw)),
            ("in_stock", lambda s, **kw: reads.in_stock("blue mug", s, NOW, **kw)))

    def test_eight_same_name_items_say_three_more(self):
        # Bug caught: the sixth to eighth items vanish without a word.
        for name, ask in self.ASKS:
            with self.subTest(ask=name):
                self.assertEqual(ask(mugs(8)), "More than one item is called that: " + shown(5) + " And 3 more.")

    def test_five_or_fewer_unchanged(self):
        # Healthy control, exact strings (green before and after): no 'more' sentence up to the limit.
        for n in (2, 5):
            for name, ask in self.ASKS:
                with self.subTest(n=n, ask=name):
                    self.assertEqual(ask(mugs(n)), "More than one item is called that: " + shown(n))

    def test_six_items_say_one_more(self):
        # Bug caught: an off-by-one at the limit (six is the first count that must add the sentence).
        for name, ask in self.ASKS:
            with self.subTest(ask=name):
                self.assertEqual(ask(mugs(6)), "More than one item is called that: " + shown(5) + " And 1 more.")

    def test_stale_label_still_wraps_the_longer_answer(self):
        # Bug caught: the new sentence is added outside the freshness wrapping, or changes where the label goes.
        body = "More than one item is called that: " + shown(5) + " And 3 more."
        for name, ask in self.ASKS:
            with self.subTest(ask=name):
                self.assertEqual(ask(mugs(8, 90)), body + " (till count as of 2:00 pm)")
                gone = ask(mugs(8, 90), reachable=False)
                self.assertTrue(gone.startswith("I can't reach the till right now."))
                self.assertTrue(gone.endswith(body))
                self.assertNotIn("more", ask(mugs(8, 30 * 60)))


class LowStockTests(unittest.TestCase):
    def test_sold_out_first_then_low_and_counts_untracked(self):
        out = [item(id="S1", name="Bread", stock=Decimal(0)), item(id="S2", name="Cheese", stock=Decimal("-1"))]
        got = reads.low_stock(snap(extra=out), NOW, 5)
        self.assertEqual(got, "Sold out: Cheese, Bread. Low (5 or fewer): Eggs, dozen 2. 1 item(s) have no count in the till, so I can't tell.")

    def test_nothing_low(self):
        self.assertEqual(reads.low_stock(snap(), NOW, 1), "Nothing is low. 1 item(s) have no count in the till, so I can't tell.")

    def test_hidden_items_are_left_out_and_the_list_is_capped(self):
        many = [item(id=f"L{n}", name=f"Low {n:02d}", stock=Decimal(n % 5 + 1)) for n in range(20)]
        got = reads.low_stock(snap(extra=many), NOW, 5)
        self.assertNotIn("Old honey", got)
        self.assertIn("And 6 more.", got)

    def test_mixed_groups_share_one_limit_and_count_only_what_is_left_out(self):
        def listed(text):
            return sum(text.count(f"Item {n:02d}") for n in range(40))
        for sold, low in ((1, 15), (1, 14), (3, 20), (15, 2), (16, 0), (0, 16)):
            with self.subTest(sold=sold, low=low):
                extra = [item(id=f"S{n}", name=f"Item {n:02d}", stock=Decimal(0)) for n in range(sold)]
                extra += [item(id=f"P{n}", name=f"Item {sold + n:02d}", stock=Decimal(2)) for n in range(low)]
                got = reads.low_stock(reads.Snapshot(tuple(extra), NOW - timedelta(minutes=5)), NOW, 5)
                shown = min(sold + low, reads.LIST_LIMIT)
                self.assertEqual(listed(got), shown)
                if sold + low > shown:
                    self.assertIn(f"And {sold + low - shown} more.", got)
                else:
                    self.assertNotIn("more.", got)

    def test_labels_apply_to_lists_too(self):
        self.assertTrue(reads.low_stock(snap(60), NOW, 5).endswith("(till count as of 2:30 pm)"))
        self.assertTrue(reads.low_stock(snap(60), NOW, 5, reachable=False).startswith("I can't reach the till"))
        self.assertIn("will not quote", reads.low_stock(snap(60 * 30), NOW, 5))


if __name__ == "__main__":
    unittest.main()
