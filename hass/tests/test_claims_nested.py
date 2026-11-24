"""RF0220-11 tests: a claim term added in the store's notice.text or homeImage.imageAlt asks, never drafts.

Frozen rule: only those two leaves of the store record are scanned (labelled "notice.text", "homeImage.imageAlt"), with the
existing terms, fold, whole-word, occurrence-increase and owner-affirmation rules. Other dictionaries stay skipped.
Run: python3 -m unittest hass.tests.test_claims_nested -v
"""

import unittest

from hass import claims, conversation
from hass.tests.test_claims import MAKERS
from hass.tests.test_conversation import ConversationTestCase, _ops

IMG = "assets/products/photo-0123456789abcdef.jpg"
SET_NOTICE = [{"op": "store.set_notice", "args": {}}]
REVERT = [{"op": "history.revert", "args": {"changeId": "c1"}}]


def store(before, after, collection="store", ops=None):
    return {"ops": ops or SET_NOTICE, "records": [{"collection": collection, "key": "store", "before": before, "after": after}]}


def notice(text, until="2026-11-26"):
    return {"notice": {"text": text, "until": until}}


def hero(alt, image=IMG):
    return {"homeImage": {"image": image, "imageAlt": alt}}


class NestedScanTests(unittest.TestCase):
    def hits(self, before, after, owner="", **kw):
        return claims.unstated(store(before, after, **kw), owner, MAKERS)

    def test_nested_notice_and_hero_alt_additions_ask(self):
        self.assertEqual(self.hits({}, notice("Organic honey Saturday"), "put honey on the home page"),
                         [("store store notice.text", "organic")])
        self.assertEqual(self.hits({}, hero("Local organic fruit"), "use this photo"),
                         [("store store homeImage.imageAlt", "organic"), ("store store homeImage.imageAlt", "local")])
        # both slots in one record: top-level fields stay sorted (homeImage before notice), TERMS order inside a slot
        both = {**notice("Vegan bakes"), **hero("Organic fruit")}
        self.assertEqual(self.hits({}, both, "update the home page"),
                         [("store store homeImage.imageAlt", "organic"), ("store store notice.text", "vegan")])
        # a top-level product claim keeps its label
        draft = store({}, {"description": "Organic figs"}, collection="products")
        self.assertEqual(claims.unstated(draft, "new text", MAKERS), [("products store description", "organic")])

    def test_nested_claim_counts_and_nontext_metadata(self):
        was = notice("Organic honey Saturday")
        self.assertEqual(self.hits(was, notice("Organic honey Sunday")), [])  # same count
        self.assertEqual(self.hits(was, notice("Organic honey and organic figs"), "x"), [("store store notice.text", "organic")])
        self.assertEqual(self.hits(was, notice("Honey Saturday")), [])  # removed
        self.assertEqual(self.hits(was, notice("Organic honey Saturday", until="2026-12-01")), [])  # date only
        self.assertEqual(self.hits(hero("Local fruit"), hero("Local fruit", image="assets/products/other.jpg")), [])  # image only
        self.assertEqual(self.hits({"notice": "x"}, notice("Organic honey")), [("store store notice.text", "organic")])  # old not a dict
        self.assertEqual(self.hits({"notice": {"text": 7}}, notice("Organic honey")), [("store store notice.text", "organic")])
        self.assertEqual(self.hits({"notice": {"until": "x"}}, notice("Organic honey")), [("store store notice.text", "organic")])
        self.assertEqual(self.hits({}, {"notice": {"text": ["Organic"], "until": "x"}}), [])  # new leaf not a string
        self.assertEqual(self.hits({}, {"notice": {"until": "x"}}), [])  # new leaf absent
        self.assertEqual(self.hits({}, {"notice": None}), [])  # new container not a dict
        # only the two configured leaves: other keys of those dicts and other dictionaries are skipped
        self.assertEqual(self.hits({}, {"notice": {"text": "Hi", "until": "Organic"}, "other": {"text": "Organic"}}), [])
        self.assertEqual(self.hits({}, {"homeImage": {"image": "organic-photo.jpg", "imageAlt": "A tree"}}), [])
        # the same shape in another collection is not a store slot
        self.assertEqual(self.hits({}, notice("Organic honey"), collection="products"), [])

    def test_nested_owner_affirmation_negation_and_folding(self):
        add = notice("Organic honey Saturday")
        self.assertEqual(self.hits({}, add, "notice: Organic honey Saturday"), [])
        self.assertEqual(self.hits({}, hero("Local fruit"), "photo of local fruit"), [])
        self.assertEqual(self.hits({}, add, "it is not organic"), [("store store notice.text", "organic")])
        self.assertEqual(self.hits({}, hero("Local fruit"), "this isnt local"), [("store store homeImage.imageAlt", "local")])
        self.assertEqual(self.hits({}, add, "not only organic but local"), [("store store notice.text", "organic")])
        self.assertEqual(self.hits({}, notice("ORGÁNIC honey"), "x"), [("store store notice.text", "organic")])  # folded
        self.assertEqual(self.hits({}, notice("ORGÁNIC honey"), "organic"), [])
        self.assertEqual(self.hits({}, notice("Pesticide free plums"), "x"), [("store store notice.text", "pesticide-free")])
        self.assertEqual(self.hits({}, notice("Pesticide\u2011free plums"), "pesticide free"), [])
        self.assertEqual(self.hits({}, notice("Organics grown"), "x"), [])  # whole words only
        self.assertEqual(self.hits({}, notice("Organically grown"), "x"), [("store store notice.text", "organically")])  # AV1124A-08 variant term, nested too
        self.assertEqual(self.hits({}, notice("Organically grown"), "we are organic"), [])  # owner's "organic" backs it
        twice = notice("Organic here, organic there")
        self.assertEqual(self.hits(notice("Organic here"), twice, "x"), [("store store notice.text", "organic")])
        self.assertEqual(self.hits(notice("Organic here"), twice, "we are organic"), [])

    def test_nested_revert_and_hit_order(self):
        add = notice("Organic honey Saturday")
        self.assertEqual(self.hits({}, add, ops=REVERT), [])  # a pure revert restores earlier text
        self.assertEqual(self.hits({}, add, ops=REVERT + SET_NOTICE), [("store store notice.text", "organic")])
        many = {**notice("Organic, vegan and kosher"), **hero("Local organic fruit")}
        hits = self.hits({}, many, "x")
        self.assertEqual(hits, [("store store homeImage.imageAlt", "organic"), ("store store homeImage.imageAlt", "local"),
                                ("store store notice.text", "organic"), ("store store notice.text", "vegan"),
                                ("store store notice.text", "kosher")])
        self.assertEqual(claims.question(hits[:1]), 'You didn\'t say \ue000"organic"\ue001 in your message. Is that true? Send the change again with it in your own words, or without it.')
        self.assertEqual(claims.question(hits), 'You didn\'t say \ue000"organic"\ue001 and \ue000"local"\ue001 (and a few more) in your message. Are they true? Send the change again with them in your own words, or without them.')
        self.assertEqual(claims.question(self.hits({}, add, "x")), 'You didn\'t say \ue000"organic"\ue001 in your message. Is that true? Send the change again with it in your own words, or without it.')


class NestedConversationTests(ConversationTestCase):
    """The production registry and the writer worktree's store record, as the live conversation runs."""

    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.conv = self.open()
        self.base = self.count()

    def test_notice_conversation_asks_without_replacing_waiting_draft(self):
        self.interp.mapping["hours"] = _ops(("store.set_hours", {"hours": ["Mon–Sat 9–6"]}))
        self.assertEqual(self.say("hours"), "proposed")
        self.replies()
        [waiting] = self.drafts()
        notice_args = {"text": "Organic honey Saturday", "until": "2026-11-26"}
        text = "put honey on the home page"
        self.interp.mapping[text] = _ops(("store.set_notice", notice_args))
        self.assertEqual(self.say(text), "claim-question")
        [reply] = self.replies()
        self.assertEqual(reply, 'You didn\'t say "organic" in your message. Is that true? Send the change again with it in your own words, or without it.')
        self.assertEqual((self.drafts(), self.commits()), ([waiting], 0))  # no new row, same waiting proposal, no commit
        said = "notice until the 26th: Organic honey Saturday"
        self.interp.mapping[said] = _ops(("store.set_notice", notice_args))
        self.assertEqual(self.say(said), "proposed")  # owner-stated: the existing proposal path, not applied
        self.assertEqual(self.commits(), 0)


if __name__ == "__main__":
    unittest.main()
