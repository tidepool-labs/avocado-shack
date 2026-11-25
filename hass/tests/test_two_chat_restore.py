"""L8: two owners' pending listings survive ONE backup and restore without crossing pictures, cards or confirmation codes.

Mike and G (synthetic addresses) each start a listing in their own one-to-one chat: two different photos, two different names and
prices, two visibly different cards. Both cards are delivered and wait for a yes. The state is backed up WITH the photo originals,
restored into a NEW directory with a NEW worktree (restore pauses it), and a fresh chat is started on the restored copy.

Checked: each chat got only its own card and its own code; a yes carrying the OTHER chat's code is refused before and after the
restore and posts nothing; one yes from the right chat posts only that chat's listing (its price, its photo) once; the saved
conversation keeps each chat's rows apart (own code, own pictures). The other chat's yes after the first listing posted is
pinned to what the product really does (it is not left to chance and never posts the wrong card). The source install is never
touched. Fixtures only: throwaway repos, no network, no service, no live site.
"""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from hass import conversation, statebackup, transcript
from hass.npp import reply
from hass.npp.job import Card, Plan
from hass.skills.testkit import _clocked_editor
from hass.tests import test_npp_edits as edits_tests
from hass.tests import test_npp_undo_journey as journey
from hass.tests.test_editor import git
from hass.tests.test_npp_job import Transport
from hass.tests.test_npp_second_product import png

MIKE, GEE = "mike@example.invalid", "g@example.invalid"
MCHAT, GCHAT = f"iMessage;-;{MIKE}", f"iMessage;-;{GEE}"
TWO = {"ownerSenders": [MIKE, GEE], "ownerChat": MCHAT, "ownerChats": [MCHAT, GCHAT],
       "ownerNames": {MCHAT: "Mike", GCHAT: "G"}, "approvalTtlSeconds": 600}
# One listing per chat: different price, name, alt text, photo and card picture.
LISTINGS = {
    MCHAT: dict(price="12.34", name="Fixture quince jelly", alt="Red jar", photo=png((200, 20, 20)), card=png((250, 120, 120))),
    GCHAT: dict(price="8.75", name="Fixture orchard honey", alt="Gold jar", photo=png((20, 20, 200)), card=png((120, 120, 250))),
}
WHO = {MCHAT: MIKE, GCHAT: GEE}
REFUSED = ("no-target", "unsupported")  # what the chat answers to a yes it cannot match to its own card
BY_PRICE = {v["price"]: v for v in LISTINGS.values()}


def sha(data):
    return hashlib.sha256(data).hexdigest()


class _ChatTransport(Transport):
    """Records which chat each text and card went to."""

    def __init__(self):
        super().__init__()
        self.previews = []
        self.to = {MCHAT: [], GCHAT: []}  # chat -> [(text, card picture or None)]

    def send(self, chat, text, attachments):
        if attachments:  # the fixture's picture of the changed site, sent after a post
            self.previews.append((chat, text))
        else:
            super().send(chat, text, attachments)
        self.to[chat].append((text, None))

    def send_card(self, row, chat, text, png_path, digest):
        super().send_card(row, chat, text, png_path, digest)
        self.to[chat].append((text, Path(png_path).read_bytes()))


class TwoChatRestoreTests(journey.NppUndoJourneyTests):
    def setUp(self):
        super().setUp()
        self.transport = _ChatTransport()
        self.photo_for = {}
        self.jobs = {}
        self.live = self.engine

    # ---- fixtures ----------------------------------------------------------------------------------------------------
    def fetch(self, provider_id, count):
        return [self.photo_for[provider_id]][:count]

    def stages(self):
        return reply.Stages(edits_tests.PINNED, start=self.start_stage, render=self.render_stage)

    def start_stage(self, work):
        price = work.request["slots"]["intake"].get("price")
        if price is None:
            return Plan(questions=(("ask_price", edits_tests.REPLIES["questions"]["ask_price"]),), identified=True)
        return Plan(listing={"name": BY_PRICE[price]["name"], "sellingPrice": price})

    def render_stage(self, work, listing):
        mine = BY_PRICE[listing["sellingPrice"]]
        ops = [{"op": "maker.add", "args": {**journey.MAKER, "key": mine["name"] + " Farm", "name": mine["name"] + " Farm"}},
               {"op": "product.add", "args": {
                   "name": mine["name"], "brand": mine["name"] + " Farm", "producerKey": mine["name"] + " Farm",
                   "category": "pantry", "description": "Fixture listing.", "sellingPrice": listing["sellingPrice"],
                   "photo": work.request["attachments"][0], "imageAlt": mine["alt"]}}]
        out = self.live.prepare(ops)  # cards are made by the engine of whichever install is running
        assert out["result"] == "ok", out
        path, digest = next(iter(out["draft"]["assets"].items()))
        return Card(out["draft"], mine["card"], "raw", path, digest.removeprefix("sha256:"), "picture: your own photo")

    def open_conv(self, state, engine):
        conv = conversation.Conversation(
            state, engine, conversation.FixtureInterpreter({}), self._clock, self.previewer, photos=self,
            npp_stages=self.stages(), npp_executor=self.scheduler, npp_receipt_for=self.transport.receipt_for)
        self.addCleanup(conv.db.close)
        return conv

    def talk(self, chat, text, *, photo=None):
        self.serial += 1
        self.now += journey.timedelta(seconds=1)
        pid = f"fixture-{self.serial}"
        if photo is not None:
            self.photo_for[pid] = photo
        msg = conversation.Inbound(pid, chat, WHO[chat], text, received_at=self.now.isoformat(),
                                   attachments=0 if photo is None else 1)
        result = self.conv.handle(msg, forwarded_at=self.now)
        self.conv.flush(self.transport)
        return result

    def pump(self, conv):
        for _ in range(8):
            conv.flush(self.transport)
            if self.scheduler.steps:
                self.scheduler.run()
        self.assertFalse(self.scheduler.steps)

    def deliver(self, job):
        version = self.conv.npp.version(job, 1)
        self.assertEqual(version["state"], "queued", self.transport.texts)
        self.transport.receipts[version["outbox_id"]] = dict(
            state="confirmed", png_sha256=version["card_png_sha"], provider_guid=f"fixture-card-{job}",
            confirmed_at=self.now.isoformat())
        self.conv.flush(self.transport)

    def two_pending(self):
        """Both owners have a delivered card waiting. Returns {chat: job id}."""
        cfg_path = self.repo.state / "config.json"
        cfg = json.loads(cfg_path.read_text("utf-8"))
        cfg["settings"].update(TWO, npp=True, approvalNeedsCode=True)
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        self.conv = self.open_conv(self.repo.state, self.engine)
        self.base_head, self.base_count, self.base_site = self.repo.head(), self.commits(), self.site()
        for chat in (MCHAT, GCHAT):
            mine = LISTINGS[chat]
            self.assertEqual(self.talk(chat, f"sell ${mine['price']}", photo=mine["photo"]), "npp-working")
            self.pump(self.conv)
        rows = self.conv.db.execute("SELECT job_id, chat FROM npp_jobs").fetchall()
        self.jobs = {r["chat"]: r["job_id"] for r in rows}
        self.assertEqual(set(self.jobs), {MCHAT, GCHAT})
        self.assertEqual(len(set(self.jobs.values())), 2)
        for job in self.jobs.values():
            self.deliver(job)
        self.assertEqual((self.commits(), self.site()), (self.base_count, self.base_site))
        return dict(self.jobs)

    # ---- backup, restore -----------------------------------------------------------------------------------------------
    def restore(self, tmp):
        out = Path(tmp) / "backups"
        out.mkdir(mode=0o700)
        made = statebackup.create(self.repo.state, out)
        self.assertEqual(made["result"], "ok", made)
        backup = Path(made["backup"])
        self.assertEqual(statebackup.verify(backup)["result"], "ok")
        wt = Path(tmp) / "drill-worktree"
        git(self.repo.main, "worktree", "add", "-q", "-b", "hass/drill", str(wt), self.repo.head())
        drilled = statebackup.drill(backup, Path(tmp) / "restored", wt, media_into=Path(tmp) / "restored-media")
        self.assertEqual(drilled["result"], "ok", drilled)
        self.assertTrue(drilled["paused"], drilled)
        state = Path(drilled["state"])
        self.live = _clocked_editor(self)(state)
        return wt, state, self.open_conv(state, self.live), Path(tmp) / "restored-media"

    def commits_in(self, wt):
        return int(git(wt, "rev-list", "--count", "HEAD"))

    def catalog_in(self, wt):
        return (Path(wt) / journey.CATALOG).read_bytes()

    def names_in(self, wt):
        data = self.catalog_in(wt).split(b"\n", 1)[0][len(b"const catalog="):].rstrip(b";")
        return {p["name"]: p for p in json.loads(data)}

    # ---- the journeys ------------------------------------------------------------------------------------------------
    def test_t1_each_chat_got_only_its_own_card_and_code(self):
        jobs = self.two_pending()
        for chat, other in ((MCHAT, GCHAT), (GCHAT, MCHAT)):
            cards = [png_bytes for _text, png_bytes in self.transport.to[chat] if png_bytes is not None]
            self.assertEqual(cards, [LISTINGS[chat]["card"]])
            self.assertNotEqual(LISTINGS[chat]["card"], LISTINGS[other]["card"])
            said = " ".join(text for text, _ in self.transport.to[chat])
            self.assertIn(jobs[chat], said)
            self.assertNotIn(jobs[other], said)
        drafts = {chat: self.engine.show(self.conv.npp.version(job, 1)["change_id"])["draft"] for chat, job in jobs.items()}
        for chat, draft in drafts.items():
            (_p, digest), = draft["assets"].items()
            self.assertEqual(digest.removeprefix("sha256:"), sha(LISTINGS[chat]["photo"]))
        self.assertNotEqual(*[next(iter(d["assets"].values())) for d in drafts.values()])

    def test_t2_a_yes_with_the_other_chats_code_is_refused_before_the_restore(self):
        jobs = self.two_pending()
        for chat, other in ((MCHAT, GCHAT), (GCHAT, MCHAT)):
            for text in (f"yes {jobs[other]}-1", f"yes {jobs[other]}"):
                self.assertIn(self.talk(chat, text), REFUSED, (chat, text))
                self.assertEqual((self.commits(), self.site(), self.repo.head()), (self.base_count, self.base_site, self.base_head))
                self.assertNotIn(jobs[other], self.transport.to[chat][-1][0])  # the answer never repeats the other chat's code
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 0)

    def test_t3_restore_keeps_both_conversations_apart_and_one_yes_posts_only_its_own_listing(self):
        jobs = self.two_pending()
        source = (self.repo.head(), self.site(), self.commits())
        with tempfile.TemporaryDirectory() as tmp:
            wt, state, conv, restored_media = self.restore(tmp)
            self.conv = conv
            base = (git(wt, "rev-parse", "HEAD"), self.catalog_in(wt), self.commits_in(wt))
            # the saved conversation: each chat has exactly its own two rows, each naming its own code and its own picture
            with transcript.read(state) as db:
                rows = db.execute("SELECT chat, direction, draft_code, attachments FROM events ORDER BY id").fetchall()
            for chat, other in ((MCHAT, GCHAT), (GCHAT, MCHAT)):
                mine = [(d, code, json.loads(att)) for c, d, code, att in rows if c == chat]
                self.assertEqual(mine, [("in", jobs[chat], [sha(LISTINGS[chat]["photo"])]),
                                        ("out", f"{jobs[chat]}-1", [sha(LISTINGS[chat]["card"])])], chat)
                text = json.dumps(mine)
                self.assertNotIn(jobs[other], text)
                self.assertNotIn(sha(LISTINGS[other]["photo"]), text)
                self.assertNotIn(sha(LISTINGS[other]["card"]), text)
            self.assertEqual(len(rows), 4)
            # both owners' photo originals came along in the restored media
            files = {sha(p.read_bytes()) for p in restored_media.rglob("*") if p.is_file()}
            for chat in (MCHAT, GCHAT):
                self.assertIn(sha(LISTINGS[chat]["photo"]), files)
            self.assertEqual(self.talk(MCHAT, "resume changes"), "resume")
            for chat, other in ((MCHAT, GCHAT), (GCHAT, MCHAT)):  # a wrong-chat code after the restore: refused, nothing posts
                for text in (f"yes {jobs[other]}-1", f"yes {jobs[other]}"):
                    heard = len(self.transport.to[chat])
                    self.assertIn(self.talk(chat, text), REFUSED, (chat, text))
                    answers = self.transport.to[chat][heard:]
                    self.assertTrue(answers, (chat, text))  # the chat is answered, not ignored
                    self.assertFalse([a for a, _ in answers if jobs[other] in a], (chat, text))  # and the answer never repeats the other code
                    self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 0, (chat, text))
            self.assertEqual((git(wt, "rev-parse", "HEAD"), self.catalog_in(wt), self.commits_in(wt)), base)
            # Mike's own yes posts Mike's listing, once, with Mike's price and Mike's photo
            self.assertEqual(self.talk(MCHAT, f"yes {jobs[MCHAT]}-1"), "approved")
            self.assertEqual(self.commits_in(wt), base[2] + 1)
            names = self.names_in(wt)
            mine, theirs = LISTINGS[MCHAT], LISTINGS[GCHAT]
            self.assertIn(mine["name"], names)
            self.assertNotIn(theirs["name"], names)
            card = names[mine["name"]]
            self.assertEqual((card["sellingPrice"], card["imageAlt"]), (mine["price"], mine["alt"]))
            self.assertEqual(sha((Path(wt) / "storefront-mockup" / card["image"]).read_bytes()), sha(mine["photo"]))
            self.assertEqual(self.talk(MCHAT, f"yes {jobs[MCHAT]}-1"), "no-target")  # a repeat posts nothing more
            self.assertEqual(self.commits_in(wt), base[2] + 1)
            self.assertEqual(git(wt, "status", "--porcelain"), "")
            after_first = (git(wt, "rev-parse", "HEAD"), self.catalog_in(wt))
            # G's card was made before Mike's listing went in, so it is now stale: the yes is answered, nothing is saved,
            # and G is told to send the photo again. It never posts a mix and never posts Mike's listing again.
            self.talk(GCHAT, f"yes {jobs[GCHAT]}-1")
            self.assertIn("Nothing changed", self.transport.to[GCHAT][-1][0])
            self.assertEqual((git(wt, "rev-parse", "HEAD"), self.catalog_in(wt)), after_first)
            self.assertNotIn(theirs["name"], self.names_in(wt))
            self.assertEqual(self.conv.db.execute("SELECT state FROM npp_jobs WHERE job_id=?", (jobs[GCHAT],)).fetchone()[0],
                             "publish_failed")
            # the recovery: G sends the photo again, gets a fresh card with a NEW code, and one yes posts G's own listing
            self.assertEqual(self.talk(GCHAT, f"sell ${theirs['price']}", photo=theirs["photo"]), "npp-working")
            self.pump(self.conv)
            fresh = self.conv.db.execute("SELECT job_id FROM npp_jobs WHERE chat=? AND state!='publish_failed'", (GCHAT,)).fetchone()[0]
            self.assertNotIn(fresh, (jobs[GCHAT], jobs[MCHAT]))
            self.deliver(fresh)
            self.assertEqual(self.talk(GCHAT, f"yes {jobs[GCHAT]}-1"), "no-target")  # the old code stays dead
            self.assertEqual(self.commits_in(wt), base[2] + 1)
            self.assertEqual(self.talk(MCHAT, f"yes {fresh}-1") in REFUSED, True)  # and Mike cannot use G's new code
            self.assertEqual(self.commits_in(wt), base[2] + 1)
            self.assertEqual(self.talk(GCHAT, f"yes {fresh}-1"), "approved")
            self.assertEqual(self.commits_in(wt), base[2] + 2)
            names = self.names_in(wt)
            card = names[theirs["name"]]
            self.assertEqual((card["sellingPrice"], card["imageAlt"]), (theirs["price"], theirs["alt"]))
            self.assertEqual(sha((Path(wt) / "storefront-mockup" / card["image"]).read_bytes()), sha(theirs["photo"]))
            self.assertEqual(names[mine["name"]]["sellingPrice"], mine["price"])  # Mike's listing is as it was
            self.assertNotEqual(card["image"], names[mine["name"]]["image"])
            self.assertEqual(git(wt, "status", "--porcelain"), "")
        self.assertEqual((self.repo.head(), self.site(), self.commits()), source)  # the source install never moved
        self.assertEqual(sum(1 for p in self.repo.catalog() if p["name"] in {v["name"] for v in LISTINGS.values()}), 0)

    def test_t4_a_damaged_backup_restores_neither_conversation(self):
        self.two_pending()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "backups"
            out.mkdir(mode=0o700)
            made = statebackup.create(self.repo.state, out)
            backup = Path(made["backup"])
            victim = backup / "config.json"
            victim.write_bytes(victim.read_bytes() + b" ")
            self.assertNotEqual(statebackup.verify(backup)["result"], "ok")
            wt = Path(tmp) / "drill-worktree"
            git(self.repo.main, "worktree", "add", "-q", "-b", "hass/drill", str(wt), self.repo.head())
            drilled = statebackup.drill(backup, Path(tmp) / "restored", wt, media_into=Path(tmp) / "restored-media")
            self.assertNotEqual(drilled["result"], "ok", drilled)
            self.assertFalse((Path(tmp) / "restored").exists())
            self.assertFalse((Path(tmp) / "restored-media").exists())


# Run only this module's own journeys, not the inherited HRM-04 ones (those have their own module).
for _name in dir(journey.NppUndoJourneyTests):
    if _name.startswith("test_c"):
        setattr(TwoChatRestoreTests, _name, None)


if __name__ == "__main__":
    unittest.main()
