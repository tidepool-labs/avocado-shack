"""AV1622-09 (H17): `listing <id>` replies what the saved content shows for one product, maker, hike or route idea;
read-only, works while paused. Fixture content only.
Run: python3 -B -m unittest hass.tests.test_listing_command -v
"""

import json
import unittest
from datetime import datetime, timedelta, timezone

from hass import conversation, sitegen, voice
from hass.content_model import load_content
from hass.tests.test_commands_doc import verb
from hass.tests.test_conversation import T0, ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

UNAVAILABLE = "I can't look that up right now. Nothing has changed. Could you try again in a little while?"
HEAD = 'This is from my saved copy, not a live look at the website:'
NONE = "I don't know that one. Try find and a word from its name."
MANY = "That fits more than one thing. Could you say a bit more of its name?"
USAGE = voice.plain(conversation.LISTING_USAGE)  # AV1052-07: names id, name or alias and find


class ListingTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name, **k: (self.calls.append(_n), _r(*a, **k))[1])
        self.addCleanup(lambda: self.assertEqual(self.calls, [], "listing reached the interpreter/editor"))
        self.cdir = self.repo.wt / "hass" / "content"

    def edit(self, name, change):
        path = self.cdir / name
        doc = json.loads(path.read_text("utf-8"))
        change(doc)
        path.write_text(json.dumps(doc), "utf-8")

    def product(self, pid, **fields):
        def go(doc):
            rec = next(p for p in doc["products"] if p["id"] == pid)
            for k, v in fields.items():
                if v == "<DEL>": rec.pop(k, None)
                else: rec[k] = v
        self.edit("products.json", go)

    def pid(self, n=0):
        return json.loads((self.cdir / "products.json").read_text("utf-8"))["products"][n]["id"]

    def listing(self, ident="", *, text=None):
        n = self.n
        self.assertEqual(self.say(text if text is not None else f"listing {ident}".strip()), "listing")
        self.assertEqual(self.disposition(f"m{n + 1}"), "listing")
        [reply] = self.replies()
        return reply.splitlines()

    def fields(self, ident):
        lines = self.listing(ident)
        self.assertEqual(lines[0], HEAD)
        fields = dict(ln.split(": ", 1) for ln in lines[1:])
        return fields.get("Name", fields.get("Title")), fields

    def checked(self, day="2026-11-02"):
        self.edit("store.json", lambda doc: doc.update(selection_checked_on=day))

    # -- product ---------------------------------------------------------------------------------------------------
    def test_product_fields_and_description_cut(self):
        pid = self.pid()
        for n, tail in ((119, ""), (120, ""), (121, "…")):
            desc = "x" * n
            self.product(pid, description=desc)
            head, f = self.fields(pid)
            self.assertEqual((head, f["Description"]), ("Hass avocado", "x" * min(n, 120) + tail), n)
        held = {"hold": {"reason": "fixture", "source": "https://example.com/"}, "status": "held"}
        self.product(pid, **held, description="<DEL>", producerKey="<DEL>", displayBrand="<DEL>", brand="Brand B")  # held may omit them
        head, f = self.fields(pid)
        self.assertEqual((f["Description"], f["Shelf"], f["Maker"], f["Status"]), ("nothing yet", "Fruit", "Brand B", "on hold"))
        self.assertEqual(list(f), ["Name", "Maker", "Shelf", "Description", "Availability", "Status"])
        self.product(pid, status="active", hold="<DEL>", description="d", producerKey=None, displayBrand="Brand B")
        maker_key = self.maker_key()
        self.product(pid, producerKey=maker_key)
        self.assertEqual(self.fields(pid)[1]["Maker"], self.maker_name(maker_key))  # resolved name beats brand
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_saved_selling_price_only_for_active_products(self):
        # A fixed field list can silently omit the site's saved price, while an
        # unconditional append can expose prices retained on hidden or held rows.
        pid = self.pid()
        path = self.cdir / "products.json"
        self.checked()
        for status, saved, expected in (
            ("active", "9.50", ["Selling price: $9.50"]),
            ("active", "<DEL>", []),
            ("hidden", "9.50", []),
            ("held", "9.50", []),
        ):
            with self.subTest(status=status, saved=saved):
                hold = {"reason": "fixture", "source": "https://example.com/"} if status == "held" else "<DEL>"
                self.product(pid, status=status, sellingPrice=saved, hold=hold, available="yes", available_on="2026-11-02")
                before = path.read_bytes()
                lines = self.listing(pid)
                self.assertEqual(lines[0], HEAD)
                self.assertIn("Availability: Available today" if status == "active" else "Availability: not showing", lines)
                self.assertEqual([line for line in lines if line.startswith("Selling price:")], expected)
                self.assertEqual(path.read_bytes(), before)
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def maker_key(self):
        return next(iter(json.loads((self.cdir / "makers.json").read_text("utf-8"))["makers"]))

    def maker_name(self, key):
        return json.loads((self.cdir / "makers.json").read_text("utf-8"))["makers"][key]["name"]

    def test_product_name_with_several_words(self):
        self.assertEqual(self.fields("Hass avocado")[0], "Hass avocado")
        self.assertEqual(self.listing(text="listing Hass avocado?")[0], HEAD)

    def test_availability_matches_shared_helper(self):
        pid = self.pid()
        self.edit("store.json", lambda doc: doc.pop("selection_checked_on", None))
        self.product(pid, available="<DEL>", available_on="<DEL>")
        self.assertEqual(self.fields(pid)[1]["Availability"], "not confirmed")  # absent
        self.checked("2026-11-02")
        for word, label in (("yes", "Available today"), ("limited", "Limited"), ("no", "Sold out")):
            self.product(pid, available=word, available_on="2026-11-02")
            self.assertEqual(self.fields(pid)[1]["Availability"], label)
        self.product(pid, available="yes", available_on="2026-10-30")  # its own older day: not the store's latest
        self.checked("2026-11-02")
        content = load_content(self.cdir)
        want = sitegen.availability_label(content.products[0], content.store, conversation.shop_today(T0))
        self.assertEqual(self.fields(pid)[1]["Availability"], want)
        self.assertTrue(want.startswith("Last confirmed"))
        # Pacific boundary: 07:30 UTC on 11-10 is still 11-09 in Pacific; the check of 11-02 is 7 days old (fresh), 11-10 is stale
        self.product(pid, available="yes", available_on="2026-11-02")
        self.now = datetime(2026, 11, 10, 7, 30, tzinfo=timezone.utc)
        self.assertEqual(self.fields(pid)[1]["Availability"], "Available today")
        self.now = datetime(2026, 11, 10, 8, 30, tzinfo=timezone.utc)  # 00:30 PST on 11-10: now stale
        self.assertEqual(self.fields(pid)[1]["Availability"], "Last confirmed Monday, November 2")
        for status in ("hidden", "held"):  # never implied buyable
            self.now = T0
            extra = {"hold": {"reason": "fixture", "source": "https://example.com/"}} if status == "held" else {}
            self.product(pid, status=status, **extra)
            f = self.fields(pid)[1]
            self.assertEqual((f["Availability"], f["Status"]), ("not showing", "on hold" if status == "held" else status))

    # -- maker -----------------------------------------------------------------------------------------------------
    def test_maker_exact_case_and_active_count(self):
        def go(doc):
            doc["makers"]["MixedCase"] = {"name": "Mixed Case Co", "place": "Cayucos", "story": "A story.", "url": "https://example.com/"}
            doc["makers"]["NoProducts"] = {"name": "No Products Co", "place": "Morro Bay", "story": "A story.", "url": "https://example.com/", "hidden": True}
        self.edit("makers.json", go)
        ids = [json.loads((self.cdir / "products.json").read_text("utf-8"))["products"][i]["id"] for i in range(3)]
        for i, status in zip(ids, ("active", "active", "hidden")):
            self.product(i, producerKey="MixedCase", status=status)
        head, f = self.fields("MixedCase")
        self.assertEqual(head, "Mixed Case Co")
        self.assertEqual(f, {"Name": "Mixed Case Co", "Place": "Cayucos", "Products showing": "2", "Status": "on the website"})
        self.assertEqual(self.listing("mixedcase"), [NONE])  # keys keep their exact case
        self.assertEqual(self.fields("mixed case co")[0], "Mixed Case Co")  # names do not
        head, f = self.fields("NoProducts")
        self.assertEqual((f["Place"], f["Products showing"], f["Status"]), ("Morro Bay", "0", "hidden"))

    # -- hike and route idea ---------------------------------------------------------------------------------------
    def event(self, eid, **fields):
        rec = {"id": eid, "title": "Fixture hike", "startsAt": "2026-11-14T09:00:00-08:00", "timezone": "America/Los_Angeles",
               "status": "scheduled"} | fields
        self.edit("community.json", lambda doc: doc["events"].append(rec))

    def test_hike_and_route_details(self):
        self.event("hike-a", startsAt="2026-11-14T09:00:00-08:00", meetingPoint="Trailhead lot", capacity=12)
        self.event("hike-b", startsAt="2026-07-04T23:30:00-07:00", status="cancelled")  # DST offset; validation allows only Pacific offsets
        head, f = self.fields("hike-a")
        self.assertEqual(head, "Fixture hike")
        self.assertEqual(f, {"Title": "Fixture hike", "Starts": "Saturday, Nov 14 at 9 am", "Status": "coming up",
                             "Meeting place": "Trailhead lot", "Guest limit": "12"})
        head, f = self.fields("hike-b")
        self.assertEqual((f["Starts"], f["Status"], f["Meeting place"], f["Guest limit"]),
                         ("Saturday, Jul 4 at 11:30 pm", "cancelled", "nothing yet", "nothing yet"))  # DST offset
        self.edit("community.json", lambda doc: doc["routeIdeas"][0].update(status="hidden"))
        rid = json.loads((self.cdir / "community.json").read_text("utf-8"))["routeIdeas"][0]
        head, f = self.fields(rid["id"])
        self.assertEqual((head, f), (rid["title"], {"Title": rid["title"], "Place": rid["place"], "Status": "hidden"}))

    def test_route_idea_by_title(self):
        """A route idea is found by its title, one word or several, without the interpreter; two matches are not guessed."""
        for title in ("Zebrawalk", "Zebra Coastal Walk"):
            self.edit("community.json", lambda doc, t=title: doc["routeIdeas"][0].update(title=t))
            head, f = self.fields(title)
            self.assertEqual((head, f["Title"]), (title, title))
        self.edit("community.json", lambda doc: doc["routeIdeas"].append(dict(doc["routeIdeas"][0], id="route-twin")))
        self.edit("community.json", lambda doc: doc["routeIdeas"][0].update(title="Zebrawalk"))
        self.edit("community.json", lambda doc: doc["routeIdeas"][1].update(title="Zebrawalk"))
        self.assertEqual(self.listing("Zebrawalk"), [NONE])  # two routes share the title: no guess
        for r in (0, 1): self.edit("community.json", lambda doc, r=r: doc["routeIdeas"][r].update(title="Zebra Coastal Walk"))
        self.calls.clear()
        self.assertEqual(self.listing("Zebra Coastal Walk"), [NONE])  # several words, two routes: still no guess, no interpreter
        self.assertEqual(self.calls, [])

    # -- usage, unknown, collision, lookalikes ---------------------------------------------------------------------
    def test_usage_unknown_collision_and_lookalikes(self):
        self.assertEqual(self.listing(text="listing"), [USAGE])
        self.assertEqual(self.listing("no-such-id"), [NONE])
        pid = self.pid()
        self.assertEqual(self.fields(f"{pid}!".replace("!", ""))[0], "Hass avocado")
        self.assertEqual(self.listing(text=f"Listing {pid}!")[0], HEAD)  # case of the verb and a final ! do not matter
        self.assertEqual(self.listing(text=f"listing {pid.upper()}"), [NONE])  # the id is not folded or repaired
        self.edit("community.json", lambda doc: doc["events"].append(
            {"id": pid, "title": "Clash", "startsAt": "2026-11-14T09:00:00-08:00", "timezone": "America/Los_Angeles", "status": "scheduled"}))
        self.assertEqual(self.listing(pid), [MANY])
        # a sentence is not the command: it goes to the interpreter as a change request
        self.assertIsNone(conversation.parse_command("listing of all the jams please"))
        self.assertEqual(verb("listing Etto"), "listing")
        self.assertEqual(conversation.parse_command("listing Etto."), ("listing", "Etto"))
        self.calls.clear()
        self.say("listing of everything please")
        self.assertEqual(self.calls, ["interpret"])
        self.calls.clear()
        self.replies()

    def test_unreadable_or_invalid_content(self):
        pid = self.pid()
        path = self.cdir / "products.json"
        good = path.read_text("utf-8")
        path.write_text("{not json", "utf-8")
        self.assertEqual(self.listing(pid), [UNAVAILABLE])
        path.write_text(good, "utf-8")
        for bad in ("two\nlines", "x" * 700, "bad<b>"):  # newline, over the limit, markup: never echoed
            self.product(pid, description=bad)
            reply = self.listing(pid)
            self.assertEqual(reply, [UNAVAILABLE], bad[:10])
        held = {"hold": {"reason": "fixture", "source": "https://example.com/"}, "status": "held"}
        for bad in ("first line\nStatus: active <b>markup</b>", "bad<b>", "x\u200by"):  # held skips validate_products
            self.product(pid, **held, description=bad)
            self.assertEqual(self.listing(pid), [UNAVAILABLE], repr(bad))
        self.product(pid, **held, description="fine held text")
        self.assertEqual(self.fields(pid)[1]["Description"], "fine held text")
        self.product(pid, status="active", hold="<DEL>", description="fine")
        self.edit("store.json", lambda doc: doc.update(selection_checked_on="not-a-date"))
        self.assertEqual(self.listing(pid), [UNAVAILABLE])
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_paused_lapsed_draft_and_duplicate(self):
        draft, _reply = self.propose("hours")
        self.calls.clear()  # the proposal is the only allowed interpreter/editor use
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        control = [dict(r) for r in self.conv.db.execute("SELECT * FROM control")]
        tables = self.tables()
        self.now = T0 + timedelta(seconds=601)  # lapsed; no other message has swept it yet
        pid = self.pid()
        self.assertEqual(self.listing(pid)[0], HEAD)
        self.assertEqual([dict(r) for r in self.conv.db.execute("SELECT * FROM control")], control)
        self.assertEqual((self.drafts()[0]["state"], self.approvals(), self.editor.applies, self.tables()), ("proposed", 0, 0, tables))
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")  # a later message still expires it, not the listing
        self.assertEqual(self.drafts()[0]["state"], "expired")
        self.replies()
        # a repeated provider id sends no second reply
        self.say(f"listing {pid}", pid="dup1")
        self.assertEqual(len(self.replies()), 1)
        self.say(f"listing {pid}", pid="dup1")
        self.assertEqual(self.replies(), [])
        # owner-only: a stranger's listing is not answered
        self.say(f"listing {pid}", sender="stranger@example.com", pid="s1")
        self.assertEqual(self.replies(), [])

    def test_help_and_card(self):
        line = "listing Etto - what's shown for one thing"  # AV1052-12: the full line is in `help listing`
        self.assertIn(line, voice.plain(conversation.help_detail("listing")).splitlines())
        self.assertLessEqual(len(line), 70)
        self.assertEqual(verb("listing Etto"), "listing")


if __name__ == "__main__":
    unittest.main()
