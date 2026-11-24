"""AV1124C-13: one table of which phrases the stock.restock skill reads as a count and which as a date or a wait.

hass/skills/restock.py QUANTITY decides; _counted(ctx) is its only reader. A counted request is refused whole ("I don't keep counts
yet"): nothing is written, not even the day (G: counts stay private). test_skills_restock.py covers single phrases; this is the table
of the boundary. Synthetic inputs only: a bare ctx holding ``texts`` (no content, clock or network). Source files are not edited.

Owner observations, NOT pinned (current behaviour, may be wrong either way; the owner decides, then this table changes):
  "12 oz jam is back Friday"  reads as a count (a product size is taken for a quantity)
  "30 more on Friday"         is not seen as a count (a number with no unit of goods)

Run: python3 -B -m unittest hass.tests.test_restock_quantity_table -v
"""
import copy
import unittest
from types import SimpleNamespace

from hass.skills import restock as rs

HONEY = "photo-product-042"
# (phrase, is it a count). Counts: a number or spelled number with a unit of goods, "x40". Not counts: a day, a date, a wait, a time.
TABLE = (
    ("got 40 jars, back Friday", True),
    ("x40", True),
    ("two dozen eggs Friday", True),
    ("a dozen jars Friday", True),
    ("5 lb bag back Monday", True),
    ("forty more cases Monday", True),
    ("10 g tin", True),
    ("more salt coming Friday", False),
    ("in 2 weeks", False),
    ("the 14th", False),
    ("back in 3 days", False),
    ("2 pm Friday", False),
)


def ctx(*texts):
    return SimpleNamespace(texts=list(texts))


class QuantityTable(unittest.TestCase):
    # Contract: a number with a unit of goods is a count. Fails if QUANTITY stops seeing one (a unit dropped, the spoken or "x40" branch lost).
    def test_clear_counts_are_counted(self):
        for phrase, expected in TABLE:
            if expected:
                with self.subTest(phrase=phrase):
                    self.assertIs(rs._counted(ctx(phrase)), True)

    # Contract: a date or a wait is not a count. Fails if QUANTITY grows to read "in 2 weeks", "the 14th" or "2 pm" as a quantity,
    # which would refuse every restock day the owner gives in those words.
    def test_dates_and_waits_are_not_counts(self):
        for phrase, expected in TABLE:
            if not expected:
                with self.subTest(phrase=phrase):
                    self.assertIs(rs._counted(ctx(phrase)), False)

    # Contract: a counted request is refused whole with the counts sentence and nothing is planned or written, even with a good
    # item and day. Fails if the refusal is dropped (the day gets written beside the dropped count) or reworded.
    def test_counted_request_is_refused_with_the_counts_sentence(self):
        slots = {"item": HONEY, "day": "2026-11-12"}
        before = copy.deepcopy(slots)
        for phrase, expected in TABLE:
            if expected:
                with self.subTest(phrase=phrase):
                    with self.assertRaises(rs.Refusal) as caught:
                        rs._plan(slots, SimpleNamespace(today="2026-11-08", texts=[phrase]))
                    self.assertEqual(caught.exception.reply, rs.COUNTS_REFUSED)
                    self.assertEqual(slots, before)
        # healthy control: the same slots with a wait in the words plan the day, so the refusal above is the count and nothing else
        control = rs._plan(slots, SimpleNamespace(today="2026-11-08", texts=["more honey back Thursday"]))
        self.assertEqual(control, [{"op": "product.set_restock", "args": {"id": HONEY, rs.FIELD: "2026-11-12"}}])


if __name__ == "__main__":
    unittest.main()
