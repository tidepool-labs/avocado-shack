"""HASS-NL-1 tests: the hints the shop software works out before the model reads an owner text (hass/nl_prep.py), how the
interpreter request carries them, and Conversation's `recent` question. Synthetic catalog and texts only; no model, no socket.
Run: python3 -m unittest hass.tests.test_nl_prep -v
"""

import json
import unittest
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from hass import conversation, nl_eval, nl_prep
from hass.interpreter_local import LocalInterpreter
from hass.tests.test_conversation import ConversationTestCase

MONDAY = date(2026, 11, 9)  # the corpus' fixed "today"
LAST_DAY, FIRST_DAY = date.max, date.min  # 9999-12-31 (Friday) and 0001-01-01 (Monday): the calendar's ends
URL = "http://127.0.0.1:11434"


def product(n, name, category="fruit", maker=None, status="active", description=""):
    return {"id": f"photo-product-{n:03d}", "name": name, "category": category, "producerKey": maker, "status": status,
            "description": description}


def tiny(hours=("Monday–Friday 9am–6pm", "Saturday 9am–5pm · Closed Sunday")):
    products = [product(1, "Hass avocados"), product(2, "Lemons"), product(3, "Cal Poly eggs", "eggs", "calpoly"),
                product(4, "Stepladder avocado blossom honey", "pantry", "stepladder"),
                product(5, "Big Sur Honey Company honey", "pantry", "bigsur"),
                product(6, "Rye bread", "bread", "brian"), product(7, "Cracked wheat sourdough", "bread", "brian"),
                product(8, "Cass Hill Blend", "drinks", "cass"), product(9, "Old jam", "pantry", status="hidden"),
                product(10, "Cal Poly white cheddar", "dairy", "calpoly"), product(11, "Cal Poly chipotle cheddar", "dairy", "calpoly")]
    makers = {"calpoly": {"name": "Cal Poly"}, "brian": {"name": "Brian's Bakery"}, "stepladder": {"name": "Stepladder"},
              "bigsur": {"name": "Big Sur Honey Company"}, "cass": {"name": "Cass Hill Coffee"}}
    events = [{"id": "hike-2026-11-14-point-buchon", "title": "Point Buchon walk", "startsAt": "2026-11-14T08:30:00-08:00", "status": "scheduled"},
              {"id": "hike-2026-11-22-cass-hill", "title": "Cass Hill hike", "startsAt": "2026-11-22T09:00:00-08:00", "status": "scheduled"}]
    return SimpleNamespace(products=products, makers=makers, community={"events": events, "routeIdeas": [{"id": "idea-morro", "title": "Morro Rock"}]},
                           store={"hours": list(hours)})


class HintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hint = staticmethod(nl_prep.make_hinter(tiny()))

    def ask(self, text, aliases=None, today=MONDAY):
        return self.hint(text, today, aliases)

    def test_one_match_is_a_product_and_two_are_ambiguous(self):
        self.assertEqual(self.ask("eggs are out")["products"], [{"said": "eggs", "is": {"id": "photo-product-003", "name": "Cal Poly eggs"}}])
        [row] = self.ask("honey is sold out")["products"]
        self.assertEqual([c["id"] for c in row["ambiguous"]], ["photo-product-004", "photo-product-005"])
        self.assertNotIn("is", row)
        [row] = self.ask("the cheddar is low")["products"]
        self.assertEqual(len(row["ambiguous"]), 2)

    def test_a_spelling_guess_is_marked_as_a_guess(self):
        [row] = self.ask("avacados limited today")["products"]
        self.assertEqual((row["is"]["id"], row["spelling"]), ("photo-product-001", "guessed"))
        [row] = self.ask("lemons are limited")["products"]
        self.assertNotIn("spelling", row)

    def test_an_owner_alias_names_exactly_its_record(self):
        alias = [{"name": "the good stuff", "kind": "product", "id": "photo-product-005"}]
        [row] = self.ask("the good stuff is gone", aliases=alias)["products"]
        self.assertEqual((row["is"]["id"], row["alias"]), ("photo-product-005", True))
        self.assertNotIn("products", self.ask("zzz is gone", aliases=[{"name": 5}, "junk", {"name": "x"}]))

    def test_a_shelf_lists_its_active_products_only(self):
        [shelf] = self.ask("bread is gone")["shelves"]
        self.assertEqual((shelf["shelf"], shelf["count"]), ("bread", 2))
        self.assertEqual(sorted(p["id"] for p in shelf["products"]), ["photo-product-006", "photo-product-007"])
        self.assertNotIn("photo-product-009", json.dumps(self.ask("pantry is empty")["shelves"]))  # hidden stays out

    def test_a_maker_alone_lists_its_products(self):
        [row] = self.ask("nothing from Cal Poly today")["makers"]
        self.assertEqual(row["key"], "calpoly")
        self.assertEqual(len(row["products"]), 3)

    def test_dates_are_worked_out_in_the_pacific_calendar(self):
        dates = {row["said"]: row for row in self.ask("tomorrow, the 29th, dec 5, in 2 weeks, last friday")["dates"]}
        self.assertEqual(dates["tomorrow"]["date"], "2026-11-10")
        self.assertEqual((dates["29th"]["date"], dates["29th"]["weekday"]), ("2026-11-29", "Sunday"))
        self.assertEqual(dates["dec 5"]["date"], "2026-12-05")
        self.assertEqual(dates["in 2 weeks"]["date"], "2026-11-23")
        self.assertEqual(dates["last friday"]["date"], "2026-11-06")
        [row] = self.ask("wednesday")["dates"]
        self.assertEqual((row["next"], row["last"]), ("2026-11-11", "2026-11-04"))

    def test_an_unclear_day_gives_both_readings_and_a_loose_time_gives_none(self):
        [row] = self.ask("next saturday")["dates"]
        self.assertEqual(row["unclear"], ["2026-11-14", "2026-11-21"])
        self.assertNotIn("date", row)
        [row] = self.ask("sometime next week")["dates"]
        self.assertIsNone(row["date"])
        self.assertIn("ask", row["note"])

    def test_a_past_date_rolls_to_next_year_and_a_bad_one_is_left_out(self):
        self.assertEqual(self.ask("nov 2")["dates"][0]["date"], "2027-11-02")
        self.assertNotIn("dates", self.ask("feb 30"))

    def test_an_explicit_year_is_kept_and_never_turned_into_the_next_annual_day(self):
        cases = {  # text -> (said, date) the one hint has to be
            "hike on December 5 2027 at 9am": ("december 5 2027", "2027-12-05"),
            "hike on december 5th, 2027": ("december 5th, 2027", "2027-12-05"),
            "hike on 5 december 2027": ("5 december 2027", "2027-12-05"),
            "hike on 5th of dec '27": ("5th of dec '27", "2027-12-05"),
            "hike on 12/5/2027": ("12/5/2027", "2027-12-05"),
            "hike on 12/05/27": ("12/05/27", "2027-12-05"),
            "hike on 2027-12-05": ("2027-12-05", "2027-12-05"),
            "hike on 5 Dec. 2027 at 9am": ("5 dec. 2027", "2027-12-05"),
            "hike on 5th of Dec. 2027": ("5th of dec. 2027", "2027-12-05"),
            "hike on December 5 2025": ("december 5 2025", "2025-12-05"),  # a past year is as written, not rolled forward
            "hike on nov 2 2026": ("nov 2 2026", "2026-11-02"),
        }
        for text, (said, want) in cases.items():
            [row] = self.ask(text)["dates"]
            self.assertEqual((row["said"], row["date"]), (said, want), text)
        self.assertEqual(self.ask("hike on 12/5/2027")["dates"][0]["weekday"], "Sunday")

    def test_a_year_that_cannot_be_checked_leaves_the_date_hint_out(self):
        for text in ("hike on feb 30 2027", "hike on 2/30/2027", "hike on 2027-02-30", "hike on dec 5 1999", "hike on dec 5 3027",
                     "hike on 12/5/202", "hike on 12/5/20277", "hike on 5 dec 0027", "hike on 2027/12/5", "hike on dec 5 1530",
                     "hike on feb 29 2027", "hike on December 5 202", "hike on 5 December 20277", "hike on dec 5, 202", "hike on 5th of dec 20277", "hike on 5 Dec. 202", "hike on 5 Dec. 20277",
                     "hike on dec 5 0202"):
            self.assertNotIn("dates", self.ask(text), text)
        [row] = self.ask("hike on feb 29 2028")["dates"]  # a real leap day
        self.assertEqual(row["date"], "2028-02-29")

    def test_a_time_or_a_count_after_a_date_is_not_a_year(self):
        [row] = self.ask("hike on dec 5 9am")["dates"]
        self.assertEqual((row["said"], row["date"]), ("dec 5", "2026-12-05"))
        [row] = self.ask("hike on dec 5 10:30")["dates"]
        self.assertEqual((row["said"], row["date"]), ("dec 5", "2026-12-05"))
        [row] = self.ask("hike on 12/5 at 9")["dates"]
        self.assertEqual((row["said"], row["date"]), ("12/5", "2026-12-05"))
        for text, said in (("hike on dec 5 930pm", "dec 5"), ("hike on dec 5 930 pm", "dec 5"), ("hike on 5 dec 9am", "5 dec"), ("hike on dec 5 at 930", "dec 5"),
                           ("hike on dec 5 with 2 helpers", "dec 5")):
            [row] = self.ask(text)["dates"]
            self.assertEqual((row["said"], row["date"]), (said, "2026-12-05"), text)

    def test_yearless_dates_still_roll_forward(self):
        self.assertEqual(self.ask("dec 5")["dates"][0]["date"], "2026-12-05")
        self.assertEqual(self.ask("5 dec")["dates"][0]["date"], "2026-12-05")
        self.assertEqual(self.ask("12/5")["dates"][0]["date"], "2026-12-05")
        self.assertEqual(self.ask("nov 2")["dates"][0]["date"], "2027-11-02")
        self.assertEqual(self.ask("11/2")["dates"][0]["date"], "2027-11-02")

    def test_times_and_numbers(self):
        times = {t["said"]: t["time"] for t in self.ask("8:30am, 5pm, noon and 17:45")["times"]}
        self.assertEqual(times, {"8:30am": "08:30", "5pm": "17:00", "noon": "12:00", "17:45": "17:45"})
        self.assertNotIn("times", self.ask("no time here"))
        self.assertEqual(self.ask("two dozen")["numbers"], [{"said": "two", "value": 2}, {"said": "dozen", "value": 12}])

    def test_a_price_is_only_flagged_never_used(self):
        self.assertEqual(self.ask("make the lemons $9 each")["price"], {"mentioned": True, "amounts": ["9"]})
        self.assertNotIn("price", self.ask("lemons are out"))

    def test_hikes_by_name_and_by_weekday(self):
        named = self.ask("cancel the point buchon walk")["hikes"]["named"]
        self.assertEqual(named[0]["hike"], "hike-2026-11-14-point-buchon")
        [row] = self.ask("move the walk on saturday")["hikes"]["onThatWeekday"]
        self.assertEqual(row["scheduled hikes"][0]["hike"], "hike-2026-11-14-point-buchon")
        self.assertNotIn("hikes", self.ask("change the shop hours on saturday"))  # a weekday alone is not about hikes

    def test_a_hike_name_is_not_also_the_product_of_that_name(self):
        out = self.ask("cancel the cass hill walk")
        self.assertEqual(out["hikes"]["named"][0]["hike"], "hike-2026-11-22-cass-hill")
        self.assertNotIn("products", out)
        self.assertEqual(self.ask("cass hill blend is out")["products"][0]["is"]["id"], "photo-product-008")

    def test_the_hours_the_store_already_shows_are_a_fact_not_a_draft(self):
        self.assertEqual(self.ask("can you change the shop hours to 9 to 5 on saturdays")["alreadyTrue"], ["Saturday already 9am–5pm"])
        self.assertEqual(self.ask("saturday 9am to 5pm")["alreadyTrue"], ["Saturday already 9am–5pm"])
        self.assertEqual(self.ask("wed 9-6")["alreadyTrue"], ["Wednesday already 9am–6pm"])
        for text in ("saturdays 10 to 4", "sunday 10-2", "make saturday 9 to 6", "saturday hours?", "open at 9 to 5"):
            self.assertNotIn("alreadyTrue", self.ask(text), text)
        self.assertNotIn("alreadyTrue", nl_prep.make_hinter(tiny(hours=()))("saturday 9 to 5", MONDAY))

    def test_a_two_day_hours_request_is_a_fact_only_when_every_change_is_already_true(self):
        for text in ("Saturday 9 to 5 and Sunday 10 to 2", "Sunday 10 to 2 and Saturday 9 to 5", "9 to 5 on saturday and 10 to 2 on sunday"):
            self.assertNotIn("alreadyTrue", self.ask(text), text)
        self.assertEqual(self.ask("Saturday 9 to 5 and Wednesday 9 to 6")["alreadyTrue"], ["Saturday already 9am–5pm", "Wednesday already 9am–6pm"])
        self.assertEqual(self.ask("saturday and wednesday 9 to 5").get("alreadyTrue"), None)

    def test_a_closure_or_open_ended_clause_is_never_a_no_op(self):
        for text in ("Monday 9 to 6 and Tuesday closed", "Tuesday closed and Monday 9 to 6", "Monday 9 to 6, Tuesday off", "Saturday 9 to 5 and closed Sunday", "Saturday 9 to 5 and Wednesday from 10", "Monday 9 to 6 and Tuesday opens at 10am", "Monday 9 to 6 and Tuesday moves to later"):
            self.assertNotIn("alreadyTrue", self.ask(text), text)

    def test_weekday_range_never_claims_endpoints_cover_the_interior(self):
        hours = ("Monday 9am–5pm · Tuesday 10am–4pm · Wednesday 9am–5pm · Thursday 9am–5pm · Friday 9am–5pm",)
        hint = nl_prep.make_hinter(tiny(hours=hours))
        for text in ("Monday-Friday 9 to 5", "Monday\u2013Friday 9 to 5", "Monday through Friday 9 to 5"):
            self.assertNotIn("alreadyTrue", hint(text, MONDAY), text)
            self.assertIsNone(nl_prep.hours_hints(text, nl_prep._Index(tiny(hours=hours))), text)
        self.assertEqual(hint("Monday and Friday 9 to 5", MONDAY)["alreadyTrue"], ["Monday already 9am–5pm", "Friday already 9am–5pm"])

    def test_every_weekday_range_form_omits_the_hours_hint_even_when_true(self):
        uniform = nl_prep._Index(tiny(hours=("Monday–Friday 9am–5pm",)))
        for text in ("Monday-Friday 9 to 5", "Mon - Fri 9 to 5", "Monday \u2014 Friday 9 to 5", "Monday to Friday 9 to 5", "Monday until Friday 9 to 5",
                     "Mondays-Fridays 9 to 5", "Friday-Monday 9 to 5", "Monday-Monday 9 to 5", "Monday-Wednesday and Friday 9 to 5"):
            self.assertIsNone(nl_prep.hours_hints(text, uniform), text)
        for text, want in (("Monday, Friday 9 to 5", ["Monday already 9am–5pm", "Friday already 9am–5pm"]), ("Saturday 9-5", None)):
            self.assertEqual(nl_prep.hours_hints(text, uniform), want, text)
        self.assertEqual(nl_prep.hours_hints("Monday and Friday 9 to 5", uniform), ["Monday already 9am–5pm", "Friday already 9am–5pm"])

    def test_range_omission_keeps_unrelated_hints_and_the_request(self):
        seen = []
        hours = ("Monday 9am–5pm · Tuesday 10am–4pm · Wednesday 9am–5pm",)
        interp = LocalInterpreter(URL, "m", "SYSTEM", transport=RequestTests.fake(None, seen), clock=lambda: datetime(2026, 11, 9, 17, 40, tzinfo=timezone.utc),
                                  hinter=nl_prep.make_hinter(tiny(hours=hours)))
        text = "lemons are out, Monday-Wednesday 9 to 5"
        interp.interpret(text, [])
        user = json.loads(seen[-1]["messages"][1]["content"])
        self.assertEqual(user["message"], text)
        self.assertNotIn("alreadyTrue", user["hints"])
        self.assertEqual(user["hints"]["products"][0]["is"]["id"], "photo-product-002")

    def test_a_shared_prefix_is_not_resolved_to_one_product(self):
        hint = nl_prep.make_hinter(SimpleNamespace(products=[product(1, "Lemons"), product(2, "Lemonade", "drinks")], makers={},
                                                   community={}, store={"hours": []}))
        self.assertNotIn("products", hint("lem is out", MONDAY))
        self.assertEqual(hint("lemons is out", MONDAY)["products"][0]["is"]["id"], "photo-product-001")

    def test_asked_range(self):
        for text, want in (("9 to 5", ("9am", "5pm")), ("8:30-4pm", ("8:30am", "4pm")), ("10am until 2pm", ("10am", "2pm")),
                           ("11 to 3", ("11am", "3pm")), ("noon to 5", None), ("sat 13 to 5", None), ("no range", None)):
            self.assertEqual(nl_prep.asked_range(text), want, text)

    def test_nothing_to_say_is_an_empty_dict_and_the_same_text_gives_the_same_hints(self):
        self.assertEqual(self.ask("hello there"), {})
        self.assertEqual(self.ask("honey 5pm tomorrow $4"), self.ask("honey 5pm tomorrow $4"))

    def test_odd_content_and_odd_text_never_raise(self):
        for content in (SimpleNamespace(), SimpleNamespace(products=None, makers=[], community="x", store=3),
                        SimpleNamespace(products=[None, 3, {"id": 4}, {"id": "p", "name": None}], makers={"k": None, "j": 5}, community={"events": [None, {"id": 1}]})):
            hint = nl_prep.make_hinter(content)
            for text in ("eggs are out", "\ud800 lone surrogate", "x" * 5000, "", "nov 31 29th 99/99 25:99 $", "ａｖｏ"):
                self.assertIsInstance(hint(text, MONDAY, None), dict)

    def test_a_hint_never_carries_a_claim_a_price_or_a_quantity_it_was_not_given(self):
        out = json.dumps(self.ask("honey is sold out"))
        for word in ("organic", "local", "$", "quantity"):
            self.assertNotIn(word, out)


class CalendarEndpointTests(unittest.TestCase):
    """RF0015-10: a day that would leave date.min..date.max gives no date row, and the rest of the message's hints survive."""

    @classmethod
    def setUpClass(cls):
        cls.hint = staticmethod(nl_prep.make_hinter(tiny()))

    def said(self, text, today):
        rows, hits = nl_prep.date_hints(text, today)
        return {row["said"]: row for row in rows}, hits

    def test_relative_calendar_overflow_is_local_to_the_date_token(self):
        rows, _ = self.said("tomorrow, day after tomorrow, today, tonight, yesterday", LAST_DAY)
        self.assertEqual(sorted(rows), ["today", "tonight", "yesterday"])
        self.assertEqual((rows["today"]["date"], rows["today"]["weekday"], rows["yesterday"]["date"]), ("9999-12-31", "Friday", "9999-12-30"))
        rows, _ = self.said("yesterday and today and tomorrow", FIRST_DAY)
        self.assertEqual({k: v["date"] for k, v in rows.items()}, {"today": "0001-01-01", "tomorrow": "0001-01-02"})
        rows, _ = self.said("day after tomorrow", date(9999, 12, 30))
        self.assertEqual(rows, {})
        rows, _ = self.said("day after tomorrow", date(9999, 12, 29))
        self.assertEqual(rows["day after tomorrow"]["date"], "9999-12-31")

    def test_duration_calendar_overflow_skips_without_traceback(self):
        for text in ("in 2 weeks", "in 99 days", "in 1 week", "in two weeks"):
            self.assertEqual(self.said(text, LAST_DAY)[0], {}, text)
        self.assertEqual(self.said("in 99 days", date(9999, 9, 24))[0], {})
        self.assertEqual(self.said("in 99 days", date(9999, 9, 23))[0]["in 99 days"]["date"], "9999-12-31")
        self.assertEqual(self.said("in 2 weeks", date(9999, 12, 17))[0]["in 2 weeks"]["date"], "9999-12-31")
        self.assertEqual(self.said("in 2 weeks", date(9999, 12, 18))[0], {})
        self.assertEqual(self.said("in 1 day", date(9999, 12, 30))[0]["in 1 day"]["date"], "9999-12-31")
        self.assertEqual(self.said("in 2 weeks", FIRST_DAY)[0]["in 2 weeks"]["date"], "0001-01-15")
        self.assertEqual(self.said("in 1 day", date(2028, 2, 28))[0]["in 1 day"]["date"], "2028-02-29")  # leap day
        self.assertEqual(self.said("in 2 weeks", date(2026, 12, 25))[0]["in 2 weeks"]["date"], "2027-01-08")  # year crossing

    def test_weekday_overflow_does_not_collapse_ambiguity(self):
        # 9999-12-31 is a Friday: every coming Friday/Saturday..Thursday is past the end; "last" ones are fine.
        for text in ("friday", "next friday", "this friday", "saturday", "next saturday", "thursday", "next thursday", "on sunday"):
            rows, hits = self.said(text, LAST_DAY)
            self.assertEqual(rows, {}, text)  # no partial row, no lone date for an ambiguous day
            self.assertEqual(len(hits), 1, text)  # the lexical weekday survives
        rows, hits = self.said("last friday", LAST_DAY)
        self.assertEqual((rows["last friday"]["date"], hits), ("9999-12-24", [("friday", 4)]))
        self.assertEqual(self.said("last saturday", LAST_DAY)[0]["last saturday"]["date"], "9999-12-25")
        # 0001-01-01 is a Monday: "last" and the bare form need a day before the start; next/same-day readings are fine.
        for text in ("last monday", "last tuesday", "tuesday", "sunday", "last sunday"):
            rows, hits = self.said(text, FIRST_DAY)
            self.assertEqual(rows, {}, text)
            self.assertEqual(len(hits), 1, text)
        rows, _ = self.said("monday, next tuesday, next sunday", FIRST_DAY)
        self.assertEqual(rows["monday"]["unclear"], ["0001-01-01", "0001-01-08"])
        self.assertEqual(rows["next tuesday"]["unclear"], ["0001-01-02", "0001-01-09"])
        self.assertEqual(rows["next sunday"]["unclear"], ["0001-01-07", "0001-01-14"])
        self.assertTrue(all("date" not in r for r in rows.values()))
        # the +7 alternative alone overflows: near the end a same-weekday or next reading is omitted, not reduced to one date
        self.assertEqual(self.said("friday", date(9999, 12, 24))[0]["friday"]["unclear"], ["9999-12-24", "9999-12-31"])
        self.assertEqual(self.said("friday", date(9999, 12, 25))[0]["friday"]["next"], "9999-12-31")  # both bare-weekday dates fit: unchanged
        self.assertEqual(self.said("next friday", date(9999, 12, 25))[0], {})
        self.assertEqual(self.said("next saturday", date(9999, 12, 24))[0], {})  # 12-25 is fine, 01-01 is not
        self.assertEqual(self.said("wednesday", date(9999, 12, 30))[0], {})

    def test_mixed_date_tokens_preserve_valid_rows(self):
        rows, _ = nl_prep.date_hints("tomorrow, today, dec 5 2027, in 2 weeks, yesterday", LAST_DAY)
        self.assertEqual([(r["said"], r["date"]) for r in rows], [("today", "9999-12-31"), ("yesterday", "9999-12-30"), ("dec 5 2027", "2027-12-05")])
        self.assertEqual([r["said"] for r in nl_prep.date_hints("friday, today, dec 5 2027", LAST_DAY)[0]], ["today", "dec 5 2027"])
        many = ", ".join(f"jan {n} 2027" for n in range(1, 11))  # ten valid written dates keep the old cap of eight
        rows, _ = nl_prep.date_hints("tomorrow, " + many, LAST_DAY)
        self.assertEqual(len(rows), nl_prep.MAX_LIST)
        self.assertEqual(rows[0]["said"], "jan 1 2027")

    def test_hinter_keeps_products_and_clock_when_date_overflows(self):
        control = self.hint("lemons at 9am", LAST_DAY)
        self.assertEqual(control, {"products": [{"said": "lemons", "is": {"id": "photo-product-002", "name": "Lemons"}}], "times": [{"said": "9am", "time": "09:00"}]})
        self.assertEqual(self.hint("lemons tomorrow at 9am", LAST_DAY), control)
        self.assertEqual(self.hint("lemons yesterday at 9am", FIRST_DAY), control)
        out = self.hint("lemons today and tomorrow at 9am", LAST_DAY)
        self.assertEqual(out["dates"], [{"said": "today", "date": "9999-12-31", "weekday": "Friday"}])
        self.assertEqual((out["products"], out["times"]), (control["products"], control["times"]))
        self.assertEqual(self.hint("lemons in 2 weeks at 9am", LAST_DAY), control)

    def test_an_overflowing_weekday_keeps_the_hike_weekday_match(self):
        events = [{"id": "hike-9999-12-26", "title": "Far walk", "startsAt": "9999-12-26T08:30:00-08:00", "status": "scheduled"}]  # a Sunday
        content = SimpleNamespace(**{**vars(tiny()), "community": {"events": events}})
        out = nl_prep.make_hinter(content)("move the walk on sunday at 9am", LAST_DAY)
        self.assertNotIn("dates", out)
        self.assertEqual(out["hikes"]["onThatWeekday"][0]["scheduled hikes"][0]["hike"], "hike-9999-12-26")
        self.assertEqual(out["times"], [{"said": "9am", "time": "09:00"}])

    def test_ordinary_date_and_year_contract_is_unchanged(self):
        rows, hits = nl_prep.date_hints("wednesday, next saturday, last friday, monday", MONDAY)
        self.assertEqual(hits, [("wednesday", 2), ("saturday", 5), ("friday", 4), ("monday", 0)])
        self.assertEqual(rows[0], {"said": "wednesday", "next": "2026-11-11", "last": "2026-11-04", "weekday": "Wednesday",
                                   "note": "next = the coming one; last = the one just past"})
        self.assertEqual((rows[1]["unclear"], rows[2]["date"], rows[3]["unclear"]), (["2026-11-14", "2026-11-21"], "2026-11-06", ["2026-11-09", "2026-11-16"]))
        self.assertEqual(rows[1]["note"], "two readings; ask which unless the owner said")
        self.assertEqual([(r["said"], r["date"]) for r in nl_prep.date_hints("in 2 weeks, in 3 days, today, tomorrow", MONDAY)[0]],
                         [("today", "2026-11-09"), ("tomorrow", "2026-11-10"), ("in 2 weeks", "2026-11-23"), ("in 3 days", "2026-11-12")])
        self.assertEqual(nl_prep.date_hints("the 31st", date(2026, 11, 9))[0][0]["date"], "2026-12-31")  # ordinal rollover
        self.assertEqual(nl_prep.date_hints("feb 29 2028 and dec 5 202", MONDAY)[0][0]["date"], "2028-02-29")
        self.assertEqual(nl_prep._next_weekday(MONDAY, 0), date(2026, 11, 16))
        self.assertEqual(nl_prep._next_weekday(MONDAY, 0, include_today=True), MONDAY)
        self.assertIsNone(nl_prep._next_weekday(LAST_DAY, 5))


class CorpusHintTests(unittest.TestCase):
    """The corpus catalog: the hints agree with the answer key wherever the key names one product."""

    def test_clear_availability_cases_resolve_to_the_expected_product(self):
        hint = nl_prep.make_hinter(nl_eval._content())
        checked = 0
        for case in nl_eval.load_corpus():
            ops = case["expect"].get("ops") or []
            ids = {c["args"]["id"] for c in ops if c["op"].startswith("product.") and "id" in c["args"]}
            if case["intent"] != "availability" or len(ids) != 1 or case.get("also") or len(ops) != 1: continue
            rows = hint(case["text"], nl_eval.SENT_AT.date(), case.get("aliases")).get("products", [])
            resolved = {r["is"]["id"] for r in rows if "is" in r}
            if resolved: self.assertEqual(resolved, ids, case["id"])  # a hint that names a product names the right one
            checked += 1
        self.assertGreater(checked, 40)


class RequestTests(unittest.TestCase):
    def fake(self, seen):
        def transport(url, body, headers, timeout):
            seen.append(json.loads(body))
            return 200, json.dumps({"done": True, "message": {"content": json.dumps({"question": "ok"})}}).encode()
        return transport

    def user(self, seen):
        return json.loads(seen[-1]["messages"][1]["content"])

    def make(self, seen, **kw):
        return LocalInterpreter(URL, "m", "SYSTEM", transport=self.fake(seen), clock=lambda: datetime(2026, 11, 9, 17, 40, tzinfo=timezone.utc), **kw)

    def test_no_hinter_and_no_recent_leaves_the_request_as_it_was(self):
        seen = []
        self.make(seen).interpret("eggs are out", [])
        self.assertEqual(set(self.user(seen)), {"message", "pending", "today", "weekday"})

    def test_hints_and_recent_are_added_only_when_there_is_something(self):
        seen = []
        interp = self.make(seen, hinter=nl_prep.make_hinter(tiny()))
        interp.interpret("eggs are out", [], recent={"question": "Which one?"})
        user = self.user(seen)
        self.assertEqual(user["hints"]["products"][0]["is"]["id"], "photo-product-003")
        self.assertEqual(user["recent"], {"question": "Which one?"})
        interp.interpret("hello there", [])
        self.assertEqual(set(self.user(seen)), {"message", "pending", "today", "weekday"})
        for bad in (None, {}, {"question": ""}, {"question": 5}, "Which one?", ["x"]):
            interp.interpret("hello there", [], recent=bad)
            self.assertNotIn("recent", self.user(seen), bad)

    def test_product_name_order_reaches_the_interpreter_without_guessing(self):
        # Comparing whole names only as sets loses the owner's choice between
        # different listings with the same words. Inspect the real request hints.
        lime = {"id": "photo-product-021", "name": "Lime Mint Tea"}
        mint = {"id": "photo-product-022", "name": "Mint Lime Tea"}
        duplicate = {"id": "photo-product-023", "name": "LÍME-MINT Teas"}
        cases = (
            ("change the Lime Mint Tea description", [mint, lime], {"said": "lime mint tea", "is": lime}),
            ("what is the price of Mint Lime Tea?", [mint, lime], {"said": "mint lime tea", "is": mint}),
            ("change the Lime Mint Tea description", [lime], {"said": "lime mint tea", "is": lime}),
            ("what is the price of Lime Mint Tea?", [lime, duplicate],
             {"said": "lime mint tea", "ambiguous": [lime, duplicate]}),
            ("what is the price of Tea Mint Lime?", [lime], {"said": "tea mint lime", "is": lime}),
            ("what is the price of Tea Mint Lime?", [mint, lime],
             {"said": "tea mint lime", "ambiguous": [mint, lime]}),
            ("what is the price of Lim Mint Tea?", [mint, lime],
             {"said": "lim mint tea", "ambiguous": [mint, lime], "spelling": "guessed"}),
        )
        for text, products, expected in cases:
            with self.subTest(text=text, candidates=[p["id"] for p in products]):
                seen = []
                content = SimpleNamespace(products=products)
                self.make(seen, hinter=nl_prep.make_hinter(content)).interpret(text, [])
                self.assertEqual(self.user(seen)["hints"]["products"], [expected])

    def test_the_hint_day_is_the_pacific_day(self):
        seen = []
        late = datetime(2026, 11, 10, 3, 30, tzinfo=timezone.utc)  # 7:30pm Monday in California
        interp = self.make(seen, hinter=nl_prep.make_hinter(tiny()))
        interp.interpret("tomorrow", [], sent_at=late)
        user = self.user(seen)
        self.assertEqual((user["today"], user["hints"]["dates"][0]["date"]), ("2026-11-09", "2026-11-10"))

    def test_transport_receives_surviving_hints_without_guessed_day(self):
        seen = []
        last = datetime(9999, 12, 31, 20, 0, tzinfo=timezone.utc)  # noon on the last Pacific day; midday keeps the Pacific day put
        interp = LocalInterpreter(URL, "m", "SYSTEM", transport=self.fake(seen), clock=lambda: last, hinter=nl_prep.make_hinter(tiny()))
        interp.interpret("lemons tomorrow at 9am", [])
        user = self.user(seen)
        self.assertEqual(user["today"], "9999-12-31")
        self.assertEqual(user["hints"], {"products": [{"said": "lemons", "is": {"id": "photo-product-002", "name": "Lemons"}}], "times": [{"said": "9am", "time": "09:00"}]})
        self.assertNotIn("dates", user["hints"])
        interp.interpret("lemons today and tomorrow at 9am", [])
        self.assertEqual([row["date"] for row in self.user(seen)["hints"]["dates"]], ["9999-12-31"])

    def test_a_raising_or_wrong_hinter_means_no_hints_not_a_failed_call(self):
        for hinter in (lambda *a: 1 / 0, lambda *a: "text", lambda *a: None):
            seen = []
            interp = self.make(seen, hinter=hinter)
            self.assertEqual(interp.interpret("eggs", []), {"question": "ok"})
            self.assertEqual((interp.last_error, "hints" in self.user(seen)), (None, False))
        with self.assertRaises(ValueError):
            LocalInterpreter(URL, "m", "SYSTEM", hinter="not callable")

    def test_an_explicit_year_reaches_the_model_as_written(self):
        seen = []
        interp = self.make(seen, hinter=nl_prep.make_hinter(tiny()))
        for text, want in (("post a Cass Hill hike on December 5 2027 at 9am", "2027-12-05"), ("post a Cass Hill hike on 5 Dec 2027 at 9am", "2027-12-05"),
                           ("post a Cass Hill hike on 12/5/2027 at 9am", "2027-12-05"), ("post a Cass Hill hike on December 5 at 9am", "2026-12-05")):
            interp.interpret(text, [])
            user = self.user(seen)
            self.assertEqual(user["message"], text)
            self.assertEqual([row["date"] for row in user["hints"]["dates"]], [want], text)
        for text in ("post a Cass Hill hike on feb 30 2027 at 9am", "post a Cass Hill hike on December 5 202 at 9am", "post a Cass Hill hike on 5 December 20277 at 9am"):
            interp.interpret(text, [])
            self.assertEqual(self.user(seen)["message"], text)
            self.assertNotIn("dates", self.user(seen).get("hints", {}), text)

    def test_hints_are_sent_after_the_saved_context(self):
        seen = []
        self.make(seen, hinter=nl_prep.make_hinter(tiny())).interpret("eggs are out", [], notes=["n"], aliases=[{"name": "x", "kind": "product", "id": "photo-product-001"}])
        self.assertEqual(list(self.user(seen))[-3:], ["notes", "aliases", "hints"])


class RecentQuestionTests(ConversationTestCase):
    """Conversation passes Hass's last question to the interpreter, but only while it is the newest word and still fresh."""

    def setUp(self):
        super().setUp()
        self.asked = []
        outer = self

        class Recording(conversation.FixtureInterpreter):
            def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None):
                outer.asked.append((text, recent))
                return super().interpret(text, pending)

        self.interp = Recording(self.interp.mapping)
        self.conv = self.open()

    def test_the_first_message_has_no_recent_and_the_answer_gets_the_question(self):
        self.assertEqual(self.say("when?"), "question")
        self.replies()
        self.assertEqual(self.asked[-1], ("when?", None))
        self.now += timedelta(minutes=5)
        self.say("hours")
        self.assertEqual(self.asked[-1], ("hours", {"question": "Which day should change?", "earlier": ["when?"]}))  # HASS-HIKE-FLOW-1: with the owner's text

    def test_it_is_dropped_after_30_minutes_or_once_something_else_was_said(self):
        self.say("when?")
        self.now += timedelta(minutes=31)
        self.say("hours")
        self.assertIsNone(self.asked[-1][1])
        self.say("when?")
        self.say("hours")  # answered once: the proposal is newest now
        self.say("desc")
        self.assertIsNone(self.asked[-1][1])

    def test_a_question_from_before_a_newer_message_is_not_recent(self):
        self.say("when?")
        self.say("status")  # a command, not a question
        self.say("hours")
        self.assertIsNone(self.asked[-1][1])

    def test_a_question_is_kept_only_up_to_500_characters(self):
        self.interp.mapping["long?"] = {"question": "Which one?"}
        self.say("long?")
        # A legacy overlong answer in storage is not passed back as recent context.
        self.conv.db.execute("UPDATE outbox SET text = ?", ("Which one? " + "x" * 600,))
        self.conv.db.commit()
        self.say("hours")
        self.assertIsNone(self.asked[-1][1])
        self.assertEqual(conversation.RECENT_MAX, 500)

    def test_a_missing_table_or_bad_row_is_no_recent_not_a_crash(self):
        self.conv.db.execute("DROP TABLE outbox")
        self.assertIsNone(self.conv._recent_question(self.now))


class QuotedYearTests(unittest.TestCase):
    """A malformed apostrophe-prefixed year after a month and day leaves that date out instead of rolling to the next annual date."""
    fake, user, make = RequestTests.fake, RequestTests.user, RequestTests.make

    def dates(self, text):
        return nl_prep.date_hints(text, MONDAY)[0]

    def test_malformed_apostrophe_year_never_rolls_to_current_year(self):
        for text in ("hike on December 5 '2027", "hike on December 5 '277", "hike on December 5 '2", "hike on dec 5 '20277",
                     "hike on December 5, '2027", "hike on December 5th '277", "hike on 5 Dec. '2027", "hike on 5th of Dec. '277",
                     "hike on 5 December, '2027", "hike on 5 Dec '2"):
            self.assertEqual(self.dates(text), [], text)

    def test_curly_apostrophe_year_refusal_uses_existing_fold(self):
        for q in ("'", "\u2019", "\u2018"):
            self.assertEqual(self.dates(f"hike on December 5 {q}2027"), [])
            self.assertEqual(self.dates(f"hike on 5 Dec. {q}27")[0]["date"], "2027-12-05")

    def test_valid_year_and_yearless_controls_keep_exact_rows(self):
        self.assertEqual(self.dates("hike on December 5 '27"), [{"said": "december 5 '27", "date": "2027-12-05", "weekday": "Sunday"}])
        self.assertEqual(self.dates("hike on 5 Dec. '27")[0]["date"], "2027-12-05")
        self.assertEqual(self.dates("hike on December 5 2027")[0]["date"], "2027-12-05")
        self.assertEqual(self.dates("hike on December 5"), [{"said": "december 5", "date": "2026-12-05", "weekday": "Saturday"}])
        self.assertEqual(self.dates("hike on December 5 '27:30"), self.dates("hike on December 5 27:30"))
        self.assertEqual(self.dates("hike on dec 5 at 3 pm"), self.dates("hike on dec 5 3pm"))

    def test_bad_quoted_year_is_local_to_one_date_occurrence(self):
        rows = self.dates("hike on December 5 '277 or 12 Dec. '2027 or January 3 2027")
        self.assertEqual([r["date"] for r in rows], ["2027-01-03"])

    def test_serialized_request_omits_bad_year_but_keeps_owner_words(self):
        for q in ("'", "\u2019"):
            for text in (f"hike on December 5 {q}2027 at 9am", f"hike on 5 Dec. {q}2027 at 9am"):
                seen = []
                self.make(seen, hinter=nl_prep.make_hinter(tiny())).interpret(text, [])
                user = self.user(seen)
                self.assertNotIn("dates", user["hints"])
                self.assertEqual(user["message"], text)
                self.assertEqual(user["hints"]["times"], [{"said": "9am", "time": "09:00"}])


class RouteTitleHintTests(unittest.TestCase):
    """A route idea whose title carries hike/walk is named by its distinctive tokens, like the event branch."""

    def idx(self, titles, events=()):
        ideas = [{"id": f"idea-{i}", "title": t} for i, t in enumerate(titles)]
        return SimpleNamespace(products=[], makers={}, community={"events": list(events), "routeIdeas": ideas}, store={"hours": []})

    def named(self, titles, text, events=()):
        return nl_prep.make_hinter(self.idx(titles, events))(text, MONDAY, None).get("hikes", {}).get("named", [])

    def test_route_name_with_hike_or_walk_suffix_is_recognized(self):
        for title in ("Morro Rock hike", "Morro Rock walk", "Morro Rock hikes", "Morro Rock walks", "Hike Morro Rock"):
            for text in (title, "plan the MORRO rock please", "Morró Rock hike"):
                self.assertEqual(self.named([title], text), [{"routeIdea": "idea-0", "title": title}], (title, text))

    def test_generic_only_route_title_never_names_a_route(self):
        for title in ("hike", "Walks", "hike walk", "", "the"):
            self.assertEqual(self.named([title], "any hike or walk on saturday please"), [], title)

    def test_route_requires_every_distinctive_whole_token(self):
        for text in ("morro hike", "rock walk", "the morrow rocks hike", "morrorock hike"):
            self.assertEqual(self.named(["Morro Rock hike"], text), [], text)
        self.assertEqual(len(self.named(["Morro Rock hike"], "rock then morro")), 1)

    def test_named_routes_preserve_order_shape_and_cap(self):
        event = {"id": "ev-1", "title": "Morro Rock hike", "startsAt": None, "status": None}
        out = self.named(["Morro Rock walk", "Rock hike"], "morro rock hike", [event])
        self.assertEqual([r.get("hike") or r.get("routeIdea") for r in out], ["ev-1", "idea-0", "idea-1"])
        self.assertEqual(out[1], {"routeIdea": "idea-0", "title": "Morro Rock walk"})
        many = [f"Rock hike {i}" for i in range(12)]
        self.assertEqual(len(self.named(many, "rock hike " + " ".join(str(i) for i in range(12)))), nl_prep.MAX_LIST)

    def test_route_matching_preserves_other_hints_and_inputs(self):
        idx = self.idx(["Morro Rock hike"])
        idx.products = [product(1, "Lemons")]
        before = json.dumps(idx.community, sort_keys=True)
        hint = nl_prep.make_hinter(idx)
        first = hint("morro rock hike and lemons at 9am", MONDAY, None)
        self.assertEqual(first["times"], [{"said": "9am", "time": "09:00"}])
        self.assertEqual(first["hikes"]["named"], [{"routeIdea": "idea-0", "title": "Morro Rock hike"}])
        self.assertEqual(first["products"][0]["is"]["id"], "photo-product-001")
        self.assertEqual(hint("morro rock hike and lemons at 9am", MONDAY, None), first)
        self.assertEqual(json.dumps(idx.community, sort_keys=True), before)

    def test_fake_request_contains_named_suffix_route(self):
        seen = []
        req = RequestTests()
        interp = req.make(seen, hinter=nl_prep.make_hinter(self.idx(["Morro Rock hike"])))
        interp.interpret("plan the Morro Rock hike at 9am", [])
        user = req.user(seen)
        self.assertEqual(len(seen), 1)
        self.assertEqual(user["message"], "plan the Morro Rock hike at 9am")
        self.assertEqual(user["hints"]["hikes"]["named"], [{"routeIdea": "idea-0", "title": "Morro Rock hike"}])
        self.assertEqual(user["hints"]["times"], [{"said": "9am", "time": "09:00"}])


class GuideTests(unittest.TestCase):
    """docs/hass/NATURAL_LANGUAGE.md says the same numbers and commands the code uses."""
    DOCS = Path(__file__).resolve().parents[2] / "docs" / "hass"

    def test_the_guide_is_linked_and_states_the_real_question_window(self):
        guide = (self.DOCS / "NATURAL_LANGUAGE.md").read_text("utf-8")
        self.assertIn("](NATURAL_LANGUAGE.md)", (self.DOCS / "README.md").read_text("utf-8"))
        self.assertIn(f"{conversation.RECENT_MINUTES} minutes <!-- conversation.RECENT_MINUTES -->", guide)
        for command in ("`status`", "`undo`", "`no a1b2`", "`yes a1b2`"):
            self.assertIn(command, guide)
        self.assertNotIn("$", guide.replace("`", "").replace("prices", ""))  # no price is promised anywhere on the page


class LeapDayHintTests(unittest.TestCase):
    def dates(self, text, today):
        return [(r["said"], r["date"], r["weekday"]) for r in nl_prep.date_hints(text, today)[0] if "date" in r]

    def test_yearless_leap_day_finds_next_occurrence(self):
        today = date(2026, 11, 9)
        for said in ("feb 29", "29 feb", "2/29"):
            self.assertEqual(self.dates(said, today), [(said, "2028-02-29", "Tuesday")], said)

    def test_leap_day_today_and_after_rollover(self):
        self.assertEqual(self.dates("feb 29", date(2028, 2, 28))[0][1], "2028-02-29")
        self.assertEqual(self.dates("feb 29", date(2028, 2, 29))[0][1], "2028-02-29")
        self.assertEqual(self.dates("feb 29", date(2028, 3, 1))[0][1], "2032-02-29")
        self.assertEqual(self.dates("mar 1", date(2028, 3, 2))[0][1], "2029-03-01")  # ordinary rollover unchanged

    def test_century_gap_uses_gregorian_calendar(self):
        self.assertEqual(self.dates("feb 29", date(2097, 1, 1))[0][1], "2104-02-29")

    def test_explicit_year_never_searches_or_rewrites(self):
        today = date(2026, 11, 9)
        self.assertEqual(self.dates("feb 29 2027", today), [])
        self.assertEqual(self.dates("feb 29 2028", today)[0][1], "2028-02-29")
        self.assertEqual(self.dates("feb 29 2028", date(2030, 1, 1))[0][1], "2028-02-29")

    def test_impossible_date_and_calendar_exhaustion_remain_absent(self):
        today = date(2026, 11, 9)
        self.assertEqual(self.dates("feb 30", today), [])
        self.assertEqual(self.dates("apr 31", today), [])
        self.assertEqual(self.dates("feb 29", date(9996, 3, 1)), [])  # no leap day left before date.max
        self.assertEqual(self.dates("dec 31", date(9999, 12, 31))[0][1], "9999-12-31")

    def test_day_resolver_inherits_date(self):
        from hass.skills import kinds
        r = kinds.day("feb 29", date(2026, 11, 9))
        self.assertEqual((r.status, r.value), ("one", "2028-02-29"))

    def test_request_keeps_owner_text_and_independent_hints(self):
        seen = []
        def transport(url, body, headers, timeout):
            seen.append(json.loads(body))
            return 200, json.dumps({"done": True, "message": {"content": json.dumps({"question": "ok"})}}).encode()
        interp = LocalInterpreter(URL, "m", "SYSTEM", transport=transport, hinter=nl_prep.make_hinter(tiny()),
                                  clock=lambda: datetime(2026, 11, 9, 17, 40, tzinfo=timezone.utc))
        interp.interpret("lemons on feb 29 at 9am", [])
        self.assertEqual(len(seen), 1)
        user = json.loads(seen[0]["messages"][1]["content"])
        self.assertEqual(user["message"], "lemons on feb 29 at 9am")
        self.assertEqual(user["hints"]["times"], [{"said": "9am", "time": "09:00"}])
        self.assertEqual(user["hints"]["dates"], [{"said": "feb 29", "date": "2028-02-29", "weekday": "Tuesday"}])


if __name__ == "__main__":
    unittest.main()
