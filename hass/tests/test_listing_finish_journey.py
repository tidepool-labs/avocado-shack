"""Finish-line proof for the Hass live listing path, offline and on fixtures only.

One owner photo becomes a card; one coded yes puts exactly that card on the public site; one coded yes takes it down;
the whole conversation stays in the private local transcript (never in the site repo); and the state backup carries that
transcript through a verify and a restore drill. Reuses the HRM-04 undo-journey harness (real chat, NPP job, editor,
local writer and transcript). No network, no Clover, no live site.
"""

import json
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

from hass import statebackup
from hass.tests import test_npp_undo_journey as journey
from hass.tests.test_conversation import CHAT, OWNER
from hass.tests.test_editor import git

# The only keys a public Market record may carry for a photo listing (checked against the real writer's output).
PUBLIC_KEYS = {"id", "name", "brand", "category", "image", "description", "producerKey", "displayBrand",
               "imageAlt", "sellingPrice", "addedOn"}
PRIVATE_WORDS = ("cost", "qty", "quantity", "stock", "count", "margin", "wholesale", "supplier")


class ListingFinishJourneyTests(journey.NppUndoJourneyTests):
    def setUp(self):
        super().setUp()
        self.shown, show = {}, self.engine.show  # the approved draft, as the owner's card was built from it

        def spy(change_id, *args, **kw):
            out = show(change_id, *args, **kw)
            if "draft" in out:
                self.shown[change_id] = out["draft"]
            return out
        self.engine.show = spy

    def public(self):
        return next((p for p in self.repo.catalog() if p["id"] == self.pid), None)

    def transcript(self):
        path = self.repo.state / "transcript.sqlite3"
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            return db.execute("SELECT direction, kind, disposition, draft_code, text FROM events ORDER BY id").fetchall()

    def test_f1_public_listing_is_the_approved_card_and_nothing_private(self):
        self.publish()
        add = next(op["args"] for op in self.shown[self.change]["ops"] if op["op"] == "product.add")
        public = self.public()
        assert public is not None
        # Name, descriptor, public price and photo description are exactly what the approved draft carried.
        self.assertEqual((public["name"], public["description"], public["sellingPrice"], public["imageAlt"]),
                         (add["name"], add["description"], add["sellingPrice"], add["imageAlt"]))
        self.assertEqual(public["sellingPrice"], journey.PRICE)
        self.assertLessEqual(set(public), PUBLIC_KEYS)
        blob = json.dumps(public).lower()
        for word in PRIVATE_WORDS:
            self.assertNotIn(word, [k.lower() for k in public], word)
            self.assertNotIn(f'"{word}', blob, word)
        # The release commit touches only the content records, their generated site files and this item's own photo.
        expected = {"hass/content/makers.json", "hass/content/products.json", journey.CATALOG, journey.PRODUCERS,
                    "storefront-mockup/producers.js", "storefront-mockup/" + public["image"]}
        self.assertEqual(set(self.repo.committed()), expected)
        # No chat or sender id reaches anything the release wrote (a bool, so a failure never prints the diff).
        patch = git(self.repo.wt, "show", "--format=", "HEAD", "--", *sorted(expected - {"storefront-mockup/" + public["image"]}))
        for secret in (CHAT, OWNER):
            self.assertFalse(secret in patch, "private id in a release diff")

    def test_f2_one_coded_yes_takes_it_down(self):
        self.publish()
        self.assertIsNotNone(self.public())
        self.draft_hide()
        self.assertIsNotNone(self.public(), "undo alone must not remove the card")
        self.confirm_hide()
        self.assertIsNone(self.public())
        self.assertEqual(self.site(), self.base_site)

    def test_f3_conversation_recorded_locally_and_never_in_git(self):
        self.publish()
        self.draft_hide()
        self.confirm_hide()
        rows = self.transcript()
        self.assertEqual([(r[0], r[2]) for r in rows if r[0] == "in"],
                         [("in", "npp-working"), ("in", "approved"), ("in", "proposed"), ("in", "approved")])
        inbound = [r for r in rows if r[0] == "in"]
        self.assertEqual([r[4] for r in inbound][0], f"sell ${journey.PRICE}")
        self.assertTrue(inbound[1][4].startswith("yes "))
        self.assertEqual(inbound[2][4], "undo")
        self.assertEqual(inbound[3][4], f"yes {self.hide_code}")
        # Every reply Hass queued is on file too, and the card and the yes share the listing's code.
        self.assertTrue(any(r[0] == "out" and r[3] and r[3].endswith("-1") for r in rows))
        self.assertEqual(sum(r[0] == "out" for r in rows), len(rows) - 4)
        path = self.repo.state / "transcript.sqlite3"
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:  # the ids the git checks below look for are really here
            self.assertEqual(db.execute("SELECT DISTINCT chat, sender FROM events WHERE direction='in'").fetchall(), [(CHAT, OWNER)])
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        wt = self.repo.wt.resolve()
        self.assertNotIn(wt, path.resolve().parents)
        tracked = git(self.repo.wt, "ls-files").splitlines()
        self.assertFalse([t for t in tracked if t.endswith(".sqlite3")])
        history = git(self.repo.wt, "log", "-p", f"{self.base_head}..HEAD")  # what the two approvals committed
        for secret in (CHAT, OWNER, "transcript.sqlite3", "yes " + self.hide_code):
            self.assertFalse(secret in history, "private text in a release commit")

    def test_f4_backup_carries_the_transcript_through_a_restore_drill(self):
        self.publish()
        self.draft_hide()
        self.confirm_hide()
        before = self.transcript()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "backups"
            out.mkdir(mode=0o700)
            made = statebackup.create(self.repo.state, out)
            self.assertEqual(made["result"], "ok", made)
            backup = Path(made["backup"])
            self.assertTrue((backup / "transcript.sqlite3").is_file())
            self.assertEqual(stat.S_IMODE(os.stat(backup / "transcript.sqlite3").st_mode), 0o600)
            self.assertEqual(statebackup.verify(backup)["result"], "ok")
            drill_wt = Path(tmp) / "drill"
            git(self.repo.main, "worktree", "add", "-q", "-b", "hass/drill", str(drill_wt))
            drilled = statebackup.drill(backup, Path(tmp) / "restored", drill_wt, media_into=Path(tmp) / "restored-media")
            self.assertEqual(drilled["result"], "ok", drilled)
            restored = Path(drilled["state"]) / "transcript.sqlite3"
            with sqlite3.connect(f"file:{restored}?mode=ro", uri=True) as db:
                after = db.execute("SELECT direction, kind, disposition, draft_code, text FROM events ORDER BY id").fetchall()
            self.assertEqual(after, before)


# Run only this module's own journeys, not the inherited HRM-04 ones (those have their own module).
for _name in dir(journey.NppUndoJourneyTests):
    if _name.startswith("test_c"):
        setattr(ListingFinishJourneyTests, _name, None)


if __name__ == "__main__":
    unittest.main()
