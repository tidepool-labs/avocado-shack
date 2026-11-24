"""NPP-G: owner edit words (S10), the version-tagged reply lines (S9/S11/S13) and the legacy F4F5 price edits.

Each test names the contract it protects and the believable bug that breaks it (CI-ARTICLE-1)."""
from datetime import timedelta
import json
import types
import unittest

from hass import conversation, npp
from hass.npp import edits, reply
from hass.npp.job import Card, Plan, Work
from hass.skills import intake_simple
from hass.tests import test_npp_job as job_tests
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0
from hass.tests.test_photo_draft import PNG
from hass.tests.test_set_photo import PhotoRepo

PINNED = npp.assets()
REPLIES = PINNED[2]
GRAMMAR = edits.Grammar(PINNED[1])
PARENT = {"name": "Supergrip Glue", "category": "general", "sellingPrice": "2.00", "image_variant": "raw",
          "image_sha256": "a" * 64, reply.SEEN: 1}


def listing_slots(price="2.00", **intake):
    return {"name": "SUPERGRIP GLUE", "maker": "Producer not identified", "shelf": "general", "description": "A glue.",
            "photo": "b" * 64, "intake": {"simple": True, "price": price, **intake}}


class LegacyPriceEditTests(unittest.TestCase):
    """F4F5 on the existing simple-intake path (chaos edit-price-plain, edit-contradiction, intake-photo-then-two-messages-fast)."""

    def test_plain_words_price_edit_sets_the_selling_price(self):
        # Contract F4: "make it $4", "actually make it 4 bucks", "wait $4.50", "no $3" change the price on the same draft.
        # Bug: edit() only took the bare "$2 each" form and answered "Which part of the listing should change".
        for text, want in (("make it $4", "4.00"), ("actually make it 4 bucks", "4.00"), ("wait $4.50", "4.50"),
                           ("no $3", "3.00"), ("ok make it $4", "4.00"), ("make it four dollars", "4.00"),
                           ("change the price to $3.50 per lb", "3.50")):
            with self.subTest(text=text):
                slots, public, question = intake_simple.edit(listing_slots(), text)
                self.assertEqual((slots["intake"]["price"], public, question), (want, "", None))
        slots, _, _ = intake_simple.edit(listing_slots(), "change the price to $3.50 per lb")
        self.assertEqual(slots["intake"]["sold_by"], "pound")
        # F5 "from Etto" (after Hass's own price question) is the source line, not a supplier question.
        slots, _, question = intake_simple.edit(listing_slots(), "from Etto", "price")
        self.assertEqual((slots.get("supplier"), question), ("Etto", None))

    def test_amount_already_read_upstream_leaves_no_listing_words(self):
        # Contract F4: dispatch.intake_text moves "$4" into the private slots and passes on "make it"; that remainder is
        # the edit, not words to place. Bug: "make it" fell through to the clarifying question and the $4 was never drafted.
        for leftover in ("make it", "ok make it", "no", "wait", "actually change it to"):
            with self.subTest(leftover=leftover):
                slots, public, question = intake_simple.edit(listing_slots(price="4.00"), leftover)
                self.assertEqual((slots["intake"]["price"], public, question), ("4.00", "", None))

    def test_unsure_or_cost_amounts_are_not_taken_as_the_price(self):
        # Contract 1.9: an unsure amount is asked, never guessed, and a cost word stays private finance.
        # Bug: a looser price pattern would publish 4.00 from "4 or 5 bucks" or turn "paid $3" into the selling price.
        slots, _, question = intake_simple.edit(listing_slots(), "make it 4 or 5 bucks")
        self.assertEqual(slots["intake"]["price"], "2.00")
        self.assertIsNotNone(question)
        slots, _, _ = intake_simple.edit(listing_slots(), "paid $3")
        self.assertEqual((slots["intake"]["price"], slots["intake"].get("cost")), ("2.00", "3.00"))

    def test_same_name_product_is_said_plainly_with_the_price(self):
        # Contract F5: the answer to "What price should it sell for?" is shown in the listing; a same-name product on the
        # site is named, not reported as "That's already how it is". Bug: the editor's twin refusal mapped to already-so.
        content = types.SimpleNamespace(makers={}, products=[{"id": "photo-product-016", "name": "Oranges",
                                                             "brand": "Producer not identified", "status": "active"}])
        slots = {**listing_slots(price="3.50", sold_by="pound"), "name": "Oranges", "shelf": "fruit"}
        with self.assertRaises(ValueError) as said:
            intake_simple.plan(slots, content)
        self.assertIn("Price: $3.50 per lb", str(said.exception))
        self.assertRegex(str(said.exception), r"\n\W*Oranges\W* is already on the website")
        self.assertNotIn("already how it is", str(said.exception))
        slots["intake"].pop("price")  # before the price the twin is not raised: the price question is asked first
        self.assertEqual(intake_simple.plan(slots, content)[0]["op"], "product.add")


class EditGrammarTests(unittest.TestCase):
    def test_pinned_grammar_rechecks_its_examples(self):
        # Contract 2.1/4a: S10 forms come from the pinned asset and still read their own examples and not their negatives.
        # Bug: a grammar edit that stops matching "make it $4" (or starts matching "make it shorter") ships unnoticed.
        files = dict(PINNED[1])
        doc = json.loads(files[edits.GRAMMAR])
        doc["forms"][0]["negatives"].append("make it $4")
        files[edits.GRAMMAR] = json.dumps(doc).encode()
        with self.assertRaisesRegex(ValueError, "reads a negative"):
            edits.Grammar(files)

    def test_price_comes_only_from_code_parsed_finance(self):
        # Contract 1.9: sellingPrice is written only from the code-parsed finance slots, never from edit text or a model.
        # Bug: reading "$9" from the public remainder or a model patch would publish a misread or private number.
        self.assertEqual(edits.read(GRAMMAR, "make it", {"price": "4.00", "sold_by": "pound"}).patch,
                         (("sellingPrice", "4.00"), ("priceUnit", "lb")))
        self.assertEqual(edits.read(GRAMMAR, "make it $9", {}).ask, "ask_price")
        model = lambda *a: {"action": "patch", "patches": [{"field": "sellingPrice", "value": "9.00"}], "ask_id": None}
        self.assertEqual(edits.read(GRAMMAR, "change the cost thing", {}, model).ask, "ask_price")

    def test_named_values_are_his_words_and_never_pasted(self):
        # Contract F1/S10: "made by X, Town", "from X" and the last-sentence source edit set typed fields; a model may only
        # point at words he typed. Bug: the chatter of edit-source-miners pasted into public text, or a model-invented maker.
        self.assertEqual(edits.read(GRAMMAR, "made by Miners, Paso Robles", {}).patch,
                         (("maker", "Miners"), ("makerTown", "Paso Robles")))
        self.assertEqual(edits.read(GRAMMAR, "from etto", {}).patch, (("supplier", "Etto"),))
        chatter = ('Nice. Just change one thing "ask us about the source in the store". You should get that info here. '
                   'This is from "miners".')
        self.assertEqual(edits.read(GRAMMAR, chatter, {}).patch, (("supplier", "Miners"),))
        invented = lambda *a: {"action": "patch", "patches": [{"field": "maker", "value": "Acme Farms"}], "ask_id": None}
        self.assertEqual(edits.read(GRAMMAR, "use the other maker please", {}, invented).ask, "ask_edit_unclear")
        pointed = lambda *a: {"action": "patch", "patches": [{"field": "maker", "value": "Rosa"}], "ask_id": None}
        self.assertEqual(edits.read(GRAMMAR, "swap the maker to Rosa", {}, pointed).patch, (("maker", "Rosa"),))

    def test_mapping_is_schema_checked_and_digits_stay_local(self):
        # Contract 2.3/PLAN-v2: the model answer must satisfy edit.schema.json, and a text with a digit is never sent.
        # Bug: an extra key or a bad ask id accepted as a patch, or his "12 jars" sent to the cloud.
        calls = []
        bad = lambda *a: calls.append(a) or {"action": "patch", "patches": [], "ask_id": None, "extra": 1}
        self.assertEqual(edits.read(GRAMMAR, "make the label nicer", {}, bad).ask, "ask_edit_unclear")
        self.assertEqual(edits.read(GRAMMAR, "make it 12 jars nicer", {}, bad).ask, "ask_edit_unclear")
        self.assertEqual(len(calls), 1)
        sent = []
        transport = lambda url, body, headers, timeout: sent.append(json.loads(body)) or (500, "")
        self.assertIsNone(edits.codex_mapper(transport)("prompt", {}, "make it warmer", ["name"]))
        self.assertIn("make it warmer", sent[0]["messages"][1]["content"])

    def test_picture_request_asks_for_a_new_photo(self):
        # Contract 1.3 "no late styled picture": a picture request never starts a second image edit; it asks for a photo.
        # Bug: "try the picture again" re-running the polish or patching the frozen picture.
        got = edits.read(GRAMMAR, "try the picture again", {})
        self.assertEqual(reply.question(REPLIES, got), ("picture_request", "Send me another photo and I'll use that one."))

    def test_apply_builds_a_new_listing_and_keeps_the_picture(self):
        # Contract 1.3 immutable versions: v(n+1) = v(n) + patch; the parent and the frozen picture fields are unchanged.
        # Bug: patching the parent dict in place (an approved/delivered version changing under the owner).
        parent = json.loads(json.dumps(PARENT))
        new, changed = edits.apply(parent, [edits.Edit(patch=(("sellingPrice", "4.00"),)),
                                            edits.Edit(patch=(("sellingPrice", "4.50"), ("maker", "Miners")))])
        self.assertEqual(parent, PARENT)
        self.assertEqual((new["sellingPrice"], new["maker"], new["image_sha256"]), ("4.50", "Miners", "a" * 64))
        self.assertEqual(changed, {"sellingPrice": "4.50", "maker": "Miners"})


class ReplyLineTests(unittest.TestCase):
    def test_ready_line_has_its_own_version_tag_and_one_bounded_bracket(self):
        # Contract S9: every prompt names its version ("yes 4ed1-2") and at most one bracket <= 60 chars, parts dropped in
        # the asset's drop order. Bug: an untagged prompt (approval ambiguity) or an overlong bracket.
        self.assertEqual(reply.ready_line(REPLIES, "4ed1", 2), "Post this? Reply yes 4ed1-2, or tell me what to change.")
        line = reply.ready_line(REPLIES, "4ed1", 1, {"picture_own_photo": {}, "basic_wording": {}, "maker_left_off": {}})
        bracket = line[line.index("(") + 1:-1]
        self.assertLessEqual(len(bracket) + 2, REPLIES["caps"]["bracket_max_chars"])
        self.assertTrue(bracket.startswith("picture: your own photo"))
        self.assertNotIn("basic wording", bracket)
        with self.assertRaises(ValueError):
            reply.compose(REPLIES, {"free text": {}})

    def test_guards_are_one_line_and_confirmation_names_the_link(self):
        # Contract cases 34-35 and S13: guard replies are one line that offers no card; Posted names the item link.
        # Bug: a two-sentence guard read as a new prompt, or a confirmation link to the wrong shelf.
        for key in ("not_ready", "which_card", "replaced", "render_failed", "live_check_failed"):
            with self.subTest(key=key):
                self.assertTrue(reply.one_line(reply.guard(REPLIES, key)))
                self.assertNotIn("yes ", reply.guard(REPLIES, key))
        self.assertEqual(reply.posted(REPLIES, "photo-product-139"),
                         "Posted: https://theavocadoman.com/?item=photo-product-139#market (say undo to take it down)")
        with self.assertRaises(ValueError):
            reply.posted(REPLIES, "../x")


class StagesTests(unittest.TestCase):
    def stages(self, **kw):
        return reply.Stages(PINNED, start=lambda work: Plan(listing={"name": "x"}), render=lambda work, listing: None, **kw)

    def work(self, texts, intake, parent=PARENT):
        return Work("4ed1", {"texts": texts, "slots": {"intake": intake}, "attachments": []},
                    {"listing_json": json.dumps(parent)} if parent else None, None)

    def test_folded_edits_last_value_wins_and_only_new_texts_are_read(self):
        # Contract 1.3 coalescing / chaos edit-contradiction: edits folded into one segment build one version in which
        # the last value wins; texts the parent consumed are not re-read. Bug: re-reading v1's caption as an edit.
        plan = self.stages().plan(self.work(["sell these", "", "", ""], {"price": "4.50"}))
        self.assertEqual((plan.listing["sellingPrice"], plan.listing[reply.SEEN], plan.patch), ("4.50", 4, {"sellingPrice": "4.50"}))
        first = self.stages().plan(self.work(["sell these"], {"price": "2.00"}, parent=None))
        self.assertEqual(first.listing[reply.SEEN], 1)

    def test_unread_or_no_change_edit_is_one_question(self):
        # Contract 1.4 "Edit not understood | one question, card unchanged". Bug: a new card for a no-op edit.
        plan = self.stages().plan(self.work(["sell these", "make the jar happier"], {"price": "2.00"}))
        self.assertEqual(plan.questions, (("ask_edit_unclear", REPLIES["questions"]["ask_edit_unclear"]),))
        self.assertIsNone(plan.listing)

    def test_questions_to_hass_are_not_taken_as_edits(self):
        # Contract 1.3: a message unrelated to the job gets its normal answer. Bug: "what time do we close sunday" folded
        # into the listing (edit-unrelated-question-mid-draft).
        stages = self.stages()
        self.assertFalse(stages.takes_turn("what time do we close sunday", "card_out"))
        self.assertFalse(stages.takes_turn("is it sold out?", "asking"))
        self.assertTrue(stages.takes_turn("make it $4", "card_out"))
        self.assertTrue(stages.takes_turn("from Etto", "card_out"))
        self.assertTrue(stages.takes_turn("$3.50 a pound", "asking"))
        self.assertFalse(stages.takes_turn("make it $4", "published"))

    def test_build_stages_fails_closed_without_the_stage_modules(self):
        # Contract 2.1: a missing component cannot trigger a partial stage chain.
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch
        stub = SimpleNamespace(candidate=lambda _: None, render_candidate=lambda _: None, persist_candidate=lambda _: None)
        conv = SimpleNamespace(editor=stub, previewer=object(), labels=None)
        self.assertIsNotNone(npp.stages_for(conv, PINNED))
        with patch.dict(sys.modules, {'hass.npp.stages': None}):
            self.assertIsNone(npp.stages_for(conv, PINNED))


class EditLoopJobTests(unittest.TestCase):
    """The real job runner (NPP-B) with this edit segment: a delivered card, a plain edit, a new tagged card, one yes."""

    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        root = self.repo.state.parent / "pictures"
        root.mkdir(mode=0o700)
        self.transport, self.scheduler, self.now, self.serial = job_tests.Transport(), job_tests.Scheduler(), T0, 0
        self.editor = conversation.Editor(self.repo.state)
        cfg = self.repo.state / "config.json"
        settings = {**SETTINGS, "mediaRoot": str(root), "npp": True, "approvalTtlSeconds": 3600}
        cfg.write_text(json.dumps({**json.loads(cfg.read_text()), "settings": settings}))
        self.stages = reply.Stages(PINNED, start=self.start_stage, render=self.render_stage)
        self.conv = conversation.Conversation(self.repo.state, self.editor, conversation.FixtureInterpreter({}), lambda: self.now,
                                              photos=self, npp_stages=self.stages, npp_executor=self.scheduler,
                                              npp_receipt_for=self.transport.receipt_for)
        self.addCleanup(self.conv.db.close)

    def fetch(self, pid, count):
        return [PNG][:count]

    def start_stage(self, work):
        price = work.request["slots"]["intake"].get("price")
        if price is None:
            return Plan(questions=(("ask_price", REPLIES["questions"]["ask_price"]),), identified=True)
        return Plan(listing={"name": "Fixture glue", "sellingPrice": price})

    def render_stage(self, work, listing):
        args = {"name": listing["name"], "brand": "Producer not identified", "category": "general",
                "description": "A strong glue.", "photo": work.request["attachments"][0], "imageAlt": "A glue bottle",
                "sellingPrice": listing["sellingPrice"]}
        if listing.get("supplier"):
            args["supplier"] = listing["supplier"]
        out = self.editor.prepare([{"op": "product.add", "args": args}])
        path, digest = next(iter(out["draft"]["assets"].items()))
        return Card(out["draft"], PNG, "raw", path, digest.removeprefix("sha256:"), "picture: your own photo")

    def say(self, text, photos=0, reply_to=None):
        self.serial += 1
        self.now += timedelta(seconds=1)
        msg = conversation.Inbound(f"g-{self.serial}", CHAT, OWNER, text, received_at=self.now.isoformat(),
                                   attachments=photos, reply_to=reply_to)
        return self.conv.handle(msg, forwarded_at=self.now)

    def work(self):
        for _ in range(8):
            self.conv.flush(self.transport)
            if self.scheduler.steps:
                self.scheduler.run()

    def confirm(self, n):
        v = self.conv.npp.version(self.job()["job_id"], n)
        self.transport.receipts[v["outbox_id"]] = dict(state="confirmed", png_sha256=v["card_png_sha"],
                                                        provider_guid=f"m-{n}", confirmed_at=self.now.isoformat())
        self.conv.flush(self.transport)

    def job(self):
        return self.conv.db.execute("SELECT * FROM npp_jobs ORDER BY rowid DESC LIMIT 1").fetchone()

    def test_edit_gives_a_new_tagged_card_and_the_yes_publishes_that_version(self):
        # Contract S9/S10/S11: an edit builds v2 from v1 + patch, its prompt carries a PNG and "yes <code>-2", and the yes
        # for v2 publishes v2's price and supplier. Bug: the edit applied in place to v1, an untagged prompt, or v1 published.
        self.say("sell $2", photos=1)
        self.work()
        self.confirm(1)
        self.assertEqual(self.say("from Etto"), "npp-working")
        self.assertEqual(self.say("sell $4"), "npp-working")  # folded into the same edit segment: one card answers both
        self.work()
        code = self.job()["job_id"]
        cards = list(self.transport.cards.values())
        self.assertEqual(len(cards), 2)
        self.assertTrue(cards[-1][0].startswith(f"Post this? Reply yes {code}-2,"))
        self.assertEqual(cards[-1][1], PNG)
        v1 = json.loads(self.conv.npp.version(code, 1)["listing_json"])
        v2 = json.loads(self.conv.npp.version(code, 2)["listing_json"])
        self.assertEqual((v1["sellingPrice"], v2["sellingPrice"], v2["supplier"]), ("2.00", "4.00", "Etto"))
        self.confirm(2)
        self.assertEqual(self.say(f"yes {code}-2"), "approved")
        products = (self.repo.wt / "hass/content/products.json").read_text()
        self.assertIn('"sellingPrice": "4.00"', products)
        self.assertIn('"supplier": "Etto"', products)

    def test_plain_words_price_edit_gives_a_revised_card(self):
        # Contract F4 on the NPP path: "make it $4" / "wait $4.50" while a card is out revise the price on the same job.
        # Bug: the turn was parsed as a photo caption, the amount stayed in the words and no finance slot was made, so the
        # edit asked "I didn't catch that" (or changed nothing) instead of drawing a revised card.
        self.say("sell $2", photos=1)
        self.work()
        self.confirm(1)
        self.assertEqual(self.say("make it $4"), "npp-working")
        self.work()
        self.confirm(2)
        self.assertEqual(self.say("wait $4.50"), "npp-working")
        self.work()
        code = self.job()["job_id"]
        prices = [json.loads(self.conv.npp.version(code, n)["listing_json"])["sellingPrice"] for n in (1, 2, 3)]
        self.assertEqual(prices, ["2.00", "4.00", "4.50"])
        self.assertEqual(len(self.transport.cards), 3)
        self.assertTrue(list(self.transport.cards.values())[-1][0].startswith(f"Post this? Reply yes {code}-3,"))

    def test_a_yes_replying_to_the_current_card_resolves_that_exact_card(self):
        # Contract S11: a reply to the card names its delivered receipt; a reply to an older card is "replaced", an unknown
        # reference is not a card. Bug: any reply reference made the yes "not ready", so replying to the card never published.
        self.say("sell $2", photos=1)
        self.work()
        self.confirm(1)
        self.say("sell $4")
        self.work()
        self.confirm(2)
        code = self.job()["job_id"]
        self.assertEqual(self.say(f"yes {code}", reply_to="m-1"), "no-target")  # the replaced card
        self.assertEqual(self.say(f"yes {code}", reply_to="not-a-card"), "no-target")
        self.assertEqual(self.say(f"yes {code}-9", reply_to="m-2"), "no-target")  # the code names no card of this reply
        self.conv.flush(self.transport)
        self.assertEqual(self.transport.texts[-3:], [REPLIES["guards"][k] for k in ("replaced", "not_ready", "which_card")])
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 0)
        self.assertEqual(self.say(f"yes {code}", reply_to="m-2"), "approved")
        self.assertIn('"sellingPrice": "4.00"', (self.repo.wt / "hass/content/products.json").read_text())

    def test_coded_yes_without_reply_ref_after_two_cards_reasks(self):
        # A bare "yes <code>" after two delivered cards cannot name one and must fail closed: the which-card line,
        # no approval row, nothing published. Bug if it approved the newest (or oldest) card by guess.

        self.say("sell $2", photos=1)
        self.work()
        self.confirm(1)
        self.say("sell $4")
        self.work()
        self.confirm(2)
        before = (self.repo.wt / "hass/content/products.json").read_text()
        code = self.job()["job_id"]
        self.assertEqual(self.say(f"yes {code}"), "no-target")
        self.conv.flush(self.transport)
        self.assertEqual(self.transport.texts[-1], REPLIES["guards"]["which_card"])
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 0)
        self.assertEqual((self.repo.wt / "hass/content/products.json").read_text(), before)  # nothing published

    def test_posted_confirmation_names_the_item_link_only_for_a_published_listing(self):
        # Contract S13: the confirmation the live release engine sends is `Posted: <item link>` for a published listing job,
        # and nothing for an ordinary change. Bug: reply.posted was never called, so the legacy line went out instead.
        self.say("sell $2", photos=1)
        self.work()
        self.confirm(1)
        change = self.conv.npp.version(self.job()["job_id"], 1)["change_id"]
        self.assertIsNone(self.conv.npp_posted(change))  # not published yet
        self.assertEqual(self.say(f"yes {self.job()['job_id']}"), "approved")
        key = [r["key"] for r in self.editor.show(change)["change"]["records"] if r["collection"] == "products"][0]
        self.assertEqual(self.conv.npp_posted(change), f"Posted: https://theavocadoman.com/?item={key}#market (say undo to take it down)")
        self.assertIsNone(self.conv.npp_posted("0" * 16))

    def test_picture_request_is_one_line_and_no_new_card(self):
        # Contract S10 picture requests: one line asking for a new photo; no image edit and no card for that message.
        self.say("sell $2", photos=1)
        self.work()
        self.confirm(1)
        self.say("use my photo")
        self.work()
        self.assertEqual(self.transport.texts[-1], "Send me another photo and I'll use that one.")
        self.assertEqual(len(self.transport.cards), 1)


if __name__ == "__main__":
    unittest.main()
