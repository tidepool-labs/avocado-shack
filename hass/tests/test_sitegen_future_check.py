"""AV1124C-05: the catalog's no-JS "last checked" paragraph never states a check that has not happened yet.

Run: python3 -B -m unittest hass.tests.test_sitegen_future_check -v
Synthetic stores and a fixed build day only.
"""

import unittest
from datetime import date, timedelta

from hass import sitegen

TODAY = date(2026, 11, 24)
PHONE = "8055550123"  # fictional 555-01xx number, stored as ten digits
OPEN = '<p class="catalog-note selection-checked" data-checked-on="{iso}"{phone}>'


def _store(day, phone=False):
    store = {"selection_checked_on": day.isoformat()}
    if phone:
        store["phone"] = PHONE
    return store


def _html(day, sentence, phone=False):
    attr = f' data-phone="{PHONE}"' if phone else ""
    return OPEN.format(iso=day.isoformat(), phone=attr) + sentence + "</p>"


class FutureCheckTests(unittest.TestCase):
    def test_future_check_prints_no_paragraph(self):
        # Contract: a check dated after the build day is "never a fresh check" (as availability_label and shop.js treat it).
        # Bug caught: the paragraph says Michael last checked on a day that has not come (wrong clock / hand-edited store).
        for days in (1, 11):
            for phone in (False, True):
                with self.subTest(days=days, phone=phone):
                    self.assertEqual(sitegen.checked_note(_store(TODAY + timedelta(days=days), phone), TODAY), "")

    def test_today_and_past_checks_unchanged(self):
        # Healthy control: the future guard must not touch a check on or before the build day (0, 7 and 8 days old).
        plain = {0: "Selection last checked by Michael on Tuesday, November 24.",
                 7: "Selection last checked by Michael on Tuesday, November 17.",
                 8: "Selection last checked by Michael on Monday, November 16 (more than a week ago - call or visit to confirm)."}
        phoned = {**plain, 8: "Selection last checked by Michael on Monday, November 16 "
                              "(more than a week ago - call (805) 555-0123 or visit to confirm)."}
        for phone, sentences in ((False, plain), (True, phoned)):
            for age, sentence in sentences.items():
                day = TODAY - timedelta(days=age)
                with self.subTest(age=age, phone=phone):
                    self.assertEqual(sitegen.checked_note(_store(day, phone), TODAY), _html(day, sentence, phone))

    def test_checked_line_untouched_for_future(self):
        # Scope pin: checked_line (shared with preview and chat) keeps its sentence; only checked_note is guarded here.
        self.assertEqual(sitegen.checked_line(_store(date(2026, 12, 5)), TODAY),
                         "Selection last checked by Michael on Saturday, December 5.")
        self.assertIsNone(sitegen.checked_line({}, TODAY))


if __name__ == "__main__":
    unittest.main()
