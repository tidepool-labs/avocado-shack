"""HASS listing S1 (reports/pilot/hass/specs/first-public-listing-plan.md): the first-listing journey through the real chat, the
real release engine and the real site build, offline.

The owner sends a photo with a price (plus a cost and a stock count that must stay private); the real NPP job drafts a new
product and sends its card; nothing is pushed before the coded yes (a wrong code changes nothing); the yes publishes the product
to a disposable local bare remote built by the real site build; the owner is told `Posted: <item link>` once, only after the live
check reads it back; `undo` + its coded yes takes it down, and the whole website tree is then byte-for-byte what it was before;
a second undo pushes nothing. With the STOP file present the yes is refused and the website is unchanged.
Shared, not copied: the release harness and real build from test_live_add.LiveAddEndToEnd, the listing stages, chat transport
and previewer from test_npp_undo_journey. Nothing here touches the live site, host.json, real state, a model or the network.
Run: python3 -B -m unittest hass.tests.test_live_listing_e2e -v
"""
from datetime import timedelta
import hashlib
from pathlib import Path

from hass import conversation, editor, preview
from hass.npp import picture
from hass.npp.job import Card
from hass.tests import test_live_add as la
from hass.tests.test_conversation import CHAT, OWNER
from hass.tests.test_editor import git
from hass.tests.test_npp_job import Scheduler
from hass.tests.test_npp_undo_journey import ALT, MAKER, NAME, PRICE, _ChatTransport, _HidePreviewer, _ListingStages
from hass.tests.test_photo_draft import JPG

COST, STOCK = "6.17", "23"  # said in the photo caption; neither may reach the website or any reply
CAPTION = f"sell ${PRICE}, cost ${COST}, {STOCK} in stock"
CHANGED = {"catalog-products.js", "producers.js"}  # plus the new picture; every other file stays byte-identical


class _Photos:
    def fetch(self, provider_id, count):
        return [JPG][:count]


class _CardPreviewer(preview.Previewer):
    def capture(self, files, target, out_png, assets=None, **kwargs):
        target = {**target, "cardOnly": True, "price": f"${PRICE} each"}
        return super().capture(files, target, out_png, assets=assets, **kwargs)


class _RenderedListingStages(_ListingStages):
    """Keep the deterministic identification fixture, but capture the actual draft card."""
    def __init__(self, conv, engine, root, worktree):
        super().__init__(engine, root, True)
        self.conv = conv
        self.previewer = _CardPreviewer(worktree, viewports=("phone",))
        self.shot = None

    def render(self, work, listing):
        out = self.editor.prepare([
            {"op": "maker.add", "args": MAKER},
            {"op": "product.add", "args": {
                "name": NAME, "brand": MAKER["name"], "producerKey": MAKER["key"], "category": "pantry",
                "description": "Quince jelly.", "sellingPrice": f"{listing['price']} each",
                "photo": work.request["attachments"][0], "imageAlt": ALT,
            }},
        ])
        if out["result"] != "ok":
            raise AssertionError(out)
        draft = out["draft"]
        (path, digest), = draft["assets"].items()
        old = self.conv.previewer
        try:
            self.conv.previewer = self.previewer
            self.shot = self.conv._capture(draft)
        finally:
            self.conv.previewer = old
        if not self.shot.get("ok"):
            raise AssertionError(self.shot)
        return Card(draft, Path(self.shot["png"]).read_bytes(), "raw", path,
                    digest.removeprefix("sha256:"), "picture: your own photo")


class FirstListingEndToEnd(la.LiveAddEndToEnd):
    def setUp(self):
        super().setUp()
        cfg = editor._read(self.repo.state / "config.json")
        cfg["settings"] = {**cfg["settings"], "npp": True, "approvalNeedsCode": True}
        editor._write_json(self.repo.state / "config.json", cfg)
        self.live.settings = conversation.load_settings(self.repo.state)
        self.scheduler, self.transport, self.serial = Scheduler(), _ChatTransport(), 0
        self.conv = conversation.Conversation(
            self.repo.state, self.live, conversation.FixtureInterpreter({}), lambda: self.now, _HidePreviewer(),
            photos=_Photos(), npp_stages=_ListingStages(self.live, self.repo.media, True), npp_executor=self.scheduler,
            npp_receipt_for=self.transport.receipt_for)
        self.stages = _RenderedListingStages(self.conv, self.live, self.repo.media, self.repo.wt)
        self.conv.npp.stages = self.stages
        self.addCleanup(self.conv.db.close)
        self.live.conv = self.conv  # as host.make_worker does

    def say(self, text, *, photos=0):
        self.serial += 1
        self.now += timedelta(seconds=1)
        msg = conversation.Inbound(f"listing-{self.serial}", CHAT, OWNER, text, received_at=self.now.isoformat(), attachments=photos)
        return self.conv.handle(msg, forwarded_at=self.now)

    def sent(self):
        before = len(self.transport.texts)
        self.conv.flush(self.transport)
        return self.transport.texts[before:]

    def tree(self):
        """The whole website on the bare remote's main: the tree listing and every blob (not index.html only)."""
        return git(self.bare, "ls-tree", "-r", "main"), {rel: self.site_file(rel) for rel in self.site_files()}

    def run_job(self):
        for _ in range(8):
            self.conv.flush(self.transport)
            if self.scheduler.steps:
                self.scheduler.run()
        self.assertFalse(self.scheduler.steps)

    def card(self):
        """Photo + caption (with private cost and stock) -> the job asks for the selling price -> the price -> the real NPP
        job's card, delivered (receipt confirmed). Returns (job, change_id)."""
        self.assertEqual(self.say(CAPTION, photos=1), "npp-working")
        self.run_job()
        self.assertEqual(self.transport.texts[-1:], ["What's the selling price?"])
        self.say(f"${PRICE}")
        self.run_job()
        job = self.conv.db.execute("SELECT job_id FROM npp_jobs").fetchone()[0]
        version = self.conv.npp.version(job, 1)
        self.assertIsNotNone(version, self.transport.texts)
        self.assertEqual(version["state"], "queued", self.transport.texts)
        self.transport.receipts[version["outbox_id"]] = dict(
            state="confirmed", png_sha256=version["card_png_sha"], provider_guid="fixture-card", confirmed_at=self.now.isoformat())
        self.sent()
        (card_text, png, digest), = self.transport.cards.values()
        self.assertIn(f"yes {job}-1", card_text)
        shot = self.stages.shot
        evidence = shot["cardEvidence"]
        self.assertEqual(hashlib.sha256(png).hexdigest(), evidence["pngSha256"])
        self.assertEqual(digest, evidence["pngSha256"])
        fragments = [part["text"] for part in evidence["fragments"]]
        self.assertIn(NAME, fragments)
        self.assertIn("Quince jelly.", fragments)
        self.assertEqual(fragments[evidence["priceIndex"]], f"${PRICE} each")
        ocr = picture.read_text(png)
        self.assertIsNotNone(ocr, "OCR of delivered card failed")
        for value in (COST, STOCK):
            self.assertNotIn(value, shot["cardText"])
            self.assertNotIn(value, " ".join(fragments))
            self.assertNotIn(value, ocr)
        return job, version["change_id"]

    def assert_private_numbers_stay_private(self):
        _listing, files = self.tree()
        for value in (COST, STOCK + " in stock"):
            self.assertFalse([rel for rel, data in files.items() if value.encode() in data], value)
        outgoing = self.transport.texts + [c[0] for c in self.transport.cards.values()] + [p[0] for p in self.transport.previews]
        self.assertFalse([t for t in outgoing if COST in t or f"{STOCK} in stock" in t], outgoing)

    def test_photo_card_yes_posted_undo_and_the_whole_site_is_back(self):
        baseline = self.tree()
        job, change = self.card()
        # (2) nothing is pushed before the coded yes; a wrong code changes nothing either
        self.assertEqual(self.push_calls, 0)
        self.assertNotEqual(self.say(f"yes {job}-2"), "approved")  # the code of a version that was never sent
        self.assertEqual((self.push_calls, self.tree()), (0, baseline))
        # (3) the yes: one push; the new product with its price is in the built site; only its files changed
        self.assertEqual(self.say(f"yes {job}-1"), "approved")
        self.assertEqual(self.push_calls, 1)
        catalog = self.site_file("catalog-products.js")
        self.assertIn(NAME.encode(), catalog)
        self.assertIn(PRICE.encode(), catalog)
        listing, files = self.tree()
        picture = {rel for rel in set(files) - set(baseline[1])}
        self.assertEqual(len(picture), 1)
        self.assertTrue(next(iter(picture)).startswith("assets/products/photo-"), picture)
        self.assertEqual({rel for rel in files if files[rel] != baseline[1].get(rel)}, CHANGED | picture)
        self.assert_private_numbers_stay_private()
        # (4) `Posted:` once, only after the live check has read the change back
        before_check = self.sent()
        self.assertFalse([t for t in before_check if t.startswith("Posted:")], before_check)
        self.settle()
        self.assertEqual(self.entry()["state"], "live")
        pid = next(r["key"] for r in self.live.show(change)["change"]["records"] if r["collection"] == "products")
        self.assertEqual([t for t in self.sent() if t.startswith("Posted:")],
                         [f"Posted: https://theavocadoman.com/?item={pid}#market (say undo to take it down)"])
        self.settle()
        self.assertEqual(self.sent(), [])
        # (5) chat undo + its coded yes: a second push, and the whole website tree is the baseline again
        self.now += timedelta(seconds=61)
        self.assertEqual(self.say("undo"), "proposed")
        code = self.conv.db.execute("SELECT code FROM drafts WHERE state = 'proposed'").fetchone()[0]
        self.assertEqual(self.push_calls, 1)
        self.assertEqual(self.say(f"yes {code}"), "approved")
        self.assertEqual(self.push_calls, 2)
        self.settle()
        self.assertEqual(self.tree(), baseline)
        # (6) the books hold exactly [change, undo], both live; a second undo pushes nothing
        self.assertEqual([(j["kind"], j["state"]) for j in self.live.books.journals()], [("change", "live"), ("undo", "live")])
        self.sent()
        self.now += timedelta(seconds=61)
        self.assertNotEqual(self.say("undo"), "approved")
        self.assertEqual((self.push_calls, self.tree()), (2, baseline))
        self.assert_private_numbers_stay_private()

    def test_with_the_stop_file_the_yes_is_refused_and_the_website_is_unchanged(self):
        baseline = self.tree()
        job, _change = self.card()
        Path(self.cfg["stopFile"]).write_text("")
        self.say(f"yes {job}-1")
        self.settle()
        self.assertEqual((self.push_calls, self.tree()), (0, baseline))
        told = self.sent()
        self.assertFalse([t for t in told if t.startswith("Posted:")], told)
        self.assertTrue([t for t in told if "Nothing changed" in t], told)


for _name in dir(la.LiveAddEndToEnd):  # the inherited release / live-add tests run in their own modules
    if _name.startswith("test") and _name not in FirstListingEndToEnd.__dict__:
        setattr(FirstListingEndToEnd, _name, None)


if __name__ == "__main__":
    import unittest
    unittest.main()
