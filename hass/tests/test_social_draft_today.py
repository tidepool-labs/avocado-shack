"""AV1104-08 tests: social_draft.build_today and --today draft an "In at the Shack today" caption naming only the active products
whose yes/limited word was confirmed on the saved shelf-check day, and only when that day is Pacific today (SHOP-1).
Run: python3 -B -m unittest hass.tests.test_social_draft_today -v

Synthetic content only. Each test names the contract it protects and the believable bug that fails it. Nothing is posted.
"""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hass import social_draft
from hass.content_model import Content

TAGS = "\n\n#AvocadoShack #MorroBay"
STORE = {"name": "Avocado Shack", "streetAddress": "2190 Main Street", "town": "Morro Bay"}
DAY = "2026-11-24"  # Tuesday
NOON = datetime(2026, 11, 24, 20, 0, tzinfo=timezone.utc)  # 12:00 PST, Tuesday 2026-11-24
SEND = "; send today's shelf check first."


def prod(pid, name=None, available="yes", on=DAY, status="active", **extra):
    p = {"id": pid, "name": name or pid.title(), "status": status, **extra}
    if available is not None: p["available"] = available
    if on is not None: p["available_on"] = on
    return p


def content(products, check=DAY, **store):
    s = {**STORE, **store}
    if check is not None: s["selection_checked_on"] = check
    return Content(products=products, makers={}, community={}, store=s)


def refused(reason):
    return {"draft": False, "reason": reason}


def caption(listing):
    return f"In at the Shack today\n{listing}\nAvocado Shack\n2190 Main Street, Morro Bay.{TAGS}"


class BuildTodayTests(unittest.TestCase):
    def test_caption_names_confirmed_products_in_site_order_and_leaks_nothing_else(self):
        """Yes and limited products are named in products.json order (not alphabetical, not grouped), equal names on two ids both kept, and no
        description, maker or photo is copied. Bug caught: sorting, de-duplicating by name, grouping by word or leaking a description."""
        c = content([prod("zucchini", "Zucchini", description="SECRET"), prod("apple", "Apple", "limited", image="assets/products/a.png"),
                     prod("jam1", "Jam"), prod("jam2", "Jam", "limited")])
        before = copy.deepcopy(c)
        self.assertEqual(social_draft.build_today(c, NOON), {"draft": True, "caption": caption("Zucchini, Apple, Jam, Jam")})
        self.assertEqual((c.products, c.store), (before.products, before.store))  # read-only

    def test_only_the_check_day_words_of_active_products_count(self):
        """A product is named only when its own word is yes/limited, dated on today's check, and it is active. A word from an earlier check, a
        missing/bad/future date, no/absent word, hidden or held are never named. Bug caught: a later store-only check refreshing a stale word."""
        c = content([prod("ok", "Ok"), prod("old", "Old", on="2026-11-23"), prod("nodate", "Nodate", on=None), prod("bad", "Bad", on="2026-13-40"),
                     prod("future", "Future", on="2026-11-25"), prod("no", "No", "no"), prod("noword", "Noword", None, None),
                     prod("odd", "Odd", "maybe"), prod("hid", "Hid", status="hidden"), prod("held", "Held", status="held"), prod("lim", "Lim", "limited")])
        self.assertEqual(social_draft.build_today(c, NOON), {"draft": True, "caption": caption("Ok, Lim")})
        none = refused("No products were marked Available today or Limited in today's shelf check.")
        self.assertEqual(social_draft.build_today(content([prod("old", on="2026-11-23"), prod("no", available="no")]), NOON), none)
        self.assertEqual(social_draft.build_today(content([]), NOON), none)

    def test_cap_twelve_then_and_more(self):
        """Exactly 12 names has no tail; 13 gives the first 12 in site order then `and more`; unnamed products do not use the cap.
        Bug caught: an off-by-one cap, a tail on exactly 12, or hidden products consuming slots."""
        names = [f"Product {i:02}" for i in range(13)]
        many = [prod(f"p{i:02}", n) for i, n in enumerate(names)]
        many.insert(3, prod("gone", "Gone", status="hidden"))  # a hidden entry sits among them and uses no slot
        self.assertEqual(social_draft.build_today(content(many[:1]), NOON)["caption"], caption("Product 00"))
        self.assertEqual(social_draft.build_today(content(many[:13]), NOON)["caption"], caption(", ".join(names[:12])))  # 12 named + hidden
        self.assertEqual(social_draft.build_today(content(many), NOON)["caption"], caption(", ".join(names[:12]) + ", and more"))

    def test_check_must_be_pacific_today_never_older_or_future(self):
        """A check one, seven or eight days old, or dated tomorrow, is never posted as today's: the reply names the check day and asks for a new
        one; a missing check says so; a malformed one is unreadable; Pacific (not UTC) decides the day. Bug caught: a recent check treated as
        today's, or a UTC date used near Pacific midnight."""
        p = [prod("a", "Apple", on="2026-11-17")]
        for check, words in (("2026-11-23", "Monday, November 23"), ("2026-11-17", "Tuesday, November 17"), ("2026-11-16", "Monday, November 16"),
                             ("2026-11-25", "Wednesday, November 25")):
            with self.subTest(check=check):
                self.assertEqual(social_draft.build_today(content(p, check), NOON), refused(f"Your last shelf check was {words}{SEND}"))
        self.assertEqual(social_draft.build_today(content(p, None), NOON), refused("Your last shelf check was not recorded" + SEND))
        for bad in ("2026-11-31", "11/24/2026", 5, None, ""):  # present but not a real day
            with self.subTest(bad=bad):
                c = content(p)
                c.store["selection_checked_on"] = bad
                self.assertEqual(social_draft.build_today(c, NOON), refused("cannot read content"))
        late = content([prod("a", "Apple")])  # 2026-11-24 23:30 PST is already 2026-11-25 in UTC
        self.assertTrue(social_draft.build_today(late, datetime.fromisoformat("2026-11-25T07:30:00+00:00"))["draft"])
        self.assertEqual(social_draft.build_today(late, datetime.fromisoformat("2026-11-25T08:30:00+00:00"))["reason"],
                         f"Your last shelf check was Tuesday, November 24{SEND}")  # 00:30 PST on the 25th
        self.assertTrue(social_draft.build_today(late, datetime.fromisoformat("2026-11-24T23:30:00-08:00"))["draft"])

    def test_shapes_tags_controls_and_length(self):
        """Unreadable shapes are `cannot read content`; only emitted names and the store lines are checked; a # or @ (any form) is refused, never
        rewritten, and unsafe text in a product that is not named never leaks or blocks. Bug caught: a traceback, a stripped hashtag, or a
        refusal caused by a product the caption does not mention."""
        for bad in (Content(products=[], makers={}, community={}, store=[]), Content(products={}, makers={}, community={}, store=dict(STORE)),
                    Content(products=[prod("a"), "x"], makers={}, community={}, store={**STORE, "selection_checked_on": DAY})):
            self.assertEqual(social_draft.build_today(bad, NOON), refused("cannot read content"))
        for name in ("", " ", None, 7, "two\nlines", "bell\x07"):
            with self.subTest(name=name):
                self.assertEqual(social_draft.build_today(content([prod("a", "Ok"), {**prod("b"), "name": name}]), NOON), refused("product record incomplete"))
        for field in ("name", "streetAddress", "town"):
            for value in (None, "", "x\ny"):
                with self.subTest(field=field, value=value):
                    self.assertEqual(social_draft.build_today(content([prod("a")], **{field: value}), NOON), refused("store record incomplete"))
        tagged = refused("free text has a hashtag or account name")
        for mark in ("#", "@", "\uff03", "\uff20", "\ufe5f", "\ufe6b"):
            with self.subTest(mark=mark):
                self.assertEqual(social_draft.build_today(content([prod("a", f"Sale {mark}one")]), NOON), tagged)
                self.assertEqual(social_draft.build_today(content([prod("a")], town=f"Bay {mark}x"), NOON), tagged)
        self.assertTrue(social_draft.build_today(content([prod("a", "Fish # 1 @ noon")]), NOON)["draft"])  # isolated marks
        unsafe = content([prod("a", "Apple"), prod("b", "#bad", "no"), prod("c", "x\ny", status="hidden", description="@evil #x")])
        self.assertEqual(social_draft.build_today(unsafe, NOON), {"draft": True, "caption": caption("Apple")})
        room = social_draft.MAX_CAPTION - len(caption(""))
        self.assertEqual(len(social_draft.build_today(content([prod("a", "x" * room)]), NOON)["caption"]), social_draft.MAX_CAPTION)
        self.assertEqual(social_draft.build_today(content([prod("a", "x" * (room + 1))]), NOON), refused("caption too long"))
        self.assertEqual(social_draft.build_today(content([prod(f"p{i}", "y" * 300) for i in range(13)]), NOON), refused("caption too long"))


class TodayCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        docs = (("products", {"products": [prod("a", "Apple")]}), ("makers", {"makers": {}}), ("community", {}),
                ("store", {**STORE, "selection_checked_on": DAY}))
        for name, doc in docs:
            (self.dir / f"{name}.json").write_text(json.dumps({"schemaVersion": 1, **doc}), "utf-8")

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try: code = social_draft.main(list(argv), self.dir, self.dir)
            except SystemExit as exc: code = exc.code
        return code, out.getvalue()

    def test_cli_exclusive_json_and_refusals(self):
        """--today is one more exclusive mode: exit 0 with the caption JSON, 1 with a refusal, 2 for a conflict or a naive --now; files unchanged.
        Bug caught: --today accepted beside another mode, a naive --now guessed in the host zone, or content rewritten."""
        before = {p.name: p.read_bytes() for p in self.dir.iterdir()}
        code, out = self.run_cli("--today", "--now", "2026-11-24T12:00:00-08:00")
        self.assertEqual((code, json.loads(out)), (0, {"draft": True, "caption": caption("Apple")}))
        self.assertEqual(self.run_cli("--today", "--now", "2026-11-24T20:00:00Z")[0], 0)
        code, out = self.run_cli("--today", "--now", "2026-11-25T12:00:00-08:00")
        self.assertEqual((code, json.loads(out)["reason"]), (1, f"Your last shelf check was Tuesday, November 24{SEND}"))
        for argv in (("--today", "--now", "2026-11-24T12:00:00"), ("--today", "apple"), ("--today", "--notice"), ("--today", "--hike", "x"),
                     ("--today", "--maker", "k"), ("--today", "--recap", "x"), ("--today", "--hike"), ()):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_cli(*argv)[0], 2)
        (self.dir / "store.json").write_text("{not json", "utf-8")
        before["store.json"] = b"{not json"
        code, out = self.run_cli("--today", "--now", "2026-11-24T12:00:00-08:00")
        self.assertEqual((code, json.loads(out)), (1, refused("cannot read content")))
        self.assertEqual({p.name: p.read_bytes() for p in self.dir.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
