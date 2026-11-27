"""AV1922-02 tests: after the first recorded full shelf check a product word carries its own Pacific day.

The full-check line never moves for a word-only change; the card shows the word while its own day is not before the last full
check and at most STALE_AFTER_DAYS old (Python, browser, report all read one rule); before the first check it is refused.
Run: python3 -B -m unittest hass.tests.test_availability_own_day -v
"""

import copy
import unittest
from datetime import date, datetime, timedelta, timezone

from hass import morning_report, sitegen
from hass.content_model import validate_products
from hass.tests.test_browser_freshness import browser_words
from hass.tests.test_catalog_ops import CatalogTestCase
from hass.tests.test_selection_checked import DatedRepo
from hass.tests import test_skills_reports as report_cases

CHECK, SET, ALL = "store.confirm_selection", "product.set_availability", "product.set_availability_all"
MON = date(2026, 11, 2)  # the full shelf check
NOTE = "Sold out from today (your last full shelf check was Monday, November 2)"


class OwnDayTests(CatalogTestCase):
    def setUp(self):
        self.r = DatedRepo()
        self.addCleanup(self.r.cleanup)
        active = [p for p in self.r.products() if p["status"] == "active"]
        self.a, self.b, self.c = (p["id"] for p in active[:3])
        self.at(MON)

    def at(self, day: date) -> None:
        self.r.now = datetime(day.year, day.month, day.day, 20, tzinfo=timezone.utc)  # midday Pacific

    def product(self, pid):
        return next(p for p in self.r.products() if p["id"] == pid)

    def words(self, day):
        return browser_words(sitegen.render(self.r.content(), today=day), day, (self.a, self.b, self.c))

    def labels(self, day):  # the Python card words for the same products
        store = self.r.store()
        return {pid: sitegen.availability_label(self.product(pid), store, day) for pid in (self.a, self.b, self.c)}

    def facts(self, day):
        return morning_report.facts(self.r.content(), day)

    def test_midweek_single_word_stamps_own_day_only(self):
        self.assertIn("check the selection first", self.assertRejected(self.r, "refused", (SET, {"id": self.a, "available": "no"}))["reason"])  # no check ever
        self.r.run((CHECK, {"yes": [self.a]}))
        wed = MON + timedelta(days=2)
        self.at(wed)
        store = self.r.store()
        done = self.r.run((SET, {"id": self.a, "available": "no"}))
        self.assertIn(NOTE, done["warnings"])
        self.assertEqual((self.product(self.a)["available"], self.product(self.a)["available_on"]), ("no", wed.isoformat()))
        self.assertEqual(self.r.store(), store)  # the full-check day and every other store byte are unchanged
        self.assertEqual(self.words(wed)[self.a], "Sold out")
        self.assertEqual(self.labels(wed)[self.a], "Sold out")
        facts = self.facts(wed)
        self.assertEqual((facts["checked_on"], facts["sold_out"], facts["sold_out_names"]), (MON.isoformat(), 1, [self.product(self.a)["name"]]))
        self.assertEqual(sitegen.checked_line(self.r.store(), wed), "Selection last checked by Michael on Monday, November 2.")
        self.assertIn("nothing to change", self.assertRejected(self.r, "refused", (SET, {"id": self.a, "available": "no"}))["reason"])  # equal word: not a recheck

    def test_bulk_stamps_changed_only_with_the_same_note(self):
        self.r.run((CHECK, {}))
        wed = MON + timedelta(days=2)
        self.at(wed)
        before = {p["id"]: p for p in self.r.products()}
        done = self.r.run((ALL, {"available": "no", "shelf": "vegetables"}))
        changed = {r["key"] for r in done["records"]}
        self.assertIn(NOTE, done["warnings"])
        self.assertEqual(done["warnings"].count(NOTE), 1)
        for p in self.r.products():
            if p["id"] in changed:
                self.assertEqual((p["available"], p["available_on"]), ("no", wed.isoformat()))
            else:
                self.assertEqual(p, before[p["id"]])
        self.assertEqual(self.r.store()["selection_checked_on"], MON.isoformat())

    def test_newer_full_check_that_does_not_name_it_and_eight_days_later(self):
        self.r.run((CHECK, {"yes": [self.b]}))
        wed = MON + timedelta(days=2)
        self.at(wed)
        self.r.run((SET, {"id": self.a, "available": "no"}))
        thu = MON + timedelta(days=3)
        self.at(thu)
        self.r.run((CHECK, {"limited": [self.b]}))  # a newer full check that does not name a
        wed_text = f"Last confirmed {sitegen._day_text(wed)}"
        self.assertEqual(self.words(thu)[self.a], wed_text)
        self.assertEqual(self.labels(thu)[self.a], wed_text)
        self.assertEqual(self.facts(thu)["sold_out"], 0)
        later = wed + timedelta(days=8)  # the old word, 8 days on, is no longer current
        self.assertEqual(self.words(later)[self.a], wed_text)
        # a word set the day after that full check, then 7 and 8 days later
        own = thu + timedelta(days=1)
        self.at(own)
        self.r.run((SET, {"id": self.a, "available": "limited"}))
        for age, word, counted in ((0, "Limited", 1), (7, "Limited", 1), (8, f"Last confirmed {sitegen._day_text(own)}", 0)):
            day = own + timedelta(days=age)
            with self.subTest(age=age):
                self.assertEqual(self.words(day)[self.a], word)
                self.assertEqual(self.labels(day)[self.a], word)
                self.assertEqual(self.facts(day)["limited_names"].count(self.product(self.a)["name"]), counted)

    def test_named_report_uses_word_day_not_full_check_day(self):
        own = MON + timedelta(days=2)
        content = report_cases.content([report_cases.prod("eggs", "no", on=own.isoformat())], checked=MON.isoformat())
        for age, word in ((0, "sold out"), (7, "sold out"), (8, "not confirmed")):
            day = own + timedelta(days=age)
            with self.subTest(age=age):
                answer = report_cases.PLAIN(report_cases.said(content, "how many eggs do we have", today=day))
                self.assertEqual(answer.split("\n")[0], report_cases.NO_COUNTS + "eggs: " + word)

    def test_validation_accepts_own_day_after_check_but_never_future(self):
        self.r.run((CHECK, {}))
        content = copy.deepcopy(self.r.content())
        product = next(p for p in content.products if p["id"] == self.a)
        today = date(2026, 11, 20)
        for on, ok in (("2026-11-01", True), (MON.isoformat(), True), ("2026-11-19", True), (today.isoformat(), True), ("2026-11-21", False)):
            problems = []
            product.update(available="no", available_on=on)
            validate_products(problems, content.products, content.makers, None, MON, today)
            with self.subTest(on=on):
                self.assertEqual(problems == [], ok, problems)
                if not ok:
                    self.assertEqual(problems, [f"product {self.a}.available_on: {on} is in the future"])
        problems = []
        validate_products(problems, content.products, content.makers, None, None, today)  # a dated word, no first check
        self.assertEqual(problems, [f"product {self.a}.available_on: 2026-11-21 needs a recorded store.selection_checked_on"])


if __name__ == "__main__":
    unittest.main()
