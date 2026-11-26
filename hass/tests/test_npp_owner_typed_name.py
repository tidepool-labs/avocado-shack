"""H67: the product name the owner typed right after naming its maker outranks the photo read, like an "it is ..." line."""
import unittest

from hass.npp.missing import MissingInfo, OwnerPrice, owner_named_item
from hass.skills.item_intake import caption_answers, unresolved_finance
from hass.tests.test_npp_identify import EXAMPLES, PINNED


class OwnerNamedItemTests(unittest.TestCase):
    def test_golden_intake_lines_give_the_owner_typed_name(self):
        for text, name in (
                ("made by Maple Valley, Maple Valley dark and robust maple syrup, $15 each", "dark and robust maple syrup"),
                ("made by Alle-Pia, Alle-Pia Calabrese salamini, $14 each", "Calabrese salamini"),
                ("made by Big Sur Honey Company, Big Sur Honey Company honey, $12 each", "honey"),
                ("made by Fair Hills Farm; Fair Hills Farm apple juice", "apple juice"),
                ("made by Brian's, Brian's sourdough bread", "sourdough bread")):
            with self.subTest(text=text):
                self.assertEqual(owner_named_item((text,)), name)

    def test_the_finance_free_remainder_from_intake_still_names_it(self):
        remainder, fields = caption_answers("made by Maple Valley, Maple Valley dark and robust maple syrup, $15 each")
        self.assertEqual(fields.get("price"), "15.00")
        self.assertEqual(owner_named_item((remainder,)), "dark and robust maple syrup")

    def test_no_made_by_clause_or_no_clause_after_it_gives_none(self):
        for texts in (("Maple Valley dark and robust maple syrup, $15 each",), ("made by Maple Valley, $15 each",),
                      ("made by Maple Valley",), ("made by Maple Valley, Maple Valley",), (), ("",)):
            with self.subTest(texts=texts):
                self.assertIsNone(owner_named_item(texts))

    def test_the_clause_must_start_with_the_exact_maker_at_a_word_boundary(self):
        self.assertIsNone(owner_named_item(("made by Maple, Maplewood syrup",)))
        self.assertIsNone(owner_named_item(("made by Maple Valley, fresh Maple Valley syrup",)))
        self.assertIsNone(owner_named_item(("made by Maple Valley, Valley maple syrup",)))

    def test_hedges_questions_prices_and_digits_give_none(self):
        for rest in ("maybe maple syrup", "maple syrup?", "not maple syrup", "syrup or honey", "maple syrup 12 oz",
                     "maple syrup $15", "something like maple syrup"):
            with self.subTest(rest=rest):
                self.assertIsNone(owner_named_item((f"made by Maple Valley, Maple Valley {rest}",)))

    def test_two_makers_or_two_named_clauses_in_one_message_are_ambiguous(self):
        self.assertIsNone(owner_named_item(("made by Maple Valley, made by Acme, Maple Valley syrup",)))
        self.assertIsNone(owner_named_item(("made by Maple Valley, Maple Valley syrup, Maple Valley honey",)))

    def test_the_latest_message_wins(self):
        texts = ("made by Maple Valley, Maple Valley maple syrup", "made by Maple Valley, Maple Valley dark maple syrup")
        self.assertEqual(owner_named_item(texts), "dark maple syrup")
        self.assertEqual(owner_named_item(("made by Maple Valley, Maple Valley maple syrup", "make it $16")), "maple syrup")


class DecidePrecedenceTests(unittest.TestCase):
    def setUp(self):
        self.rules = MissingInfo(PINNED)
        self.reading = dict(EXAMPLES[1], item="maple syrup", kind="food", category_guess="pantry")

    def decide(self, caption):
        from hass.npp.identify import Identifier
        from hass.tests.test_npp_identify import runner_output
        reading = Identifier(PINNED, runner=lambda _: runner_output(self.reading)).read((b"fixture",)).evidence
        remainder, fields = caption_answers(caption)
        price = OwnerPrice(fields.get("price"), fields.get("price_unit", fields.get("sold_by")), unresolved_finance(remainder))
        return self.rules.decide(reading, price=price, owner_item=owner_named_item((remainder,)), owner_texts=(remainder,))

    def test_owner_typed_name_outranks_the_photo_read(self):
        decision = self.decide("made by Maple Valley, Maple Valley dark and robust maple syrup, $15 each")
        self.assertEqual(decision.item, "Dark And Robust Maple Syrup")
        self.assertTrue(decision.ready)
        self.assertEqual(decision.maker.phrase, "Maple Valley")

    def test_without_an_owner_typed_name_the_photo_read_is_kept(self):
        decision = self.decide("made by Maple Valley, $15 each")
        self.assertEqual(decision.item, "Maple Syrup")
        self.assertTrue(decision.ready)


if __name__ == "__main__":
    unittest.main()
