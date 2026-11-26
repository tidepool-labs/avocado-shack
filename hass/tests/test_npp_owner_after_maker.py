"""H68: the item name the owner typed as the clause right after "made by M" (without repeating M) names a confident
photo read it agrees with; anything else in that spot (a town, a maker sentence, another product) is ignored silently."""
import unittest

from hass.npp.job import owner_item
from hass.npp.missing import MissingInfo, OwnerPrice, owner_after_maker, owner_typed_form
from hass.skills.item_intake import caption_answers, unresolved_finance
from hass.tests.test_npp_identify import EXAMPLES, PINNED

CHIPS = "made by Taco Works, Montaña de Oro Sea Salt tortilla chips, $5 each"


class OwnerAfterMakerTests(unittest.TestCase):
    def test_golden_intake_lines_give_the_clause_after_the_maker(self):
        for text, name in ((CHIPS, "Montaña de Oro Sea Salt tortilla chips"),
                           ("made by Mighty Cap Mushrooms, Dried mushrooms, $11 each", "Dried mushrooms"),
                           ("made by Fair Hills Farm; apple juice", "apple juice")):
            with self.subTest(text=text):
                self.assertEqual(owner_after_maker((text,)), name)

    def test_the_finance_free_remainder_from_intake_still_names_it(self):
        remainder, fields = caption_answers(CHIPS)
        self.assertEqual(fields.get("price"), "5.00")
        self.assertEqual(owner_after_maker((remainder,)), "Montaña de Oro Sea Salt tortilla chips")

    def test_no_single_made_by_clause_or_nothing_after_it_gives_none(self):
        for texts in (("Montaña de Oro tortilla chips, $5 each",), ("made by Taco Works",), ("made by Taco Works, $5 each",),
                      ("tortilla chips, made by Taco Works",), ("made by Taco Works, made by Acme, tortilla chips",),
                      (), ("",)):
            with self.subTest(texts=texts):
                self.assertIsNone(owner_after_maker(texts))

    def test_hedges_prices_digits_and_maker_sentences_give_none(self):
        for rest in ("maybe tortilla chips", "tortilla chips?", "chips or salsa", "tortilla chips 12 oz",
                     "Paso Robles. plum preserves $8 each", "is based in San Luis Obispo", "in San Luis Obispo",
                     "makes tortilla chips", "was founded in 1976", "family owned"):
            with self.subTest(rest=rest):
                self.assertIsNone(owner_after_maker((f"made by Taco Works, {rest}",)))

    def test_the_latest_message_wins(self):
        self.assertEqual(owner_after_maker(("made by Taco Works, tortilla chips", "made by Taco Works, blue corn chips")),
                         "blue corn chips")
        self.assertEqual(owner_after_maker(("made by Taco Works, tortilla chips", "make it $6")), "tortilla chips")


class _Decide(unittest.TestCase):
    def setUp(self):
        self.rules = MissingInfo(PINNED)
        self.reading = dict(EXAMPLES[1], item="sea salt tortilla chips", kind="food", category_guess="pantry",
                            brand_on_label="Taco Works")

    def decide(self, caption, reading=None, earlier=()):
        from hass.npp.identify import Identifier
        from hass.tests.test_npp_identify import runner_output
        reading = Identifier(PINNED, runner=lambda _: runner_output(reading or self.reading)).read((b"fixture",)).evidence
        remainder, fields = caption_answers(caption)
        price = OwnerPrice(fields.get("price"), fields.get("price_unit", fields.get("sold_by")), unresolved_finance(remainder))
        texts = (*earlier, remainder)
        form, typed = owner_typed_form(texts, owner_item)  # exactly as ProductionStages.start_plan passes them
        return self.rules.decide(reading, price=price, owner_item=typed if form == "it_is" else None,
                                 owner_named=typed if form == "made_by" else None,
                                 owner_after_maker=owner_after_maker(texts) if form is None else None, owner_texts=texts)


class DecideAfterMakerTests(_Decide):
    def test_an_agreeing_name_after_the_maker_names_the_confident_photo_read(self):
        self.assertGreaterEqual(self.reading["confidence"]["item"], 0.8)
        decision = self.decide(CHIPS)
        self.assertEqual(decision.item.casefold(), "montaña de oro sea salt tortilla chips")
        self.assertFalse(decision.name_from_photo)
        self.assertTrue(decision.ready)
        self.assertEqual(decision.maker.phrase, "Taco Works")

    def test_a_town_after_the_maker_keeps_the_photo_read_without_a_note(self):
        for caption in ("made by Taco Works, San Luis Obispo, $5 each", "made by Taco Works, Paso Robles, $5 each"):
            with self.subTest(caption=caption):
                decision = self.decide(caption)
                self.assertEqual(decision.item, "Sea Salt Tortilla Chips")
                self.assertFalse(decision.name_from_photo)
                self.assertTrue(decision.ready)

    def test_a_maker_sentence_or_another_product_never_replaces_the_photo_read(self):
        for rest in ("whittles with care", "sells tortilla chips", "salsa", "sea salt crackers", "pours tortilla chips"):
            with self.subTest(rest=rest):
                decision = self.decide(f"made by Taco Works, {rest}, $5 each")
                self.assertEqual(decision.item, "Sea Salt Tortilla Chips")
                self.assertFalse(decision.name_from_photo)
                self.assertTrue(decision.ready)

    def test_a_different_product_sharing_the_head_word_never_replaces_the_photo_read(self):
        # Contract: the weaker after-maker clause only adds words to the photo's name. Bug it catches: "almond butter"
        # shares the head "butter" with a confident "peanut butter" read and was promoted as a silent substitution.
        reading = dict(self.reading, item="peanut butter")
        for rest in ("almond butter", "cashew butter", "sunflower seed butter"):
            with self.subTest(rest=rest):
                decision = self.decide(f"made by Taco Works, {rest}, $5 each", reading)
                self.assertEqual(decision.item, "Peanut Butter")
                self.assertFalse(decision.name_from_photo)
                self.assertTrue(decision.ready)
        decision = self.decide("made by Taco Works, Crunchy peanut butter, $5 each", reading)
        self.assertEqual(decision.item, "Crunchy Peanut Butter")

    def test_without_a_confident_photo_read_the_clause_is_not_used(self):
        unsure = dict(self.reading, confidence=dict(self.reading["confidence"], item=0.2))
        decision = self.decide(CHIPS, unsure)
        self.assertIsNone(decision.item)
        self.assertIn("identity", decision.missing)

    def test_stronger_forms_keep_their_meaning(self):
        # an "it is ..." line (its own message, either order) still outranks the clause after the maker
        decision = self.decide(CHIPS, earlier=("it is blue corn chips",))
        self.assertEqual(decision.item, "Blue Corn Chips")
        decision = self.decide("it is blue corn chips", earlier=(CHIPS,))
        self.assertEqual(decision.item, "Blue Corn Chips")
        # a message that mixes "it is" into a sentence is not an "it is" line (job.owner_item reads whole lines only)
        decision = self.decide("it is blue corn chips, made by Taco Works, tortilla chips, $5 each")
        self.assertEqual(decision.item, "Tortilla Chips")
        # the H67 "made by M, M <name>" form is unchanged: a disagreeing name keeps the photo and says so
        decision = self.decide("made by Taco Works, Taco Works salsa verde, $5 each")
        self.assertEqual(decision.item, "Sea Salt Tortilla Chips")
        self.assertTrue(decision.name_from_photo)
        decision = self.decide("made by Taco Works, Taco Works blue corn tortilla chips, $5 each")
        self.assertEqual(decision.item.casefold(), "blue corn tortilla chips")
        self.assertFalse(decision.name_from_photo)


if __name__ == "__main__":
    unittest.main()
