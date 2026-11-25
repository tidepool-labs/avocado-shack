"""Finish-line proof for the Hass live listing path, offline and on fixtures only.

One owner photo becomes a card; one coded yes puts exactly that card on the public site; one coded yes takes it down;
the whole conversation stays in the private local transcript (never in the site repo); and the state backup carries that
transcript through a verify and a restore drill. Reuses the HRM-04 undo-journey harness (real chat, NPP job, editor,
local writer and transcript). No network, no Clover, no live site.
"""

import hashlib
import json
import os
import re
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
COLUMNS = "direction, kind, disposition, draft_code, text, attachments"


def leaks(history, text):
    """True if a conversation message is in the release text: a long one anywhere, a short one as a whole line or JSON value."""
    if len(text) >= 20:
        return text in history
    return json.dumps(text) in history or any(line[1:].strip() == text for line in history.splitlines())


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

    def transcript(self, path=None):
        path = path or self.repo.state / "transcript.sqlite3"
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            return db.execute(f"SELECT {COLUMNS} FROM events ORDER BY id").fetchall()

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
        photo = "storefront-mockup/" + public["image"]
        expected = {"hass/content/makers.json", "hass/content/products.json", journey.CATALOG, journey.PRODUCERS,
                    "storefront-mockup/producers.js", photo}
        self.assertEqual(set(self.repo.committed()), expected)
        # No chat or sender id reaches anything the release wrote (a bool, so a failure never prints the diff).
        patch = git(self.repo.wt, "show", "--format=", "HEAD", "--", *sorted(expected - {photo}))
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
        inbound = [r for r in rows if r[0] == "in"]
        outbound = [r for r in rows if r[0] == "out"]
        self.assertEqual([r[2] for r in inbound], ["npp-working", "approved", "proposed", "approved"])
        self.assertEqual(inbound[0][4], f"sell ${journey.PRICE}")
        self.assertTrue(inbound[1][4].startswith("yes "))
        self.assertEqual(inbound[2][4], "undo")
        self.assertEqual(inbound[3][4], f"yes {self.hide_code}")
        # Every reply Hass sent is on file, matched one by one to what the fake transport independently captured:
        # the card (text + picture) and each preview (text + picture), with the picture's own SHA-256.
        sent = [(text, hashlib.sha256(png).hexdigest()) for text, png, _digest in self.transport.cards.values()]
        sent += [(text, hashlib.sha256(pic).hexdigest()) for text, pics in self.transport.previews for pic in pics]
        self.assertEqual(len(sent), 4)
        self.assertFalse(self.transport.texts)  # nothing went out by a path the transcript might miss
        self.assertEqual(sorted((r[4], tuple(json.loads(r[5]))) for r in outbound), sorted((t, (d,)) for t, d in sent))
        self.assertEqual(len(rows), len(inbound) + len(outbound))
        path = self.repo.state / "transcript.sqlite3"
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:  # the ids the git checks below look for are really here
            self.assertEqual(db.execute("SELECT DISTINCT chat, sender FROM events WHERE direction='in'").fetchall(), [(CHAT, OWNER)])
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertNotIn(self.repo.wt.resolve(), path.resolve().parents)
        self.assertFalse([t for t in git(self.repo.wt, "ls-files").splitlines() if t.endswith(".sqlite3")])
        # Nothing the two approvals committed (messages and diffs) carries any conversation message, either approval
        # code as a token, or a "yes <code>" phrase. Booleans only, so a failure never prints private text.
        history = git(self.repo.wt, "log", "-p", "--format=%B", f"{self.base_head}..HEAD")
        for direction, kind, _disposition, _code, text, _attachments in rows:
            self.assertFalse(leaks(history, text), f"a {direction} {kind} message is in a release commit")
        for code in (self.publish_code, self.hide_code):
            self.assertFalse(re.search(rf"(?<![0-9A-Za-z-]){re.escape(code)}(?![0-9A-Za-z])", history), "approval code in a release commit")
            self.assertFalse(f"yes {code}" in history)
        for secret in (CHAT, OWNER, "transcript.sqlite3"):
            self.assertFalse(secret in history, "private text in a release commit")
        # The leak check can fail: a message put into the release text is found.
        self.assertTrue(leaks(history + "\n+undo\n", "undo") and leaks(history + f"\n {inbound[0][4]}", inbound[0][4]))

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
            self.assertEqual(self.transcript(Path(drilled["state"]) / "transcript.sqlite3"), before)


# Run only this module's own journeys, not the inherited HRM-04 ones (those have their own module).
for _name in dir(journey.NppUndoJourneyTests):
    if _name.startswith("test_c"):
        setattr(ListingFinishJourneyTests, _name, None)


if __name__ == "__main__":
    unittest.main()
