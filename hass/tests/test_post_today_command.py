"""AV1104-08: `post today` replies social_draft.build_today's caption for the products Michael's shelf check marked Available today or
Limited, only when that check is Pacific today. Read-only: nothing is posted, scheduled, stored or drafted; works while paused or out of
interpreter calls. Synthetic fixtures only.
Run: python3 -B -m unittest hass.tests.test_post_today_command -v

Each test names the contract it protects and the believable bug that fails it.
"""
import json
import re
import unittest
from datetime import timedelta
from unittest import mock

from hass import conversation, editor, social_draft
from hass.content_model import load_content
from hass.tests.test_commands_doc import DOC, rows, verb
from hass.tests.test_conversation import T0, ConversationTestCase
from hass.tests.test_editor import git
from hass.tests.test_status_pause import StoreMixin

PREFIX = "Draft post (not posted; copy it yourself):\n"
EMPTY = "No products were marked Available today or Limited in today's shelf check."
UNAVAILABLE = "Catalog unavailable right now; nothing changed."
TODAY = "2026-11-02"  # T0 is Monday 2026-11-02 09:00 Pacific


class PostTodayTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.content = self.repo.wt / "hass" / "content"
        self.store, self.products = self.content / "store.json", self.content / "products.json"
        doc = json.loads(self.products.read_text("utf-8"))
        self.ids = [p["id"] for p in doc["products"] if p.get("status") == "active"][:3]
        self.names = {p["id"]: p["name"] for p in doc["products"]}
        self.set_check(TODAY, {self.ids[0]: ("yes", TODAY), self.ids[1]: ("limited", TODAY), self.ids[2]: ("no", TODAY)})

    def set_check(self, check, words=None, **store):
        doc = json.loads(self.store.read_text("utf-8"))
        doc.pop("selection_checked_on", None)
        if check is not None: doc["selection_checked_on"] = check
        doc.update(store)
        self.store.write_text(json.dumps(doc), "utf-8")
        if words is not None:
            pdoc = json.loads(self.products.read_text("utf-8"))
            for p in pdoc["products"]:
                for k in ("available", "available_on"): p.pop(k, None)
                if p["id"] in words: p["available"], p["available_on"] = words[p["id"]]
            self.products.write_text(json.dumps(pdoc), "utf-8")
        git(self.repo.wt, "commit", "-qam", "fixture shelf check")  # a clean worktree, so a waiting proposal can exist beside the posts
        self.base = self.count()

    def want(self):
        return social_draft.build_today(load_content(self.content), self.now)

    def post(self, text, **kw):
        self.assertEqual(self.say(text, **kw), "post")
        [row] = self.conv.db.execute("SELECT text, attachments FROM outbox ORDER BY id DESC LIMIT 1").fetchall()
        self.assertEqual(len(self.replies()), 1)
        return row["text"], json.loads(row["attachments"] or "[]")

    def untouched(self):
        return (self.drafts(), self.tables(), self.commits(), self.approvals(), self.editor.applies, self.store.read_bytes(), self.products.read_bytes())

    def test_post_today_equals_builder_without_photo(self):
        """The reply is the builder's caption after the draft line, text only, naming exactly the yes and limited products, and nothing changes.
        Bug caught: a reworded caption, an attached photo, the sold-out product named, or a draft/commit created by a read."""
        want = self.want()
        self.assertEqual(want["caption"].splitlines()[1], f"{self.names[self.ids[0]]}, {self.names[self.ids[1]]}")
        before = self.untouched()
        with mock.patch("socket.socket", side_effect=AssertionError("network")), mock.patch("os.system", side_effect=AssertionError("shell")):
            self.assertEqual(self.post("post today"), (PREFIX + want["caption"], []))
            for send in ("Post Today", "POST TODAY!", "  post today. ", "post today?"):
                with self.subTest(send=send):
                    self.assertEqual(self.post(send), (PREFIX + want["caption"], []))
        self.assertEqual(self.untouched(), before)

    def test_old_missing_or_future_check_is_never_posted_as_today(self):
        """A check from yesterday, a week ago, tomorrow or none gets the one send-the-shelf-check line and no caption, even though the products
        still carry yes words. Bug caught (SHOP-1): an old check posted as today's stock."""
        for check, day in (("2026-10-30", "Friday, October 30"), ("2026-10-26", "Monday, October 26"), ("2026-11-03", "Tuesday, November 3")):
            with self.subTest(check=check):
                self.set_check(check, {self.ids[0]: ("yes", check)})  # the words were set on that very check
                self.assertEqual(self.post("post today"), (f"Your last shelf check was {day}; send today's shelf check first.", []))
        self.set_check(None)
        self.assertEqual(self.post("post today"), ("Your last shelf check was not recorded; send today's shelf check first.", []))
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_today_check_but_nothing_confirmed_and_other_reasons(self):
        """A current check that named nothing gets the exact empty line; a word set on an earlier check is not named; a tagged name is refused
        in plain words, never rewritten; unreadable content says nothing changed. Bug caught: an empty success caption or a stale word named."""
        self.set_check(TODAY, {self.ids[0]: ("yes", "2026-10-30"), self.ids[1]: ("no", TODAY)})
        self.assertEqual(self.post("post today"), (EMPTY, []))
        doc = json.loads(self.products.read_text("utf-8"))
        for p in doc["products"]:
            if p["id"] == self.ids[0]: p.update({"name": "Fish #deal", "available_on": TODAY})
        self.products.write_text(json.dumps(doc), "utf-8")
        git(self.repo.wt, "commit", "-qam", "tagged")
        self.base = self.count()
        self.assertEqual(self.post("post today"), ("Cannot draft a today post: free text has a hashtag or account name.", []))
        self.store.write_text("{not json", "utf-8")
        self.assertEqual(self.post("post today"), (UNAVAILABLE, []))
        with mock.patch.object(editor, "_load", side_effect=editor.UnsafeState("/private/state/path")):
            self.assertEqual(self.post("post today"), (UNAVAILABLE, []))
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_follows_the_clock_across_pacific_midnight(self):
        """The same content drafts late on the check day and asks for a new check after Pacific midnight. Bug caught: a UTC date or cached answer."""
        self.now = T0 + timedelta(hours=14)  # Monday 23:00 Pacific
        self.assertTrue(self.post("post today")[0].startswith(PREFIX))
        self.now = T0 + timedelta(hours=16)  # Tuesday 01:00 Pacific
        self.assertEqual(self.post("post today"), ("Your last shelf check was Monday, November 2; send today's shelf check first.", []))

    def test_lookalikes_and_other_post_modes_unchanged(self):
        """Only the whole argument `today` is this command; other words keep their old meaning. Bug caught: `post today extra` or `post todays` dispatching."""
        with mock.patch.object(self.interp, "interpret", side_effect=lambda *a, **k: None):
            self.assertEqual(self.post("post todays")[0], "I don't know a product called todays. Try find and a word from its name.")
            self.assertNotEqual(self.say("post today for the market"), "post")
            self.assertFalse(any(PREFIX in r for r in self.replies()))
        self.assertEqual(self.post("post hike nope")[0], "I don't know a hike called nope. Try find and a word from its name.")
        self.assertEqual(self.post("post maker zz")[0], "No maker zz; send find <words> for keys.")
        self.assertTrue(self.post("post notice")[0].startswith("There is no notice"))

    def test_paused_lapsed_and_capped_read_only(self):
        """While paused, with a lapsed proposal waiting, or with the interpreter cap used up, the reply still comes and no row, usage count or
        expiry changes. Bug caught: a read-only post sweeping a waiting draft, spending a call, or being refused while paused."""
        want = PREFIX + self.want()["caption"]
        draft, _ = self.propose("hours")
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.now = T0 + timedelta(seconds=601)  # the proposal has lapsed but no other message has swept it
        before = self.untouched()
        with mock.patch.object(self.interp, "interpret", side_effect=AssertionError("interpreter")):
            self.assertEqual(self.post("post today"), (want, []))
        self.assertEqual(self.untouched(), before)  # includes every table row, so no usage count moved
        self.assertEqual(self.drafts()[0]["state"], "proposed")  # not swept to expired
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")  # a later message still expires it
        self.assertEqual(self.drafts()[0]["state"], "expired")

    def test_help_and_commands_row(self):
        """Help and COMMANDS.md carry one parsable example. Bug caught: a command nobody can find, or an example that does not parse."""
        self.assertIn("post today", conversation.help_detail("post"))
        [(send, example, row)] = [r for r in rows(DOC.read_text("utf-8")) if r[0].startswith("`post today")]
        self.assertEqual(verb(re.findall(r"`([^`]+)`", example)[0]), "post")
        self.assertEqual(conversation.parse_command("post today"), ("post", "today"))
        for phrase in ("Draft post (not posted; copy it yourself):", "Nothing is posted, scheduled or saved", "works while paused",
                       "Your last shelf check was <day>; send today's shelf check first.", "at most 12, then `and more`", "There is no photo"):
            self.assertIn(phrase, " ".join(row.split()))


if __name__ == "__main__":
    unittest.main()
