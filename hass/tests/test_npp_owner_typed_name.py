"""H67: the product name the owner typed right after naming its maker outranks the photo read, like an "it is ..." line."""
import unittest

from hass.npp.job import owner_item
from hass.npp.missing import MissingInfo, OwnerPrice, owner_named_item, owner_typed_item
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

    def test_a_clause_that_describes_the_maker_is_not_an_item_name(self):
        # Contract: only an item name counts. Bug: "Maple Valley is based in Vermont" gave "is based in Vermont" as owner_item.
        for rest in ("is based in Vermont", "are a family farm", "was founded in 1990", "has been around a while",
                     "in Vermont", "from Vermont", "and Sons", "makes syrup", "located in Vermont", "that sells honey"):
            with self.subTest(rest=rest):
                self.assertIsNone(owner_named_item((f"made by Maple Valley, Maple Valley {rest}",)))

    def test_item_names_with_plain_connecting_words_still_count(self):
        self.assertEqual(owner_named_item(("made by Maple Valley, Maple Valley peaches in syrup",)), "peaches in syrup")
        self.assertEqual(owner_named_item(("made by Maple Valley, Maple Valley dark and robust maple syrup",)),
                         "dark and robust maple syrup")


class OrderedOwnerItemTests(unittest.TestCase):
    # Contract: of the two owner-item forms, the one typed last wins. Bug: any "it is ..." line beat a later made-by name.
    def test_a_later_made_by_name_beats_an_earlier_it_is_line(self):
        texts = ("it is honey", "made by Maple Valley, Maple Valley maple syrup")
        self.assertEqual(owner_typed_item(texts, owner_item), "maple syrup")

    def test_a_later_it_is_line_beats_an_earlier_made_by_name(self):
        texts = ("made by Maple Valley, Maple Valley maple syrup", "it is honey")
        self.assertEqual(owner_typed_item(texts, owner_item), "honey")

    def test_a_later_message_with_neither_form_keeps_the_earlier_one(self):
        self.assertEqual(owner_typed_item(("it is honey", "make it $16"), owner_item), "honey")
        self.assertEqual(owner_typed_item(("made by Maple Valley, Maple Valley maple syrup", "thanks"), owner_item), "maple syrup")

    def test_an_unusable_later_made_by_clause_does_not_erase_an_earlier_it_is_line(self):
        texts = ("it is honey", "made by Maple Valley, Maple Valley is based in Vermont")
        self.assertEqual(owner_typed_item(texts, owner_item), "honey")

    def test_no_owner_item_at_all_gives_none(self):
        self.assertIsNone(owner_typed_item(("made by Maple Valley, $15 each", "hello"), owner_item))


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
        return self.rules.decide(reading, price=price, owner_item=owner_typed_item((remainder,), owner_item), owner_texts=(remainder,))

    def test_owner_typed_name_outranks_the_photo_read(self):
        decision = self.decide("made by Maple Valley, Maple Valley dark and robust maple syrup, $15 each")
        self.assertEqual(decision.item, "Dark And Robust Maple Syrup")
        self.assertTrue(decision.ready)
        self.assertEqual(decision.maker.phrase, "Maple Valley")

    def test_a_maker_description_clause_keeps_the_photo_read(self):
        decision = self.decide("made by Maple Valley, Maple Valley is based in Vermont, $15 each")
        self.assertEqual(decision.item, "Maple Syrup")
        self.assertTrue(decision.ready)

    def test_without_an_owner_typed_name_the_photo_read_is_kept(self):
        decision = self.decide("made by Maple Valley, $15 each")
        self.assertEqual(decision.item, "Maple Syrup")
        self.assertTrue(decision.ready)


if __name__ == "__main__":
    unittest.main()
