"""AV1937-10 (F07): `post maker <key>` replies social_draft.build_maker's caption draft in chat.
Read-only: nothing is posted, scheduled, stored or drafted; works while paused. Synthetic fixtures only.
Run: python3 -B -m unittest hass.tests.test_post_maker_command -v
"""

import json
import re
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import conversation, editor, social_draft, voice
from hass.content_model import load_content
from hass.tests.test_commands_doc import DOC, rows, verb
from hass.tests.test_conversation import GROUP, SETTINGS, STRANGER, T0, ConversationTestCase
from hass.tests.test_editor import git
from hass.tests.test_status_pause import StoreMixin

PREFIX = "Draft post (not posted; copy it yourself):\n"
USAGE = "Send post maker and a maker key; find <words> gives keys."
UNAVAILABLE = "Catalog unavailable right now; nothing changed."
STORY = "Three generations of growers."


def maker(**changes):
    return {"name": "Fixture Farm", "place": "Pismo Beach, California", "story": STORY, **changes}


def product(pid, key, status="active"):
    hold = {"hold": {"reason": "fixture", "source": "https://sierranevadacheese.com/", "evidence": "fixture", "record": "storefront-mockup/held-products.json"}}
    return {**(hold if status == "held" else {}), "name": "Fixture " + pid, "brand": "Fixture", "category": "pantry", "id": pid, "image": "assets/products/photo-product-002.webp",
            "description": "A fixture product.", "producerKey": key, "displayBrand": "Fixture", "status": status}


EXTRA = {"fixture-farm": maker(), "Dot Farm.": maker(name="Dot Farm"), "Bang Farm!": maker(name="Bang Farm"),
         "Two  Spaces": maker(name="Two Spaces"), "Question Farm?": maker(name="Question Farm"), "Hidden Farm": maker(hidden=True),
         "Empty Farm": maker(name="Empty Farm"), "Held Farm": maker(name="Held Farm")}
BAD = {"No Story": maker(story=" "), "Tag Farm": maker(story="Find us at #tagfarm"), "Long Farm": maker(story="x" * 2200)}  # added by the one test that needs them

PRODUCTS = [product("fx-1", "fixture-farm"), product("fx-2", "fixture-farm"), product("fx-3", "fixture-farm", "held"),
            product("fx-4", "Dot Farm."), product("fx-5", "Bang Farm!"), product("fx-6", "Two  Spaces"),
            product("fx-7", "Question Farm?"), product("fx-8", "Hidden Farm", "held"), product("fx-9", "Held Farm", "held")]
BAD_PRODUCTS = [product("fx-10", "No Story"), product("fx-11", "Tag Farm"), product("fx-12", "Long Farm")]


class ParseTests(unittest.TestCase):
    def test_key_is_the_whole_rest_in_its_own_case_with_final_punctuation(self):
        for text, key in (("post maker fixture-farm", "fixture-farm"), ("POST Maker Linn's", "Linn's"), ("  Post  MAKER   Cal  Poly  ", "Cal  Poly"),
                          ("post maker Dot Farm.", "Dot Farm."), ("post maker Bang Farm!", "Bang Farm!"), ("post maker Etto?", "Etto?"),
                          ("post maker Etto and more", "Etto and more"), ("post maker a b c d e f g h", "a b c d e f g h")):
            with self.subTest(text=text):
                self.assertEqual(conversation.parse_command(text), ("post", "maker " + key))
                self.assertEqual(conversation.read_command(text), ("post", "maker " + key))

    def test_no_key_and_line_breaks_are_the_usage_form(self):
        for text in ("post maker", "Post Maker   ", "post maker\n", "post maker Cal\nPoly", "post maker\nEtto", "post maker Cal\x07Poly",
                     "post maker Cal\tPoly", "post maker Cal\u2028Poly"):
            with self.subTest(text=text):
                self.assertEqual(conversation.parse_command(text), ("post", "maker"))

    def test_lookalikes_are_not_this_branch(self):
        for text in ("postmaker Etto", "post makers Etto", "post maker's cheese", "please post maker Etto", "post  makerEtto"):
            with self.subTest(text=text):
                self.assertNotEqual((conversation.parse_command(text) or ("", ""))[1][:6], "maker ", text)
        self.assertIsNone(verb("postmaker Etto"))
        self.assertIsNone(verb("please post maker Etto"))
        self.assertEqual(conversation.parse_command("POST HIKE Hike-A!"), ("post", "HIKE Hike-A"))
        self.assertEqual(conversation.parse_command("post photo-product-001"), ("post", "photo-product-001"))


class PostMakerTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        content = self.repo.wt / "hass" / "content"
        self.makers, self.products = content / "makers.json", content / "products.json"
        doc = json.loads(self.makers.read_text("utf-8"))
        doc["makers"].update(EXTRA)
        self.makers.write_text(json.dumps(doc), "utf-8")
        doc = json.loads(self.products.read_text("utf-8"))
        doc["products"] += PRODUCTS
        self.products.write_text(json.dumps(doc), "utf-8")
        self.content = content
        git(self.repo.wt, "commit", "-qam", "fixture makers")  # a clean worktree, so a waiting proposal can exist beside the posts
        self.base = self.count()

    def want(self, key):
        return social_draft.build_maker(load_content(self.content), key)

    def post(self, text, **kw):
        self.assertEqual(self.say(text, **kw), "post")
        [row] = self.conv.db.execute("SELECT text, attachments FROM outbox ORDER BY id DESC LIMIT 1").fetchall()
        self.assertEqual(len(self.replies()), 1)
        return row["text"], json.loads(row["attachments"] or "[]")

    def untouched(self):
        return (self.drafts(), self.tables(), self.commits(), self.approvals(), self.editor.applies)

    def test_post_maker_caption_equals_builder(self):
        want = self.want("fixture-farm")
        self.assertEqual(want, {"draft": True, "caption": f"Meet the maker: Fixture Farm\nBased in Pismo Beach, California.\n{STORY}\n"
                                                          "2 active products on our site.\n\n#AvocadoShack #MeetTheMaker"})
        before = self.untouched()
        with mock.patch("socket.socket", side_effect=AssertionError("network")), mock.patch("os.system", side_effect=AssertionError("shell")):
            self.assertEqual(self.post("post maker fixture-farm"), (PREFIX + want["caption"], []))
        self.assertEqual(self.untouched(), before)
        long_story = self.want("Etto")
        self.assertTrue(long_story["draft"])
        self.assertEqual(self.post("post maker Etto")[0], PREFIX + long_story["caption"])  # a real, long story is never cut

    def test_maker_key_case_spaces_apostrophe_and_punctuation(self):
        for send, key in (("POST Maker Linn's", "Linn's"), ("pOsT mAkEr   Cal Poly  ", "Cal Poly"), ("post maker Dot Farm.", "Dot Farm."),
                          ("post maker Bang Farm!", "Bang Farm!"), ("post maker Two  Spaces", "Two  Spaces"),
                          ("post maker Question Farm?", "Question Farm?"), ("post maker Joebella / Avocado Shack", "Joebella / Avocado Shack")):
            with self.subTest(send=send):
                want = self.want(key)
                self.assertTrue(want["draft"], want)
                self.assertEqual(self.post(send), (PREFIX + want["caption"], []))
        for send, said in (("post maker fixture-FARM", "fixture-FARM"), ("post maker cal poly", "cal poly"), ("post maker Two Spaces", "Two Spaces"),
                           ("post maker Dot Farm", "Dot Farm"), ("post maker Etto and more", "Etto and more"), ("post maker Linn’s", "Linn’s")):
            with self.subTest(send=send):  # no folding, no alias, no search by name
                self.assertEqual(self.post(send), (f"No maker {said}; send find <words> for keys.", []))
        self.assertEqual(self.post("post maker Fixture Farm")[0], "No maker Fixture Farm; send find <words> for keys.")  # a name is not a key

    def test_missing_key_and_bad_text_usage(self):
        before, calls = self.untouched(), []
        with mock.patch.object(self.interp, "interpret", side_effect=lambda *a, **k: calls.append(a)):
            for send in ("post maker", "Post Maker   ", "post maker?", "post maker!", "post maker Cal\nPoly", "post maker Cal\x07Poly", "post maker\nEtto"):
                with self.subTest(send=send):
                    self.assertEqual(self.post(send), (USAGE, []))
        self.assertEqual((calls, self.untouched()), ([], before))

    def test_lookalikes_and_other_post_modes_unchanged(self):
        for send in ("postmaker Etto", "post makers Etto"):
            with self.subTest(send=send):
                self.assertNotEqual(self.say(send), "post")
                self.assertFalse(any(PREFIX in r for r in self.replies()))
        self.assertEqual(self.post("post photo-product-001x")[0], "I don't know a product called photo-product-001x. Try find and a word from its name.")
        self.assertEqual(self.post("post hike nope")[0], "I don't know a hike called nope. Try find and a word from its name.")
        self.assertEqual(self.post("post maker Etto and more")[0], "No maker Etto and more; send find <words> for keys.")

    def test_hidden_unknown_no_active_and_builder_refusals(self):
        for path, key, extra in ((self.makers, "makers", BAD), (self.products, "products", BAD_PRODUCTS)):  # content the site would not accept
            doc = json.loads(path.read_text("utf-8"))
            doc[key].update(extra) if key == "makers" else doc[key].extend(extra)
            path.write_text(json.dumps(doc), "utf-8")
        for send, key, words in (("post maker zz", "zz", "No maker zz; send find <words> for keys."),
                                 ("post maker Hidden Farm", "Hidden Farm", "Maker Hidden Farm is hidden; nothing to draft."),
                                 ("post maker Empty Farm", "Empty Farm", "Maker Empty Farm has no active products on the site."),
                                 ("post maker Held Farm", "Held Farm", "Maker Held Farm has no active products on the site."),
                                 ("post maker No Story", "No Story", "Cannot draft a post for No Story: maker record incomplete."),
                                 ("post maker Tag Farm", "Tag Farm", "Cannot draft a post for Tag Farm: free text has a hashtag or account name."),
                                 ("post maker Long Farm", "Long Farm", "Cannot draft a post for Long Farm: caption too long.")):
            with self.subTest(send=send):
                self.assertEqual(self.want(key).get("draft"), False)
                self.assertEqual(self.post(send), (words, []))
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_unavailable_content_is_plain_refusal(self):
        self.makers.write_text("{not json", "utf-8")
        self.assertEqual(self.post("post maker fixture-farm"), (UNAVAILABLE, []))
        self.makers.unlink()
        self.assertEqual(self.post("post maker fixture-farm"), (UNAVAILABLE, []))
        self.makers.write_text(json.dumps({"schemaVersion": 1, "makers": []}), "utf-8")  # the builder's own "cannot read content"
        self.assertEqual(self.post("post maker fixture-farm"), (UNAVAILABLE, []))
        with mock.patch.object(editor, "_load", side_effect=editor.UnsafeState("/private/state/path")):  # unsafe writer state
            text, files = self.post("post maker fixture-farm")
        self.assertEqual((text, files), (UNAVAILABLE, []))
        for text in (UNAVAILABLE,):
            self.assertNotRegex(text, r"Traceback|/home|/private|\.json")
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_paused_lapsed_proposal_and_question_unchanged(self):
        want = PREFIX + self.want("fixture-farm")["caption"]
        draft, _ = self.propose("hours")
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.now = T0 + timedelta(seconds=601)  # the proposal has lapsed but no other message has swept it
        before = self.untouched()
        calls = []
        with mock.patch.object(self.interp, "interpret", side_effect=lambda *a, **k: calls.append(a)):
            for send, said in (("post maker fixture-farm", want), ("post maker zz", "No maker zz; send find <words> for keys."), ("post maker", USAGE)):
                with self.subTest(send=send):
                    self.assertEqual(self.post(send), (said, []))
        self.assertEqual((calls, self.untouched()), ([], before))
        self.assertEqual(self.drafts()[0]["state"], "proposed")  # not swept to expired
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")  # a later message still expires it
        self.assertEqual(self.drafts()[0]["state"], "expired")

    def test_question_and_exhausted_cap_are_unchanged(self):
        self.set_settings({**SETTINGS, "interpreterDailyCap": 1})
        self.conv = self.open()
        self.assertEqual(self.say("when?"), "question")
        self.replies()
        self.assertEqual(self.say("hours"), "daily-limit")
        self.replies()
        before = (self.untouched(), self.conv.db.execute("SELECT day, calls FROM usage").fetchall())
        want = PREFIX + self.want("fixture-farm")["caption"]
        self.assertEqual(self.post("post maker fixture-farm"), (want, []))
        self.assertEqual((self.untouched(), self.conv.db.execute("SELECT day, calls FROM usage").fetchall()), before)

    def test_duplicate_echo_stranger_and_group(self):
        self.assertEqual(self.say("post maker fixture-farm", pid="m-dup"), "post")
        self.assertEqual(len(self.replies()), 1)
        self.assertEqual((self.say("post maker fixture-farm", pid="m-dup"), self.replies()), ("duplicate", []))
        self.assertEqual(self.say("post maker fixture-farm", sender=STRANGER), "ignored")
        self.assertEqual(self.say("post maker fixture-farm", chat=GROUP), "ignored")
        self.assertEqual(self.say("post maker fixture-farm", from_me=True), "echo")
        self.assertEqual(self.replies(), [])

    def test_help_and_commands_maker_example(self):
        plain = voice.plain(conversation.help_detail("post"))  # AV1052-12: the full post lines are in `help post`
        self.assertEqual(plain, "post Hass avocado - a caption to copy for a product\npost maker fixture-farm - a caption to copy for a maker\n"
                                "post notice - a caption for the home page notice\n"  # AV1104-07 adds the notice line
                                "post today - a caption for what you checked today")  # AV1104-08 adds the today line
        for line in plain.splitlines(): self.assertLessEqual(len(line), 70)
        for bad in ("<id>", "<$>", "<code>"): self.assertNotIn(bad, plain)
        [(_, example, row)] = [r for r in rows(DOC.read_text("utf-8")) if r[0].startswith("`post maker")]
        self.assertEqual(verb(re.findall(r"`([^`]+)`", example)[0]), "post")
        self.assertEqual(conversation.parse_command(re.findall(r"`([^`]+)`", example)[0]), ("post", "maker fixture-farm"))
        self.assertIn("Nothing is posted", row)


if __name__ == "__main__":
    unittest.main()
