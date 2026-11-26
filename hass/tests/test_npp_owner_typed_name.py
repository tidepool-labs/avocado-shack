"""H67: the product name the owner typed right after naming its maker outranks the photo read, like an "it is ..." line."""
import unittest

from hass.npp.job import owner_item
from hass.npp.missing import MissingInfo, OwnerPrice, owner_named_item, owner_typed_form, owner_typed_item
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
        for rest, name in (("pickles", "pickles"), ("dates and figs", "dates and figs"), ("hummus dip", "hummus dip"),
                           ("Swiss cheese", "Swiss cheese"), ("live culture yogurt", "live culture yogurt")):
            with self.subTest(rest=rest):
                self.assertEqual(owner_named_item((f"made by Maple Valley, Maple Valley {rest}",)), name)

    def test_a_maker_statement_outside_the_verb_list_is_not_an_item_name(self):
        # Contract: a clause that says what the maker does is not an item name. Bug: "produces honey" (a verb the filter
        # did not list) was taken as the name and overrode a confident photo; the filter now fails closed on a verb-first clause.
        for rest in ("produces honey", "bottles syrup", "supplies farms", "bakes bread", "make honey", "produce honey",
                     "we make honey", "they sell syrup"):
            with self.subTest(rest=rest):
                self.assertIsNone(owner_named_item((f"made by Maple Valley, Maple Valley {rest}",)))

    def test_the_item_clause_must_follow_the_made_by_clause(self):
        # Contract: only the name typed AFTER its maker counts. Bug: the product clause was taken from before the made-by clause.
        self.assertIsNone(owner_named_item(("Maple Valley honey, made by Maple Valley",)))
        self.assertIsNone(owner_named_item(("Maple Valley honey; made by Maple Valley, $15 each",)))
        self.assertEqual(owner_named_item(("made by Maple Valley, Maple Valley honey",)), "honey")
        self.assertEqual(owner_named_item(("made by Maple Valley; Maple Valley honey",)), "honey")


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


class _Decide(unittest.TestCase):
    def setUp(self):
        self.rules = MissingInfo(PINNED)
        self.reading = dict(EXAMPLES[1], item="maple syrup", kind="food", category_guess="pantry")

    def decide(self, caption, reading=None):
        from hass.npp.identify import Identifier
        from hass.tests.test_npp_identify import runner_output
        reading = Identifier(PINNED, runner=lambda _: runner_output(reading or self.reading)).read((b"fixture",)).evidence
        remainder, fields = caption_answers(caption)
        price = OwnerPrice(fields.get("price"), fields.get("price_unit", fields.get("sold_by")), unresolved_finance(remainder))
        form, typed = owner_typed_form((remainder,), owner_item)  # exactly as ProductionStages.start_plan passes it
        return self.rules.decide(reading, price=price, owner_item=typed if form == "it_is" else None,
                                 owner_named=typed if form == "made_by" else None, owner_texts=(remainder,))


class DecidePrecedenceTests(_Decide):
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


class MakerSentenceOrItemNameTests(unittest.TestCase):
    """#634 rule-29 checkpoint. The filter: a sentence about the maker gives None, a genuine item name keeps its typed
    shape. The filter is a first layer only; PairedDecisionControlTests show why a gap in it cannot silently replace a
    confident photo read (disposition A, t_8bbd055e)."""

    MAKER_SENTENCES = (
        # R2.1: a third-person verb followed by a connector and a place
        "works in Vermont", "lives in Vermont",
        # verbs no list names, caught by structure: verb + object, or a preposition + a place/business name
        "crafts honey", "whittles spoons", "hand-pours candles", "whittles in Vermont", "sold at Costco",
        "ships from Burlington", "roasts in small batches",
        # third-person forms of maker verbs that double as nouns
        "bakes", "brews with care", "farms with bees", "smokes with hickory",
        # statements anywhere in the clause
        "is family-owned", "family owned and operated", "headquartered in Vermont", "has bees",
        "will deliver", "could ship", "situated in Vermont",
        # R3 (t_dd93a1f8 @7dcca5b8): past tense and time phrases
        "opened last year", "moved here", "relocated to Barre", "expanded recently", "retired", "bakes daily",
        "for three generations", "started small")
    ITEM_NAMES = (
        # R2.2: plural-noun-first names
        "Brussels sprouts",
        # controls named in the returns
        "peaches in syrup", "dates and figs", "pickles", "hummus dip", "Swiss cheese", "live culture yogurt",
        "dark and robust maple syrup",
        # participle adjectives and verb-like nouns that are food words
        "smoked salmon", "cured salami", "pressed apple juice", "baked beans", "craft beer", "dark roast coffee",
        "cold brew coffee", "cinnamon rolls", "rolls", "preserves", "spreads", "fruit blends", "Calabrese salamini",
        "smoked and cured ham", "dried apricots", "whipped honey")

    def test_maker_sentences_are_not_item_names(self):
        for rest in self.MAKER_SENTENCES:
            with self.subTest(rest=rest):
                self.assertIsNone(owner_named_item((f"made by Maple Valley, Maple Valley {rest}",)))

    def test_item_names_keep_their_typed_shape(self):
        for rest in self.ITEM_NAMES:
            with self.subTest(rest=rest):
                self.assertEqual(owner_named_item((f"made by Maple Valley, Maple Valley {rest}",)), rest)

    def test_an_unusable_later_sentence_keeps_the_earlier_it_is_line(self):
        self.assertEqual(owner_typed_item(("it is honey", "made by Maple Valley, Maple Valley works in Vermont"),
                                          owner_item), "honey")
        self.assertEqual(owner_typed_item(("it is honey", "made by Maple Valley, Maple Valley Brussels sprouts"),
                                          owner_item), "Brussels sprouts")


class PairedDecisionControlTests(_Decide):
    """Rule-29 disposition A (t_8bbd055e). With a confident photo read of "maple syrup": a maker sentence never replaces
    it; a made-by name that agrees with it does (cases 8 and 10); a made-by name that disagrees with it is not used
    silently, the photo read is kept and the card says so, and the owner's "it is ..." line then wins. Without a
    confident photo read the made-by name names the item. So no filter gap can silently swap a confident identity."""

    def test_a_maker_sentence_never_overrides_the_confident_photo(self):
        self.assertGreaterEqual(self.reading["confidence"]["item"], 0.8)
        for rest in ("works in Vermont", "is based in Vermont", "produces honey", "crafts honey", "whittles in Vermont",
                     "sold at Costco", "opened last year", "moved here"):
            with self.subTest(rest=rest):
                decision = self.decide(f"made by Maple Valley, Maple Valley {rest}, $15 each")
                self.assertEqual(decision.item, "Maple Syrup")
                self.assertEqual(decision.maker.phrase, "Maple Valley")

    def test_a_filter_gap_against_a_confident_photo_keeps_the_photo_and_says_so(self):
        # The class R0-R3 kept finding: a maker sentence no test names ("whittles with care" passes the filter).
        self.assertEqual(owner_named_item(("made by Maple Valley, Maple Valley whittles with care",)), "whittles with care")
        decision = self.decide("made by Maple Valley, Maple Valley whittles with care, $15 each")
        self.assertEqual(decision.item, "Maple Syrup")
        self.assertTrue(decision.name_from_photo)
        self.assertTrue(decision.ready)

    def test_a_made_by_name_that_agrees_with_the_photo_names_the_item(self):
        for rest, item in (("dark and robust maple syrup", "Dark And Robust Maple Syrup"), ("maple syrups", "Maple Syrups"),
                           ("Grade A syrup", "Grade A Syrup")):
            with self.subTest(rest=rest):
                decision = self.decide(f"made by Maple Valley, Maple Valley {rest}, $15 each")
                self.assertEqual(decision.item, item)
                self.assertFalse(decision.name_from_photo)

    def test_a_conflicting_genuine_name_is_shown_not_silently_used_and_it_is_wins(self):
        for rest in ("Brussels sprouts", "dates and figs", "smoked salmon"):
            with self.subTest(rest=rest):
                decision = self.decide(f"made by Maple Valley, Maple Valley {rest}, $15 each")
                self.assertEqual(decision.item, "Maple Syrup")
                self.assertTrue(decision.name_from_photo)
        # His one-message correction after seeing the note is the "it is ..." field, which outranks the photo.
        self.assertEqual(owner_typed_form(("made by Maple Valley, Maple Valley Brussels sprouts", "it is Brussels sprouts"),
                                          owner_item), ("it_is", "Brussels sprouts"))
        decision = self.decide("it is Brussels sprouts, $15 each")
        self.assertEqual(decision.item, "Brussels Sprouts")
        self.assertFalse(decision.name_from_photo)

    def test_without_a_confident_photo_read_the_made_by_name_names_the_item(self):
        unsure = dict(self.reading, confidence=dict(self.reading["confidence"], item=0.3))
        decision = self.decide("made by Maple Valley, Maple Valley Brussels sprouts, $15 each", unsure)
        self.assertEqual(decision.item, "Brussels Sprouts")
        self.assertFalse(decision.name_from_photo)

    def test_the_card_note_fits_the_one_bracket(self):
        from hass.npp.reply import compose
        note = compose(self.rules.replies, {"name_from_photo": {}})
        self.assertEqual(note, 'name from the photo: say "it is …" to use yours')
        self.assertLessEqual(len(note) + 2, self.rules.replies["caps"]["bracket_max_chars"])
        both = compose(self.rules.replies, {"name_from_photo": {}, "basic_wording": {}})
        self.assertEqual(both, note)  # the lower-priority part is dropped, never this one


class StartPlanNameFromPhotoTests(unittest.TestCase):
    """Through the real caption intake and ProductionStages.start_plan (photo read "Fixture product", confidence 1)."""

    @classmethod
    def setUpClass(cls):
        from hass.npp import assets
        cls.pinned = assets()

    def plan(self, caption):
        from hass.tests.test_npp_caption_table import replay
        return replay(caption, "food", self.pinned)[2]

    def test_a_conflicting_made_by_name_keeps_the_photo_and_flags_the_card(self):
        listing = self.plan("made by Maple Valley, Maple Valley Brussels sprouts, $15 each").listing
        self.assertEqual(listing["name"], "Fixture Product")
        self.assertIs(listing.get("nameFromPhoto"), True)

    def test_an_agreeing_made_by_name_names_the_listing_without_a_flag(self):
        listing = self.plan("made by Maple Valley, Maple Valley smoked fixture product, $15 each").listing
        self.assertEqual(listing["name"], "Smoked Fixture Product")
        self.assertNotIn("nameFromPhoto", listing)

    def test_an_it_is_line_names_the_listing_without_a_flag(self):
        listing = self.plan("it is Brussels sprouts, $15 each").listing
        self.assertEqual(listing["name"], "Brussels Sprouts")
        self.assertNotIn("nameFromPhoto", listing)


if __name__ == "__main__":
    unittest.main()
