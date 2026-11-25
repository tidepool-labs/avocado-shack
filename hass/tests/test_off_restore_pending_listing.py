"""L7: a pending listing version carried through a state backup and an isolated restore (the OFF install rehearsal).

Two versions of one listing are waiting for a yes (v1, then the owner changes the price and v2 replaces it). The state is backed
up with its photo originals, restored into a NEW directory with a NEW worktree (restore pauses it), and a fresh chat is started on
the restored copy, as after a restart. Nothing may post by itself; while paused a yes saves nothing; after `resume changes` the
old version's yes fails and exactly one yes for the current version posts, once, with the current price and the approved photo.
The source install is never touched. Fixtures only: throwaway repos, no network, no service, no live site.
"""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from hass import conversation, statebackup
from hass.npp import reply
from hass.npp.job import Card, Plan
from hass.skills.testkit import _clocked_editor
from hass.tests import test_npp_edits as edits_tests
from hass.tests import test_npp_undo_journey as journey
from hass.tests.test_editor import git

V2_PRICE = "13.50"


def sha(data):
    return hashlib.sha256(data).hexdigest()


class OffRestorePendingListingTests(journey.NppUndoJourneyTests):
    # ---- the source install: a listing with two pending versions -------------------------------------------------------
    def stages(self):
        return reply.Stages(edits_tests.PINNED, start=self.start_stage, render=self.render_stage)

    def start_stage(self, work):
        price = work.request["slots"]["intake"].get("price")
        if price is None:
            return Plan(questions=(("ask_price", edits_tests.REPLIES["questions"]["ask_price"]),), identified=True)
        return Plan(listing={"name": journey.NAME, "sellingPrice": price})

    def render_stage(self, work, listing):
        ops = [{"op": "maker.add", "args": journey.MAKER},
               {"op": "product.add", "args": {
                   "name": journey.NAME, "brand": journey.MAKER["name"], "producerKey": journey.MAKER["key"],
                   "category": "pantry", "description": "Quince jelly.", "sellingPrice": listing["sellingPrice"],
                   "photo": work.request["attachments"][0], "imageAlt": journey.ALT}}]
        out = self.engine.prepare(ops)
        assert out["result"] == "ok", out
        path, digest = next(iter(out["draft"]["assets"].items()))
        return Card(out["draft"], journey.PNG, "raw", path, digest.removeprefix("sha256:"), "picture: your own photo")

    def open_conv(self, state, engine):
        conv = conversation.Conversation(
            state, engine, conversation.FixtureInterpreter({}), self._clock, self.previewer, photos=self,
            npp_stages=self.stages(), npp_executor=self.scheduler, npp_receipt_for=self.transport.receipt_for)
        self.addCleanup(conv.db.close)
        return conv

    def pump(self, conv):
        for _ in range(8):
            conv.flush(self.transport)
            if self.scheduler.steps:
                self.scheduler.run()
        self.assertFalse(self.scheduler.steps)

    def confirm(self, n):
        version = self.conv.npp.version(self.job, n)
        self.assertEqual(version["state"], "queued", self.transport.texts)
        self.transport.receipts[version["outbox_id"]] = dict(
            state="confirmed", png_sha256=version["card_png_sha"], provider_guid=f"fixture-card-{n}",
            confirmed_at=self.now.isoformat())
        self.conv.flush(self.transport)
        return version

    def pending_listing(self):
        """Two confirmed versions waiting for a yes in the source install; returns their (approved) prices and photo digest."""
        cfg_path = self.repo.state / "config.json"
        cfg = json.loads(cfg_path.read_text("utf-8"))
        cfg["settings"].update(journey.SETTINGS, npp=True, approvalNeedsCode=True)
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        self.conv = self.open_conv(self.repo.state, self.engine)
        self.base_head, self.base_count, self.base_site = self.repo.head(), self.commits(), self.site()
        self.assertEqual(self.say(f"sell ${journey.PRICE}", photos=1), "npp-working")
        self.pump(self.conv)
        self.job = self.conv.db.execute("SELECT job_id FROM npp_jobs").fetchone()[0]
        self.confirm(1)
        self.assertEqual(self.say(f"make it ${V2_PRICE}"), "npp-working")
        self.pump(self.conv)
        v1, v2 = self.conv.npp.version(self.job, 1), self.confirm(2) and self.conv.npp.version(self.job, 2)
        prices = [json.loads(v["listing_json"])["sellingPrice"] for v in (v1, v2)]
        self.assertNotEqual(*prices)
        draft = self.engine.show(v2["change_id"])["draft"]
        (_path, digest), = draft["assets"].items()
        self.assertEqual((self.commits(), self.site()), (self.base_count, self.base_site))
        return prices, digest.removeprefix("sha256:")

    # ---- backup, restore, restart ----------------------------------------------------------------------------------------
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
        self.assertNotIn("nppOff", drilled)  # the media came along, so both open versions can still be answered
        state = Path(drilled["state"])
        engine = _clocked_editor(self)(state)
        return backup, wt, state, self.open_conv(state, engine)

    def commits_in(self, wt):
        return int(git(wt, "rev-list", "--count", "HEAD"))

    def catalog_in(self, wt):
        return (Path(wt) / journey.CATALOG).read_bytes()

    def test_r1_restart_posts_nothing_and_a_paused_yes_saves_nothing(self):
        prices, _photo = self.pending_listing()
        source = (self.repo.head(), self.site(), self.commits())
        with tempfile.TemporaryDirectory() as tmp:
            _backup, wt, _state, conv = self.restore(tmp)
            head, catalog, count = git(wt, "rev-parse", "HEAD"), self.catalog_in(wt), self.commits_in(wt)
            self.assertEqual(catalog, self.base_site[0])
            for _ in range(3):  # the restart: the chat keeps flushing; nothing is posted by itself
                self.pump(conv)
            self.assertEqual((git(wt, "rev-parse", "HEAD"), self.catalog_in(wt), self.commits_in(wt)), (head, catalog, count))
            self.conv = conv
            self.assertEqual(self.say(f"yes {self.job}-2"), "no-target")  # restore pauses: the yes is answered, not saved
            self.assertIn("Changes are paused, so nothing will be saved yet.", self.transport.texts[-1])
            self.assertEqual((git(wt, "rev-parse", "HEAD"), self.catalog_in(wt)), (head, catalog))
            self.assertEqual(git(wt, "status", "--porcelain"), "")
        self.assertEqual((self.repo.head(), self.site(), self.commits()), source)  # the source install never moved
        self.assertEqual(len(prices), 2)

    def test_r2_stale_yes_fails_and_one_current_yes_posts_once(self):
        (old, new), photo = self.pending_listing()
        source = (self.repo.head(), self.site(), self.commits())
        with tempfile.TemporaryDirectory() as tmp:
            _backup, wt, _state, conv = self.restore(tmp)
            count, catalog = self.commits_in(wt), self.catalog_in(wt)
            self.conv = conv
            self.assertEqual(self.say("resume changes"), "resume")
            for stale in (f"yes {self.job}-1", f"yes {self.job}", "yes"):  # an old version's code, a bare job code, a bare yes
                self.assertEqual(self.say(stale), "no-target", stale)
                self.assertEqual((self.commits_in(wt), self.catalog_in(wt)), (count, catalog), stale)
            self.assertEqual(self.say(f"yes {self.job}-2"), "approved")
            self.assertEqual(self.commits_in(wt), count + 1)
            records = json.loads(self.catalog_in(wt).split(b"\n", 1)[0][len(b"const catalog="):].rstrip(b";"))
            card, = [p for p in records if p["name"] == journey.NAME]
            self.assertEqual((card["sellingPrice"], card["imageAlt"]), (new, journey.ALT))
            self.assertNotEqual(card["sellingPrice"], old)
            self.assertEqual(sha((Path(wt) / "storefront-mockup" / card["image"]).read_bytes()), photo)  # the approved photo
            for again in (f"yes {self.job}-2", f"yes {self.job}-1", "yes"):  # a repeat posts nothing more
                self.assertEqual(self.say(again), "no-target", again)
                self.assertEqual(self.commits_in(wt), count + 1, again)
            self.assertEqual(git(wt, "status", "--porcelain"), "")
        self.assertEqual((self.repo.head(), self.site(), self.commits()), source)  # the source never saw the drill's yes
        self.assertEqual(sum(1 for p in self.repo.catalog() if p["name"] == journey.NAME), 0)

    def test_r3_a_damaged_backup_is_refused_and_restores_nothing(self):
        self.pending_listing()
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
            out = statebackup.drill(backup, Path(tmp) / "restored", wt, media_into=Path(tmp) / "restored-media")
            self.assertNotEqual(out["result"], "ok", out)
            self.assertFalse((Path(tmp) / "restored").exists())
            self.assertFalse((Path(tmp) / "restored-media").exists())


# Run only this module's own journeys, not the inherited HRM-04 ones (those have their own module).
for _name in dir(journey.NppUndoJourneyTests):
    if _name.startswith("test_c"):
        setattr(OffRestorePendingListingTests, _name, None)


if __name__ == "__main__":
    unittest.main()
