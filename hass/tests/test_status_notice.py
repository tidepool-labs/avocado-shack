"""AV1937-07 (H13/H17): `status` and `report` name the saved home-page notice and its last day.

Valid notice, last day not before the Pacific shop day: "Home notice: <text> - through <weekday, month day>". Last day
passed: "Home notice: <text> - ended <weekday, month day>; no longer shown". No, unreadable or invalid notice: no line.
Read-only and working while paused: the saved notice, waiting drafts, pause, approvals and the interpreter are untouched.
Clock T0 = Mon 2026-11-02 09:00 PST. Run: python3 -B -m unittest hass.tests.test_status_notice -v
"""

import json
import unittest
from datetime import date, datetime, timedelta, timezone

from hass import editor, morning_report
from hass.chat.shared import SHELF_ASK
from hass.content_model import MAX_NOTICE, load_content
from hass.tests.test_editor import git
from hass.tests.test_conversation import _ops
from hass.tests.test_status_pause import StoreMixin
from hass.tests.test_undo import H06TestCase

TEXT = "Closed Thanksgiving Day"
LINE = "Home notice: Closed Thanksgiving Day - through Thursday, November 26"
ENDED = "Home notice: Closed Thanksgiving Day - ended Sunday, November 1; no longer shown"
NOT_DONE = "I still need your shelf check."
NOTHING_WAITING = "Nothing is waiting for you."


class NoticeTestCase(StoreMixin, H06TestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        real = self.interp.interpret
        self.interp.interpret = lambda *a, **k: (self.calls.append(a), real(*a, **k))[1]
        self.interp.mapping[f"notice {TEXT}"] = _ops(("store.set_notice", {"text": TEXT, "until": "2026-11-26"}))

    def store_path(self):
        return self.repo.wt / "hass" / "content" / "store.json"

    def put(self, **fields):
        doc = json.loads(self.store_path().read_text("utf-8"))
        for key, value in fields.items():
            doc.pop(key, None) if value is KeyError else doc.__setitem__(key, value)
        self.store_path().write_text(json.dumps(doc), "utf-8")

    def notice(self, until="2026-11-26", text=TEXT):
        self.put(notice={"text": text, "until": until})

    def report(self):
        self.assertEqual(self.say("report"), "report")
        [reply] = self.replies()
        return reply

    def only(self, lines):
        return [line for line in lines if line.startswith("Home notice")]

    def at(self, *args):
        self.now = datetime(*args, tzinfo=timezone.utc)


class NoticeLineTests(NoticeTestCase):
    def test_active_notice_same_line_in_status_and_report(self):  # 1
        self.put(selection_checked_on="2026-11-02")
        self.notice()
        draft, _reply = self.propose("hours")
        status = self.status()
        self.assertEqual(self.only(status), [LINE])
        self.assertEqual(status, ["Everything is ready.", status[1], "Your last shelf check was Monday, November 2.", "On the shelves: 0 available, 0 running low, 0 sold out, 170 not confirmed.", LINE])
        self.assertTrue(status[1].startswith("Waiting for your yes:"))
        report = self.report()
        content = load_content(self.repo.wt / "hass" / "content")
        text = morning_report.render(morning_report.facts(content, date(2026, 11, 2)))
        self.assertEqual(report.count(LINE), 1)
        self.assertEqual(report, f"{text}\n{LINE}\n\nWaiting for you:\n" + report.split("Waiting for you:\n")[1])
        self.assertIn(draft["code"], report.split("Waiting for you:\n")[1])
        long_text = "Closed " + "x" * (MAX_NOTICE - 7)  # the complete owner text, never cut
        self.notice(text=long_text)
        self.assertEqual(self.only(self.status()), [f"Home notice: {long_text} - through Thursday, November 26"])

    def test_last_day_inclusive_and_pacific_midnight(self):  # 2
        for until, clocks in (
                ("2026-11-01", (((2026, 11, 2, 7, 59), LINE.replace("November 26", "November 1").replace("Thursday", "Sunday")),
                                ((2026, 11, 2, 8, 0), ENDED))),  # 23:59 PST then 00:00 PST on 2 Nov; UTC is already 2 Nov
                ("2026-10-31", (((2026, 11, 1, 6, 59), LINE.replace("November 26", "October 31").replace("Thursday", "Saturday")),
                                ((2026, 11, 1, 7, 0), ENDED.replace("Sunday, November 1", "Saturday, October 31"))))):  # PDT midnight, before the fall back
            self.notice(until=until)
            for clock, line in clocks:
                with self.subTest(until=until, clock=clock):
                    self.at(*clock)
                    self.assertEqual(self.only(self.status()), [line])
                    self.assertEqual(self.only(self.report().splitlines()), [line])

    def test_expired_notice_keeps_text_and_saved_record(self):  # 3
        self.notice(until="2026-11-01")
        saved, head = self.store_path().read_bytes(), self.repo.head()
        self.assertEqual(self.only(self.status()), [ENDED])
        self.assertEqual(self.only(self.report().splitlines()), [ENDED])
        self.assertEqual((self.store_path().read_bytes(), self.repo.head(), self.repo.status()), (saved, head, "M hass/content/store.json"))
        self.assertNotIn("through", ENDED)

    def test_absent_notice_preserves_replies(self):  # 4
        self.assertNotIn("notice", json.loads(self.store_path().read_text("utf-8")))
        self.assertEqual(self.status(), ["Everything is ready.", "Nothing is waiting for your yes.", NOT_DONE])
        content = load_content(self.repo.wt / "hass" / "content")
        text = morning_report.render(morning_report.facts(content, date(2026, 11, 2)))
        self.assertEqual(self.report(), f"{text}\n\n{NOTHING_WAITING}\n\n{SHELF_ASK}")

    def test_unreadable_or_malformed_notice_is_omitted(self):  # 6
        good = "2026-11-26"
        for name, bad in (("not an object", "Closed"), ("empty text", {"text": "", "until": good}),
                          ("too few letters", {"text": "!!", "until": good}), ("text not a string", {"text": 5, "until": good}),
                          ("too long", {"text": "x" * (MAX_NOTICE + 1), "until": good}), ("extra key", {"text": TEXT, "until": good, "x": 1}),
                          ("bad date", {"text": TEXT, "until": "2026-02-30"}), ("date and time", {"text": TEXT, "until": "2026-11-26T00:00"}),
                          ("date not a string", {"text": TEXT, "until": 20261126})):
            with self.subTest(name):
                self.put(notice=bad, selection_checked_on="2026-11-02")
                status = self.status()
                report = self.report()
                self.assertEqual((self.only(status), "Home notice" in report), ([], False))
                self.assertEqual(status[0], "Everything is ready.")
                self.assertIn("Your last shelf check was Monday, November 2.", status)  # the other status lines stay
                self.assertTrue(report.endswith(NOTHING_WAITING))  # an invalid notice also fails the report's own validation
                for reply in ("\n".join(status), report):
                    self.assertNotIn("Traceback", reply)
                    self.assertNotIn("2026-02-30", reply)
        for name, damage in (("malformed JSON", lambda p: p.write_text("{not json", "utf-8")), ("missing file", lambda p: p.unlink())):
            with self.subTest(name):
                self.put(notice={"text": TEXT, "until": good})
                damage(self.store_path())
                status, report = self.status(), self.report()
                self.assertEqual((self.only(status), "Home notice" in report, status[0]), ([], False, "Everything is ready."))
                self.assertIn("I can't read the shelf report right now", report)
                git(self.repo.wt, "checkout", "--", "hass/content/store.json")
        with self.subTest("product facts failure alone"):
            self.notice()
            (self.repo.wt / "hass" / "content" / "products.json").write_text("{not json", "utf-8")
            status, report = self.status(), self.report()
            self.assertEqual(self.only(status), [LINE])
            self.assertEqual(self.only(report.splitlines()), [LINE])
            self.assertIn("I can't read the shelf report right now", report)


class NoticeReadOnlyTests(NoticeTestCase):
    def test_paused_commands_do_not_sweep_or_apply(self):  # 5
        self.put(selection_checked_on="2026-11-02")
        self.notice()
        draft, _reply = self.propose("hours")
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        control = lambda: [tuple(r) for r in self.conv.db.execute("SELECT name, value FROM control")]
        before = (self.drafts(), self.store_path().read_bytes(), self.repo.head(), control(), len(self.calls))
        self.now += timedelta(hours=1)  # the waiting draft has expired; nothing sweeps it
        for reply in (self.status(), self.report().splitlines()):
            self.assertEqual(self.only(reply), [LINE])
        self.assertNotIn("Waiting for your yes", "\n".join(self.status()))
        self.assertEqual(self.drafts(), before[0])
        self.assertEqual(self.drafts()[0]["state"], "proposed")
        self.assertEqual((self.store_path().read_bytes(), self.repo.head(), control(), len(self.calls)), before[1:])
        self.assertEqual((self.commits(), self.editor.applies if hasattr(self.editor, "applies") else 0, self.approvals()), (0, 0, 0))
        self.assertIsNotNone(self.conv._paused())

    def test_notice_after_approved_change_and_undo(self):  # 7
        self.put(selection_checked_on="2026-11-02")
        git(self.repo.wt, "commit", "-aqm", "shelf check")
        self.base = self.count()
        self.assertEqual(self.only(self.status()), [])
        # Prepare and apply against the same synthetic shop day as the conversation.
        self.editor.prepare = lambda ops: editor.prepare({"ops": ops}, state=self.editor.state,
                                                         registry=self.editor.registry, now=self.now)
        self.editor.apply = lambda change_id, draft_hash: editor.apply(change_id, draft_hash, state=self.editor.state,
                                                                       registry=self.editor.registry, now=self.now)
        done = self.apply(f"notice {TEXT}")
        self.assertEqual((done["state"], self.commits()), ("verified", 1))
        first = date.fromisoformat(json.loads(self.store_path().read_text("utf-8"))["notice"]["from"])  # AV2152-08: saved as set
        self.assertEqual(first, date(2026, 11, 2))  # editor used the injected Pacific shop day
        self.at(first.year, first.month, first.day, 20)  # that Pacific day, midday: the notice is active
        line = f"Home notice: {TEXT} - from {first.strftime('%A, %B')} {first.day} through Thursday, November 26"
        self.assertEqual(self.only(self.status()), [line])
        self.assertEqual(self.only(self.report().splitlines()), [line])
        self.assertEqual((self.commits(), len(self.calls)), (1, 1))  # reading adds no commit and no interpreter call
        self.assertEqual(self.say(f"undo {done['code']}"), "proposed")
        self.replies()
        self.assertEqual(self.say("yes"), "approved")
        self.replies()
        self.assertEqual(self.commits(), 2)
        self.assertNotIn("notice", json.loads(self.store_path().read_text("utf-8")))
        self.assertEqual(self.only(self.status()), [])
        self.assertNotIn("Home notice", self.report())
        self.assertEqual(self.commits(), 2)


class ScheduledNoticeTests(NoticeTestCase):  # AV2152-08: a notice with its own first day
    RANGE = "from Friday, November 20 through Thursday, November 26"

    def test_scheduled_active_ended_lines_in_status_and_report(self):
        self.notice_from("2026-11-20", "2026-11-26")
        for clock, suffix in (((2026, 11, 2, 17), "; not shown yet"), ((2026, 11, 20, 7, 59), "; not shown yet"),  # 23:59 PST on the 19th
                              ((2026, 11, 20, 8, 0), ""), ((2026, 11, 27, 7, 59), ""),  # first day midnight; 23:59 on the last day
                              ((2026, 11, 27, 8, 0), "; no longer shown")):
            with self.subTest(clock=clock):
                self.at(*clock)
                line = f"Home notice: {TEXT} - {self.RANGE}{suffix}"
                self.assertEqual(self.only(self.status()), [line])
                report = self.report()
                self.assertEqual((self.only(report.splitlines()), report.count("Home notice")), ([line], 1))

    def test_same_day_legacy_and_invalid_first_day(self):
        self.notice_from("2026-11-26", "2026-11-26")
        self.assertEqual(self.only(self.status()),
                         [f"Home notice: {TEXT} - from Thursday, November 26 through Thursday, November 26; not shown yet"])
        self.notice()  # legacy wording stays
        self.assertEqual(self.only(self.status()), [LINE])
        for bad in ("2026-02-30", "2026-11-27", None, 20261120, "2026-11-20T00:00"):
            with self.subTest(bad=bad):
                self.put(notice={"text": TEXT, "from": bad, "until": "2026-11-26"})
                self.assertEqual((self.only(self.status()), "Home notice" in self.report()), ([], False))

    def test_read_only_and_paused_with_a_scheduled_notice(self):
        self.notice_from("2026-11-20", "2026-11-26")
        draft, _reply = self.propose("hours")
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        before = (self.drafts(), self.store_path().read_bytes(), self.repo.head(), len(self.calls))
        self.now += timedelta(hours=1)
        self.assertEqual(self.only(self.status()), [f"Home notice: {TEXT} - {self.RANGE}; not shown yet"])
        self.assertEqual((self.drafts(), self.store_path().read_bytes(), self.repo.head(), len(self.calls)), before)
        self.assertEqual(self.drafts()[0]["state"], "proposed")
        self.assertEqual(draft["state"], "proposed")

    def notice_from(self, first, until):
        self.put(notice={"text": TEXT, "from": first, "until": until})


if __name__ == "__main__":
    unittest.main()
