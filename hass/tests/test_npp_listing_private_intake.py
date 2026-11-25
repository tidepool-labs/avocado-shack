"""HASS-INTAKE-2 on the listing path (Hass finish, case 13 contract).

The owner's cost and quantity never reach the card, but they are his: they wait privately beside the listing job and
become one labelled line of the private intake record (state/item-intake.jsonl) only when his approved card is applied.
An applied take-down marks that line undone. Runs the real Conversation, NPP job and local writer from the undo journey.
"""

import json
import os
import stat
import unittest

from hass.tests import test_npp_undo_journey as journey

CAPTION = f"Just bought 50 of these for $1. I will sell at ${journey.PRICE} each"


class _Journey(journey.NppUndoJourneyTests):
    caption = CAPTION

    def say(self, text, *, photos=0):
        if photos and text == f"sell ${journey.PRICE}":
            text = self.caption  # the same journey, with the owner's private numbers in his caption
        return super().say(text, photos=photos)

    def store(self):
        return self.repo.state / "item-intake.jsonl"

    def saved(self):
        path = self.store()
        return [json.loads(line) for line in path.read_text("utf-8").splitlines()] if path.exists() else []

    def pending(self):
        db = self.conv.db
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='intake_pending'").fetchone():
            return {}
        return {code: json.loads(rec) for code, rec in db.execute("SELECT code, record_json FROM intake_pending")}


for _name in [n for n in dir(journey.NppUndoJourneyTests) if n.startswith("test")]:
    setattr(_Journey, _name, None)  # reuse the journey's steps, not its own tests (they run in their module)

class ListingPrivateIntakeTests(_Journey):
    def test_cost_and_quantity_are_saved_privately_only_when_the_card_is_applied(self):
        self.publish()
        rows = self.saved()
        self.assertEqual(len(rows), 1, rows)
        row = rows[0]
        self.assertEqual((row["status"], row["draft"], row["product"]), ("saved", self.publish_code, self.pid))
        self.assertEqual(row["answers"], {"cost": "1.00", "qty": 50})
        self.assertTrue(row["applied_at"])
        self.assertEqual(self.pending(), {}, "the waiting record moves to the store, nothing is left behind")
        self.assertEqual(stat.S_IMODE(os.stat(self.store()).st_mode), 0o600)
        public = next(p for p in self.repo.catalog() if p["id"] == self.pid)
        self.assertEqual(public["sellingPrice"], journey.PRICE)
        self.assertNotIn("1.00", json.dumps(public))

    def test_nothing_is_saved_before_the_yes(self):
        original = self.say

        def stop_before_yes(text, *, photos=0):
            if text.startswith("yes "):
                job = self.conv.db.execute("SELECT job_id FROM npp_jobs").fetchone()[0]
                self.assertEqual(self.saved(), [])
                waiting = self.pending()
                self.assertEqual(list(waiting), ["npp:" + job])
                self.assertEqual(waiting["npp:" + job]["answers"], {"cost": "1.00", "qty": 50})
                self.assertIsNone(waiting["npp:" + job]["draft"])
            return original(text, photos=photos)

        self.say = stop_before_yes
        self.publish()
        self.assertEqual(len(self.saved()), 1)

    def test_an_applied_take_down_marks_the_record_undone(self):
        self.publish()
        self.draft_hide()
        self.assertEqual([r["status"] for r in self.saved()], ["saved"], "drafting the hide changes nothing")
        self.confirm_hide()
        rows = self.saved()
        self.assertEqual([(r["status"], r["draft"]) for r in rows],
                         [("saved", self.publish_code), ("undone", self.publish_code)])


class ListingWithoutPrivateNumbersTests(_Journey):
    caption = f"sell ${journey.PRICE}"

    def test_a_caption_without_cost_or_quantity_saves_no_record(self):
        self.publish()
        self.assertEqual(self.saved(), [])
        self.assertEqual(self.pending(), {})


class FinanceLabelTests(unittest.TestCase):
    def test_only_one_unambiguous_cost_and_count_are_labelled(self):
        from hass.npp.private_numbers import finance
        one = finance(CAPTION)
        self.assertEqual((one.cost, one.qty), ("1.00", 50))
        self.assertNotIn("1.00", repr(one))  # labelled values stay out of logs and reprs
        self.assertEqual((finance(f"sell ${journey.PRICE} each").cost, finance(f"sell ${journey.PRICE} each").qty),
                         (None, None))
        both = finance("cost $1; cost $2; sell $5 each")
        self.assertTrue(both.has_cost)
        self.assertIsNone(both.cost)  # two different costs: kept private, never guessed into a record


if __name__ == "__main__":
    unittest.main()
