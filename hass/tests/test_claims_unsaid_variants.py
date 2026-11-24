"""AV1124A-08 tests: a draft that adds a claim wording variant or a hyphenated hike quantity the owner never said asks.

Same NB-AV-05 rules as test_claims and test_claims_numbers (folded text, negation, counts against the text before).
Run: python3 -B -m unittest hass.tests.test_claims_unsaid_variants -v
"""

import unittest

from hass import claims
from hass.tests.test_claims import MAKERS, edit

POST = "post a hike Saturday 9am at Cass Hill"
EV = dict(field="distance", collection="events", key="h1")
# (draft text, term the question names, an owner message that says it)
VARIANT_TERMS = (
    ("Organically grown wildflower honey.", "organically", "it is organically grown"),
    ("GMO free honey.", "gmo-free", "it is gmo-free"),
    ("GMO-free honey.", "gmo-free", "it is gmo free"),
    ("Preservative free jam.", "preservative-free", "preservative-free jam"),
    ("Sulfite-free wine vinegar.", "sulfite-free", "sulfite free"),
    ("Sulphite-free wine vinegar.", "sulphite-free", "sulphite free"),
    ("No pesticides used.", "no pesticides", "we use no pesticides"),
)
# (draft text, quantity the question names, owner spellings of the same number and unit)
HYPHEN_UNITS = (
    ("Easy 2-mile loop.", "2-mile", ("2 miles", "2-mile", "2 mi")),
    ("A 3-hour walk", "3-hour", ("3 hours", "3-hour", "3 hrs")),
    ("A 90-minute walk", "90-minute", ("90 minutes", "90-minute", "90 min")),
    ("An 800-foot climb", "800-foot", ("800 feet", "800 ft", "800-foot")),
    ("A 5-km route", "5-km", ("5 km", "5 kilometers", "5-km")),
    ("A 2-mi walk", "2-mi", ("2 miles", "2 mi", "2-mi")),
    ("A 3-hr walk", "3-hr", ("3 hours", "3-hr", "3 hrs")),
)


def terms(after, owner="", field="description", collection="products", **kw):
    return [t for _w, t in claims.unstated(edit(None, after, field=field, collection=collection, **kw), owner, MAKERS)]


class VariantTermTests(unittest.TestCase):
    def test_variant_terms_asked_unless_owner_said(self):
        # Contract: a claim wording the whole-word term list misses ("organically", "gmo free") still asks the owner.
        # Bug it catches: the variant is left out of the term patterns, so the draft goes out with no question.
        for text, term, said in VARIANT_TERMS:
            with self.subTest(term=term, text=text):
                self.assertEqual(terms(text, POST), [term])
                self.assertEqual(terms(text, said), [])
        organically = "Organically grown wildflower honey."
        self.assertEqual(terms(organically, "it is organic honey"), [])  # an owner's "organic" backs "organically"
        self.assertEqual(terms(organically, "it is not organic"), ["organically"])  # a negated word backs nothing
        self.assertEqual(terms("Organic honey.", "it is organically grown"), ["organic"])  # but not the other way round

    def test_variant_terms_are_apart_from_the_pinned_terms(self):
        # Contract: TERMS stays as pinned; the variants live in their own tuple.
        mine = [v for v in vars(claims).values() if isinstance(v, tuple) and "no pesticides" in v]
        self.assertEqual(len(mine), 1)
        self.assertFalse(set(mine[0]) & set(claims.TERMS))
        self.assertEqual(len(mine[0]), 6)


class HyphenUnitTests(unittest.TestCase):
    def test_hyphen_units_are_unsaid_quantities(self):
        # Contract: "2-mile" is the same (number, unit) as "2 miles". Bug it catches: the quantity pattern needs a space
        # before the unit, so a hike length or duration the owner never gave goes out unasked.
        for text, qty, said in HYPHEN_UNITS:
            with self.subTest(qty=qty):
                self.assertEqual(terms(text, POST, **EV), [qty])
                for owner in said:
                    self.assertEqual(terms(text, f"{POST}, {owner}", **EV), [], owner)

    def test_hyphen_unit_is_the_same_pair_as_the_spaced_form(self):
        self.assertEqual(terms("Easy 2 miles.", POST, **EV), ["2 miles"])
        self.assertEqual(terms("Easy 2-mile loop.", "a 3 mile walk", **EV), ["2-mile"])  # another number
        self.assertEqual(terms("Easy 2-mile loop.", "2 km", **EV), ["2-mile"])  # another unit
        self.assertEqual(terms("Easy 2 miles.", "a 2-mile walk", **EV), [])  # spaced draft, hyphen owner


class UnchangedTests(unittest.TestCase):
    def test_ranges_and_existing_terms_unchanged(self):
        # Healthy control: what the gate did before this change stays exactly as it was.
        self.assertEqual(terms("Certified organic honey.", POST), ["organic", "certified"])
        self.assertEqual(terms("Certified organic honey.", "certified organic"), [])
        self.assertEqual(terms("A 2-5 miles loop", POST, **EV), ["2-5 miles"])  # a range still gives both ends
        self.assertEqual(terms("A 2-5 miles loop", "2 to 5 miles", **EV), [])
        self.assertEqual(terms("A 2-5 miles loop", "2 miles", **EV), ["2-5 miles"])  # 5 miles is still unsaid
        self.assertEqual(terms("10h and 5k", POST, **EV), [])  # "h" alone is not a unit; "5k" is not 5 km
        self.assertEqual(terms("a 3-h walk", POST, **EV), [])
        self.assertEqual(terms("Takes 90 minutes", POST, **EV), ["90 minutes"])


if __name__ == "__main__":
    unittest.main()
