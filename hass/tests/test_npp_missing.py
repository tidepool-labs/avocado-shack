"""S3 fixture replay: only questions/eligibility, not draft or publish claims."""
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
import unittest

from hass.clover.reads import Snapshot
from hass.npp.identify import Identifier
from hass.npp.missing import MissingInfo, OwnerPrice
from hass.skills.item_intake import caption_answers, unresolved_finance
from hass.tests.test_npp_identify import EXAMPLES, PINNED, runner_output


class MissingTests(unittest.TestCase):
    def setUp(self):
        self.rules = MissingInfo(PINNED)

    def test_product_cases_13_through_18_and_missing_price_22(self):
        # These are the stage projections of the NPP cases; no image edit, draft or send is requested here.
        rows = (
            (13, EXAMPLES[0], "wood glue $5; paid $3; got 12", "Wood Glue", "general", (), True),
            (14, EXAMPLES[2], "lavender honey candle $18", "Lavender Honey Soy Candle", "general", (), True),
            (15, dict(EXAMPLES[0], item="elderberry syrup", kind="food", category_guess="pantry",
                      visible_claims=["immune support"]), "elderberry syrup $7", "Elderberry Syrup", "pantry", (), True),
            (16, EXAMPLES[3], "from Etto $3.50 a lb", "Persimmons", "fruit", (), True),
            (17, EXAMPLES[1], "raspberry jam $7", "Raspberry Jam", "pantry", (), True),
            (18, EXAMPLES[4], "add this", None, None, ("identity",), False),
            (18, EXAMPLES[5], "add this", None, None, ("identity",), False),
            (22, dict(EXAMPLES[1], item="honey"), "new honey", "Honey", "pantry", ("selling_price",), False),
        )
        for case, raw, caption, name, category, qids, ready in rows:
            with self.subTest(case=case, photo=raw["kind"]):
                reading = Identifier(PINNED, runner=lambda _: runner_output(raw)).read((b"fixture",)).evidence
                remainder, fields = caption_answers(caption)
                price = OwnerPrice(fields.get("price"), fields.get("price_unit", fields.get("sold_by")), unresolved_finance(remainder))
                decision = self.rules.decide(reading, price=price, owner_texts=(remainder,))
                self.assertEqual((decision.item, decision.category, decision.ready), (name, category, ready))
                self.assertEqual(tuple(q for q, _ in decision.questions), qids)
                self.assertIs(decision.identified, name is not None)
                self.assertEqual(decision.maker.state, "absent" if name else "unidentified")
                if case == 16:
                    self.assertEqual(decision.price, OwnerPrice("3.50", "pound"))
                if not name:
                    self.assertFalse(decision.maker.research_allowed)
                self.assertNotIn("Post this?", str(decision.questions))

    def test_no_photo_or_ambiguous_owner_price_can_satisfy_essentials(self):
        # Do not treat an old/ambiguous price or basket unit as publishable.
        cases = ((OwnerPrice(), "selling_price", "ask_price_unit"),
                 (OwnerPrice(None, "item"), "selling_price", "ask_price"),
                 (OwnerPrice("5.00", "item", unresolved=True), "selling_price", "ask_price"),
                 (OwnerPrice("5.00", "basket"), "price_unit", "ask_unit"))
        for price, q, template in cases:
            with self.subTest(price=price):
                evidence = dict(EXAMPLES[1], sellingPrice="5.00")
                result = self.rules.decide(evidence, price=price)
                self.assertEqual(result.questions, ((q, PINNED[2]["questions"][template]),))
                self.assertFalse(result.ready)
                self.assertIsNone(result.price.amount if q == "selling_price" else result.price.unit)

    def test_maker_exact_near_negation_and_case_31_contradiction(self):
        # Exact reuse must not call research; fuzzy matching and contradictory labels are not authority.
        makers = {"miners": {"name": "Miners", "town": "Fixture town"}, "acme": {"name": "Acme"}}
        price = OwnerPrice("7.00", "item")
        jam = dict(EXAMPLES[1], brand_on_label=None)
        for words, key in (("made by Miners", "miners"), ("Acme’s Raspberry jam", "acme")):
            result = self.rules.decide(jam, price=price, makers=makers, owner_texts=(words,))
            self.assertEqual(result.maker.record, makers[key])
            self.assertFalse(result.maker.research_allowed)
            self.assertTrue(result.ready)
        for words in (("from Miners",), ("made by Miners", "not Miners"), ("made by Miners maybe",)):
            self.assertEqual(self.rules.decide(jam, price=price, makers=makers, owner_texts=words).maker.state, "absent")
        near = self.rules.decide(jam, price=price, makers=makers, owner_texts=("made by Miner",))
        self.assertEqual(near.questions, (("near_maker", "Is that the Miners already on the website?"),))
        # A "yes" to near_maker keeps the matched record (bug: it was dropped and read as no maker).
        confirmed = self.rules.decide(jam, price=price, makers=makers, owner_texts=("made by Miner",), near_maker_confirmed=True)
        self.assertEqual((confirmed.maker.state, confirmed.maker.key, confirmed.maker.record), ("known", "miners", makers["miners"]))
        self.assertEqual(confirmed.questions, ())
        self.assertFalse(confirmed.maker.research_allowed)
        self.assertTrue(confirmed.ready)
        # An explicit "no" is not an unanswered question (bug: False read as unanswered and left state near, research off);
        # the owner-named maker stays new and may be researched; an unanswered, already-asked one stays near.
        rejected = self.rules.decide(jam, price=price, makers=makers, owner_texts=("made by Miner",),
                                     ask_counts={"near_maker": 1}, near_maker_confirmed=False)
        self.assertEqual((rejected.maker.state, rejected.maker.phrase, rejected.maker.record), ("new", "Miner", None))
        self.assertEqual(rejected.questions, ())
        self.assertTrue(rejected.maker.research_allowed)
        self.assertTrue(rejected.ready)
        unanswered = self.rules.decide(jam, price=price, makers=makers, owner_texts=("made by Miner",),
                                       ask_counts={"near_maker": 1}, near_maker_confirmed=None)
        self.assertEqual((unanswered.maker.state, unanswered.maker.record), ("near", None))
        self.assertFalse(unanswered.maker.research_allowed)
        # No owner-named maker (bug: absent allowed research) and an unconfirmed near match never license research.
        self.assertEqual(self.rules.decide(jam, price=price, makers=makers).maker.state, "absent")
        self.assertFalse(self.rules.decide(jam, price=price, makers=makers).maker.research_allowed)
        self.assertTrue(self.rules.decide(jam, price=price, makers=makers, owner_texts=("made by Zed",)).maker.research_allowed)
        capped = self.rules.decide(jam, makers=makers, owner_texts=("made by Miner",),
                                   products=[{"name": "Raspberry Jam"}])
        self.assertEqual(tuple(q for q, _ in capped.questions), ("selling_price", "duplicate"))
        self.assertIsNone(capped.maker.record)
        self.assertFalse(capped.maker.research_allowed)
        contradiction = self.rules.decide(EXAMPLES[1], price=price, makers=makers, owner_texts=("made by Miners",))
        self.assertEqual(contradiction.maker.state, "contradictory")
        self.assertFalse(contradiction.maker.research_allowed)
        self.assertEqual(contradiction.note, "maker left off: label says Hillside Kitchen")
        self.assertTrue(contradiction.ready)

    def test_made_by_outranks_a_possessive_read_of_the_same_maker(self):
        # Golden cases 4/5 (live recording): "made by Brian's, Brian's sourdough bread" was read as the possessive
        # "Brian" (near, so a needless "Is that the Brian's already on the website?") instead of the typed "Brian's".
        makers = {"Brian's": {"name": "Brian's"}, "acme": {"name": "Acme"}}
        price = OwnerPrice("8.00", "item")
        jam = dict(EXAMPLES[1], brand_on_label=None)
        for words in (("made by Brian's, Brian's Raspberry jam, $8 each",), ("Brian's Raspberry jam, made by Brian's",),
                      ("made by Brian's", "Brian's Raspberry jam")):
            with self.subTest(words=words):
                result = self.rules.decide(jam, price=price, makers=makers, owner_texts=words)
                self.assertEqual((result.maker.state, result.maker.key), ("known", "Brian's"))
                self.assertEqual(result.questions, ())
        # Possessive alone still strips the suffix, and a hedged "made by" still names no maker.
        alone = self.rules.decide(jam, price=price, makers=makers, owner_texts=("Acme’s Raspberry jam",))
        self.assertEqual((alone.maker.state, alone.maker.key), ("known", "acme"))
        hedged = self.rules.decide(jam, price=price, makers=makers, owner_texts=("made by Acme maybe, Acme’s Raspberry jam",))
        self.assertEqual(hedged.maker.state, "absent")

    def test_duplicate_exact_local_name_prompts_once_and_never_waives_confirmation(self):
        # Same-name catalog/maker/till rows are one bounded question; private cached values are not read back.
        jam = dict(EXAMPLES[1], item="Raspberry Jam")
        till = Snapshot((SimpleNamespace(name="raspberry jam", stock=12345),), datetime.now(timezone.utc))
        args: dict[str, Any] = dict(products=[{"name": "RASPBERRY JAM"}], makers={"raspberry jam": {"name": "Other"}}, clover=till)
        result = self.rules.decide(jam, **args)
        self.assertEqual(result.duplicate_sources, ("catalog", "makers", "clover"))
        self.assertEqual(tuple(q for q, _ in result.questions), ("selling_price", "duplicate"))
        self.assertLessEqual(len(" ".join(text for _, text in result.questions)), 160)
        self.assertNotIn("12345", str(result))
        price = OwnerPrice("7.00")
        refused = self.rules.decide(jam, price=price, ask_counts={"duplicate": 1}, **args)
        self.assertFalse(refused.ready)
        self.assertEqual(refused.questions, ())
        self.assertTrue(self.rules.decide(jam, price=price, duplicate_confirmed=True, **args).ready)

    def test_exhausted_or_answered_ids_do_not_repeat_or_authorize_incomplete_card(self):
        # Durable IDs, not wording, delimit retries; exhausted questions are still missing essentials.
        for counts, answered in (({"selling_price": 2}, ()), ({}, ("selling_price",))):
            result = self.rules.decide(EXAMPLES[0], ask_counts=counts, answered=answered)
            self.assertFalse(result.ready)
            self.assertEqual(result.missing, ("selling_price",))
            self.assertEqual(result.questions, ())
