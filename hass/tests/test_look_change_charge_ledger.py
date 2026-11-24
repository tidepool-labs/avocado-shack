"""AV1124C-09: pin look_change.charge(), the daily website-look draft ledger (HASS-SITE-LOOK-1: at most DAILY drafts per
Pacific day, counted before any model call). Calls charge() directly on a temporary ledger file with synthetic days: no
model, git, network or live site. The cap is read from look_change.DAILY, never restated or changed here."""
import json
import tempfile
import unittest
from pathlib import Path

from hass import look_change

DAY, NEXT_DAY = "2026-11-24", "2026-11-25"


class ChargeLedgerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ledger = Path(tmp.name, "ledger.json")

    def stored(self):
        return json.loads(self.ledger.read_text("utf-8"))

    def refused(self, today):
        with self.assertRaises(look_change.Refused) as caught:
            look_change.charge(self.ledger, today)
        return str(caught.exception)

    # Contract: a day's drafts are capped at DAILY and a refusal never counts. Fails if the cap is loosened (>= to >),
    # or if a refused call still writes the ledger.
    def test_fourth_charge_in_a_day_refused_and_ledger_unchanged(self):
        for _ in range(look_change.DAILY):  # healthy control: every charge up to the cap succeeds
            self.assertIsNone(look_change.charge(self.ledger, DAY))
        self.assertEqual(self.stored(), [DAY] * look_change.DAILY)
        before = self.ledger.read_bytes()
        for _ in range(2):  # the refusal repeats and never changes the file
            self.assertEqual(self.refused(DAY), "cap")
            self.assertEqual(self.ledger.read_bytes(), before)
        self.assertFalse(self.ledger.with_name("ledger.json.tmp").exists())

    # Contract: only today's entries count; older days are dropped on the next charge. Fails if old entries are kept
    # (a full yesterday would then block today) or if the new day is not recorded.
    def test_new_day_drops_old_entries(self):
        self.ledger.write_text(json.dumps([DAY] * look_change.DAILY), "utf-8")
        self.assertEqual(self.refused(DAY), "cap")  # control: the old day really is full
        self.assertIsNone(look_change.charge(self.ledger, NEXT_DAY))
        self.assertEqual(self.stored(), [NEXT_DAY])

    # Contract: a ledger that cannot be trusted refuses (fail closed) rather than restarting the count. Fails if an
    # unparseable or non-list ledger is treated as empty.
    def test_unreadable_or_non_list_ledger_refuses(self):
        for raw in (b'{"days": []}', b'"2026-11-24"', b"7", b"null", b"[1, 2", b"", b"not json", b"\xff\xfe\x00"):
            with self.subTest(raw=raw):
                self.ledger.write_bytes(raw)
                self.assertEqual(self.refused(DAY), "cap")
                self.assertEqual(self.ledger.read_bytes(), raw)

    # Contract: entries that are not today's string never count and are not carried forward. Fails if junk is kept
    # (it would eat the cap or be written back) or if it makes charge() crash.
    def test_junk_entries_are_dropped(self):
        self.ledger.write_text(json.dumps([1, None, NEXT_DAY, {"d": NEXT_DAY}, [NEXT_DAY], "x", DAY]), "utf-8")
        self.assertIsNone(look_change.charge(self.ledger, NEXT_DAY))
        self.assertEqual(self.stored(), [NEXT_DAY, NEXT_DAY])

    # Contract: no ledger yet is an empty count, and what is written is a JSON list of strings. Fails if a missing file
    # refuses, or if the file is written in another shape.
    def test_missing_ledger_starts_empty(self):
        self.assertFalse(self.ledger.exists())
        self.assertIsNone(look_change.charge(self.ledger, DAY))
        self.assertEqual(self.stored(), [DAY])
        look_change.charge(self.ledger, DAY)
        written = self.stored()
        self.assertIsInstance(written, list)
        self.assertTrue(all(isinstance(d, str) for d in written))


if __name__ == "__main__":
    unittest.main()
