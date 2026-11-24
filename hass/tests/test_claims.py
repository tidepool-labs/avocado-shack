"""NB-AV-05 tests: a draft that adds organic, origin or maker claims not in the owner's words asks, never drafts.

The pure check runs on hand-made draft records; the conversation tests reuse the H05 fixture conversation
(ConversationTestCase) with the production ops registry and the throwaway writer worktree's content.
Run: python3 -m unittest hass.tests.test_claims -v
"""

import unittest

from hass import claims, conversation, voice
from hass.tests.test_conversation import ConversationTestCase, _ops

ADD = "add avocados from Ava's, description: creamy"
NEW = {"name": "Hass avocados", "brand": "Ava’s", "category": "fruit", "image": "assets/products/photo-product-001.webp",
       "displayBrand": "Ava’s", "producerKey": "Ava’s"}
MAKERS = {"Linn's": {"name": "Linn's"}, "Etto": {"name": "Etto Pastificio"}}
P1 = "photo-product-001"


def edit(before, after, field="description", collection="products", key="p1", ops=None):
    return {"ops": ops or [{"op": "product.edit", "args": {}}],
            "records": [{"collection": collection, "key": key, "before": {field: before}, "after": {field: after}}]}


class UnstatedTests(unittest.TestCase):
    def hits(self, before, after, owner="", **kw):
        return [term for _w, term in claims.unstated(edit(before, after, **kw), owner, MAKERS)]

    def test_new_term_not_in_owner_text_is_named_with_its_field(self):
        draft = {"ops": [{"op": "product.add", "args": {}}],
                 "records": [{"collection": "products", "key": "p9", "before": None,
                              "after": {"name": "Avocados", "description": "Organic creamy avocados", "price": 3}}]}
        self.assertEqual(claims.unstated(draft, ADD, MAKERS), [("products p9 description", "organic")])

    def test_owner_words_fold_case_accents_and_apostrophes(self):
        for owner in ("make it organic", "ORGANIC please", "Organíc", "ｏｒｇａｎｉｃ"):
            with self.subTest(owner=owner):
                self.assertEqual(self.hits("Creamy", "Organic and creamy", owner), [])
        for after in ("ORGANIC and creamy", "Orgánic and creamy", "creamy, organic."):
            with self.subTest(after=after):  # the draft's spelling cannot dodge the check either
                self.assertEqual(self.hits("Creamy", after, "creamy"), ["organic"])

    def test_counts_compare_with_the_text_before(self):
        kept = "Grown in Los Osos. Creamy."
        self.assertEqual(self.hits(kept, "Grown in Los Osos. Very creamy."), [])
        self.assertEqual(self.hits(kept, "Grown in Los Osos, grown in sun."), ["grown in"])
        self.assertEqual(self.hits("Grown in Los Osos.", "Creamy."), [])  # removing a claim is not adding one

    def test_whole_terms_only_and_hyphen_variants(self):
        # "locale" is another word, not the term "local"; plural "organics" likewise; "organically" is itself a variant term (asked)
        self.assertEqual(self.hits("", "Organically minded, a fine locale, Massa Organics"), ["organically"])
        self.assertEqual(self.hits("", "Pesticide free"), ["pesticide-free"])
        self.assertEqual(self.hits("", "pesticide-free and non\u2011GMO"), ["pesticide-free", "non-gmo"])
        self.assertEqual(self.hits("", "Pesticide-free", "it is pesticide free"), [])
        # an owner who wrote only "organically" has not said "organic"
        self.assertEqual(self.hits("", "Organic", "organically grown"), ["organic"])
        self.assertEqual(self.hits("", "Locally made in Cambria, family farm estate"),
                         ["locally", "made in", "family farm", "estate"])

    def test_producer_key_must_be_named_by_key_or_name(self):
        def maker(key, owner, makers=MAKERS):
            return claims.unstated(edit(None, key, field="producerKey"), owner, makers)
        self.assertEqual(maker("Etto", "set the producer"), [("products p1 producerKey", "maker")])
        self.assertEqual(maker("Etto", "it is from etto"), [])
        self.assertEqual(maker("Etto", "from Etto Pastificio"), [])
        self.assertEqual(maker("Linn's", "from Linn’s"), [])  # curly apostrophe in the owner's words
        self.assertEqual(maker("Linn's", "from Linns"), [("products p1 producerKey", "maker")])
        self.assertEqual(maker("Etto", "from Etto", None), [("products p1 producerKey", "maker")])  # unreadable: asks
        self.assertEqual(claims.unstated(edit("Etto", "Etto", field="producerKey"), "", MAKERS), [])  # unchanged
        self.assertEqual(claims.unstated(edit("Etto", None, field="producerKey"), "", MAKERS), [])  # cleared

    def test_maker_added_in_the_same_draft_and_other_collections(self):
        draft = {"ops": [{"op": "maker.add", "args": {}}, {"op": "product.edit", "args": {}}], "records": [
            {"collection": "makers", "key": "lo", "before": None,
             "after": {"name": "Los Osos Grove", "story": "Organic since 1990."}},
            {"collection": "products", "key": "p1", "before": {"producerKey": None}, "after": {"producerKey": "lo"}}]}
        self.assertEqual(claims.unstated(draft, "new maker Los Osos Grove", MAKERS), [("makers lo story", "organic")])

    def test_only_a_pure_revert_skips_the_check(self):
        revert = [{"op": "history.revert", "args": {"changeId": "c1"}}]
        self.assertEqual(self.hits("Creamy", "Organic and creamy", ops=revert), [])
        mixed = revert + [{"op": "product.edit", "args": {}}]
        self.assertEqual(self.hits("Creamy", "Organic and creamy", ops=mixed), ["organic"])

    def test_question_names_two_hits_then_counts(self):
        one = claims.question([("products p1 description", "organic")])
        self.assertEqual(one, 'You didn\'t say \ue000"organic"\ue001 in your message. Is that true? Send the change again with it in your own words, or without it.')
        many = claims.question([("a", "organic"), ("b", "local"), ("c", "estate"), ("d", "maker")])
        self.assertIn('You didn\'t say "organic" and "local" (and a few more) in your message', voice.plain(many))
        self.assertNotIn("estate", many)


class ClaimConversationTests(ConversationTestCase):
    """The production registry and the writer worktree's makers.json, as the live conversation runs."""

    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.conv = self.open()

    def asks(self, text, mapping):
        before = self.drafts()
        self.interp.mapping[text] = mapping
        self.assertEqual(self.say(text), "claim-question")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("You didn't say "), reply)
        self.assertEqual(self.drafts(), before)
        return reply

    def proposes(self, text, mapping):
        self.interp.mapping[text] = mapping
        self.assertEqual(self.say(text), "proposed")
        return self.replies()[0]

    def test_added_organic_description_asks_and_owner_words_propose(self):
        reply = self.asks(ADD, _ops(("product.add", {**NEW, "description": "Organic creamy avocados"})))
        self.assertRegex(reply, r'You didn\'t say "organic" in your message')
        self.assertEqual((self.drafts(), self.commits()), ([], 0))
        self.proposes("add organic avocados from Ava’s, creamy",
                      _ops(("product.add", {**NEW, "description": "Organic creamy avocados"})))

    def test_unnamed_maker_asks_and_named_maker_proposes(self):
        ops = _ops(("product.edit", {"id": P1, "producerKey": "Linn's"}))
        self.assertIn('You didn\'t say "maker" in your message', self.asks("set its producer", ops))
        self.proposes("these are from Linn’s", ops)

    def test_revision_with_a_claim_leaves_the_waiting_draft(self):
        self.proposes("desc", _ops(("product.edit", {"id": P1, "description": "Ripe and creamy."})))
        self.interp.mapping["half"] = _ops(("product.edit", {"id": "photo-product-016"}))
        self.assertEqual(self.say("half"), "needs-details")
        self.replies()
        waiting = self.drafts()
        for row in waiting:
            with self.subTest(state=row["state"]):
                fix = {**_ops(("product.edit", {"id": P1, "description": "Local and creamy."})),
                       "revises": row["code"]}
                self.asks(f"fix {row['code']}", fix)
        self.assertEqual([(r["code"], r["state"], r["summary"]) for r in self.drafts()],
                         [(r["code"], r["state"], r["summary"]) for r in waiting])

    def approve(self, text, mapping):
        self.proposes(text, mapping)
        self.say("yes")
        self.replies()
        self.assertEqual(self.drafts()[-1]["state"], "applied")
        return self.drafts()[-1]

    def test_undo_restoring_organic_text_is_proposed(self):
        self.approve("description: organic and creamy", _ops(("product.edit", {"id": P1, "description": "Organic, creamy."})))
        plain = self.approve("description: creamy", _ops(("product.edit", {"id": P1, "description": "Creamy."})))
        self.assertEqual(self.say(f"undo {plain['code']}"), "proposed")  # AV0007-02: command undo, not interpreter
        reply = self.replies()[0]
        self.assertIn("Organic, creamy.", reply)


if __name__ == "__main__":
    unittest.main()
