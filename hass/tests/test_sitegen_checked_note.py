"""AV1124C-12: pin the no-JS "selection last checked" paragraph that sitegen.checked_note writes.

Contract: the exact HTML at the fresh, 7-day (still fresh) and 8-day (stale) boundaries, the fixed English day names,
data-phone only when a phone is stored, and the empty string for no or impossible check dates. Pure calls with synthetic
stores. The future-date case is deliberately not asserted here (AV1124C-05 owns it).
Run: python3 -B -m unittest hass.tests.test_sitegen_checked_note -v
"""

import unittest
from datetime import date

from hass import sitegen

TODAY = date(2026, 11, 24)  # a Tuesday
PHONE = "8055550123"
STALE_TAIL = " (more than a week ago - call or visit to confirm)"
STALE_PHONE_TAIL = " (more than a week ago - call (805) 555-0123 or visit to confirm)"


def note(checked, phone=None) -> str:
    store = {} if checked is None else {"selection_checked_on": checked}
    if phone:
        store["phone"] = phone
    return sitegen.checked_note(store, TODAY)


def para(checked, sentence, phone=None) -> str:
    attrs = f' data-checked-on="{checked}"' + (f' data-phone="{phone}"' if phone else "")
    return f'<p class="catalog-note selection-checked"{attrs}>{sentence}</p>'


class CheckedNoteTests(unittest.TestCase):
    def test_fresh_note_exact(self):
        # Protects the no-JS fallback markup and the fixed day names; fails if an attribute, class or weekday drifts.
        self.assertEqual(note("2026-11-22", PHONE),
                         '<p class="catalog-note selection-checked" data-checked-on="2026-11-22" '
                         'data-phone="8055550123">Selection last checked by Michael on Sunday, November 22.</p>')
        self.assertEqual(note("2026-11-24"),  # checked today: still plain, no phone attribute
                         para("2026-11-24", "Selection last checked by Michael on Tuesday, November 24."))

    def test_seven_days_is_fresh_eight_is_stale(self):
        # Protects STALE_AFTER_DAYS = 7 (stale only when strictly older); fails on an off-by-one in the comparison.
        self.assertEqual(note("2026-11-17"), para("2026-11-17", "Selection last checked by Michael on Tuesday, November 17."))
        self.assertEqual(note("2026-11-16"),
                         para("2026-11-16", "Selection last checked by Michael on Monday, November 16" + STALE_TAIL + "."))

    def test_stale_note_with_and_without_phone(self):
        # Protects the phone in the stale tail and data-phone only when a phone is stored.
        stale = "Selection last checked by Michael on Sunday, November 1"
        with_phone = note("2026-11-01", PHONE)
        self.assertEqual(with_phone, para("2026-11-01", stale + STALE_PHONE_TAIL + ".", PHONE))
        self.assertIn(' data-phone="8055550123"', with_phone)
        without = note("2026-11-01")
        self.assertEqual(without, para("2026-11-01", stale + STALE_TAIL + "."))
        self.assertNotIn("data-phone", without)
        self.assertNotIn("data-phone", note("2026-11-01", ""))  # an empty stored phone is no phone

    def test_no_or_impossible_check_is_empty(self):
        # Protects "say nothing before the first real check": no date and a non-calendar date give '' (healthy control:
        # the same store shape with a real date above gives a paragraph).
        self.assertEqual(note(None, PHONE), "")
        self.assertEqual(note("2026-02-30", PHONE), "")
        self.assertNotEqual(note("2026-11-22", PHONE), "")


if __name__ == "__main__":
    unittest.main()
