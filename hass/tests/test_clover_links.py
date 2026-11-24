"""HASS-LINK: exact-name link suggestions, the owner's one-yes `link all`, `link X to <SKU>`, `unlink X` and `stock yes|no <code>`.
Fixtures only: the synthetic #571 till cache, a temp writer folder, a mocked stock_site.approve/decline. No token, network or editor call.
Run: python3 -m unittest discover -s hass/tests -p 'test_clover_links.py' -v
"""
import json
import stat
import types
from datetime import timedelta
from unittest import mock

from hass import conversation, editor, stock_site
from hass.clover import cache, chat, cli, links, reports
from hass.clover.config import from_settings
from hass.tests import test_stock_site as ss
from hass.tests.test_clover_chat import BLOCK, seed, strict
from hass.tests.test_clover_cli import CliCase, T0
from hass.tests.test_conversation import CHAT, OWNER, STRANGER, ConversationTestCase

GROUP = "chat-fixture;+;group"
P = lambda pid, name, status="active": {"id": pid, "name": name, "status": status}  # noqa: E731
PRODUCTS = {"products": [P("avocado", "Hass avocado"), P("oil", "Sunshine  olive OIL"), P("eggs-1", "Eggs, dozen"), P("eggs-2", "eggs, dozen"),
                         P("tomato", "Heirloom tomato"), P("lemons", "Lemons"), P("honey", "Old honey jar", "hidden")]}
STOCK = {"stk-000000000001": "open", "stk-000000000002": "stale"}


class Fixture:
    """A till cache, local products and a TillDesk that can change the till (owners only), all under a temp state."""

    def stage(self, state, wt):
        seed(state)
        (wt / "hass/content").mkdir(parents=True, exist_ok=True)
        (wt / "hass/content/products.json").write_text(json.dumps(PRODUCTS))
        (state / "config.json").write_text(json.dumps({"worktree": str(wt)}))
        engine = chat.BundleEngine(state, from_settings(BLOCK), lambda token: None, mike=(OWNER, CHAT))
        self.desk, self.wt, self.state = chat.TillDesk(str(state), BLOCK, engine=engine), wt, state

    def ask(self, text, sender=OWNER, chat=CHAT):
        intent = self.desk.parse(text)
        self.assertIsNotNone(intent, text)   # claimed by the till desk, never the interpreter
        return strict(self.desk.answer(intent, T0, sender=sender, chat=chat, worktree=lambda: self.wt))

    def links(self):
        path = self.state / "clover/links.json"
        return json.loads(path.read_text()) if path.exists() else None


class LinkTests(Fixture, CliCase):
    def setUp(self):
        super().setUp()
        self.stage(self.state, self.root / "writer")

    def suggest(self):
        code, out, stdout = self.run_cli("link", "suggest")
        self.assertEqual(code, 0)
        return out, stdout

    def test_suggest_links_exact_names_only_and_lists_the_rest_unlinked(self):
        # Contract: a looser (fuzzy, hidden-site or clashing) match is never suggested. Bug: "Heirloom tomato" joins "Heirloom tomatoes".
        snapshot, _ = cache.read(self.state, cache.identity_of(from_settings(BLOCK)))
        pairs, clashes, site_only, till_only = self.distinct(snapshot, PRODUCTS)
        self.assertEqual(pairs, {"avocado": {"cloverId": "FAKEITEM00002"}, "oil": {"cloverId": "FAKEITEM00001", "sku": "AS-PAN-SUNSHINE-OLIVE-OIL-01"}})
        self.assertEqual((clashes, site_only), (["Eggs, dozen (eggs-1)", "eggs, dozen (eggs-2)", "Eggs, dozen (EGG12)"], ["Heirloom tomato", "Lemons"]))   # the lone till item is listed too
        self.assertEqual(till_only, ["Heirloom tomatoes", "Market special (ring up price)", "Old honey jar"])
        self.assertEqual(links.suggest(snapshot, PRODUCTS, {"avocado": {"cloverId": "FAKEITEM00002"}})[0].keys(), {"oil"})   # linked ones are left alone

    def distinct(self, snapshot, content, links_=None):
        """Contract: no two labels in any list suggest() returns are equal. Run over every fixture output in this file."""
        found = links.suggest(snapshot, content, links_ or {})
        for rows in found[1:]:
            self.assertEqual(len(rows), len(set(rows)), rows)
        return found

    def test_every_one_sided_item_is_listed_and_same_name_twins_carry_their_ids(self):
        # Contract: nothing left over is silently dropped. Bug: only the first of two same-name unmatched items was listed (ps[0] / its[0]).
        till = lambda i, name, sku="": types.SimpleNamespace(id=i, name=name, sku=sku)   # noqa: E731
        snapshot = types.SimpleNamespace(items=[till("T1", "Quince", "Q-1"), till("T2", "quince"), till("T3", "Plum"), till("T4", "Fig"), till("T5", "fig")])
        content = {"products": [P("s1", "Pear"), P("s2", "pear"), P("s3", "Plum"), P("s4", "Fig"), P("s5", "Kale")]}
        pairs, clashes, site_only, till_only = self.distinct(snapshot, content)
        self.assertEqual(pairs, {"s3": {"cloverId": "T3"}})
        self.assertEqual(site_only, ["Kale", "Pear (s1)", "pear (s2)"])             # (a) both site-only twins, each with its product id
        self.assertEqual(till_only, ["Quince (Q-1)", "quince (T2)"])                 # (b) both till-only twins, by SKU or else item id
        self.assertEqual(clashes, ["Fig (s4)", "Fig (T4)", "fig (T5)"])            # one site product, two till items: neither is linked or lost

    def test_same_name_twins_with_one_sku_or_a_sku_equal_to_an_id_still_get_distinct_labels(self):
        # Contract: every label in a same-name group is unique. Bug: two twins sharing SKU "Q" were both labelled "Quince (Q)".
        till = lambda i, name, sku="": types.SimpleNamespace(id=i, name=name, sku=sku)   # noqa: E731
        snapshot = types.SimpleNamespace(items=[till("T1", "Quince", "Q"), till("T2", "quince", "Q"), till("T3", "Leek", "L"), till("T4", "leek", " l "),
                                                till("T5", "Leek", "L-5"), till("T6", "Fig", "F"), till("T7", "fig", "F"), till("T8", "Kiwi", "T9"), till("T9", "kiwi")])
        pairs, clashes, site_only, till_only = self.distinct(snapshot, {"products": [P("s1", "Fig")]})
        self.assertEqual((pairs, site_only), ({}, []))
        self.assertEqual(till_only, ["Kiwi (T8)", "kiwi (T9)",                         # a SKU that is another item's id is not used
                                     "Leek (T3)", "leek (T4)", "Leek (L-5)",         # (b) the shared pair shows ids, the unique SKU may show
                                     "Quince (T1)", "quince (T2)"])                  # (a) one shared SKU: both item ids
        self.assertEqual(clashes, ["Fig (s1)", "Fig (T6)", "fig (T7)"])              # (c) the same collision in the clash list

    def test_clash_labels_are_unique_across_site_and_till_and_a_lone_till_item_is_listed(self):
        # Contract: every label in a same-name group is distinct over BOTH sides, and every member of a clash group is listed.
        # Bug: site id "s1" and a till SKU "s1" both gave "Fig (s1)"; one till item beside two site products was left out of the list.
        till = lambda i, name, sku="": types.SimpleNamespace(id=i, name=name, sku=sku)   # noqa: E731
        snapshot = types.SimpleNamespace(items=[till("T1", "Fig", "s1"), till("T2", "Fig"), till("T3", "Plum", "p"), till("T4", "Date", "d"), till("T5", "Pear")])
        content = {"products": [P("s1", "Fig"), P("p", "Plum"), P("p2", "plum"), P("d1", "Date"), P("d2", "date"), P("pear", "Pear")]}
        pairs, clashes, site_only, till_only = self.distinct(snapshot, content)
        self.assertEqual((pairs, site_only, till_only), ({"pear": {"cloverId": "T5"}}, [], []))   # 1:1 unchanged
        self.assertEqual(clashes, ["Date (d1)", "date (d2)", "Date (d)",              # two site products, ONE till item (its SKU): it is listed
                                   "Fig (site s1)", "Fig (till T1)", "Fig (T2)",     # the colliding pair is prefixed by side, the till one by item id
                                   "Plum (site p)", "plum (p2)", "Plum (till T3)"])  # a till SKU equal to a site id collides too

    def snap(self):
        return cache.read(self.state, cache.identity_of(from_settings(BLOCK)))[0]

    def refused(self, content, links_):
        """suggest(), draft() and apply() all refuse with the one fixed text, which echoes no value. A good draft is waiting first, so apply()
        reaches the check; it and the link table stay exactly as they were."""
        snapshot, folder = self.snap(), self.state / "clover"
        code = links.draft(self.state, snapshot, PRODUCTS, {})[0]
        (folder / "reports" / "link-suggest.md").unlink()   # a refused draft() must not recreate the list either
        before = {p.name: p.read_bytes() for p in folder.rglob("*") if p.is_file()}
        for call in (lambda: links.suggest(snapshot, content, links_), lambda: links.draft(self.state, snapshot, content, links_),
                     lambda: links.apply(self.state, code, snapshot, content, links_)):
            with self.assertRaises(ValueError) as caught:
                call()
            self.assertEqual(str(caught.exception), "link inputs")
        self.assertEqual({p.name: p.read_bytes() for p in folder.rglob("*") if p.is_file()}, before)   # no new draft, list or link table; the old draft stays
        self.assertIsNone(self.links())

    def test_malformed_catalog_refused_before_any_write(self):
        # Contract: a catalog of the wrong shape is one plain refusal before any file is written. Bug: KeyError / TypeError / AttributeError
        # tracebacks, and a product whose name is None listed as the word "None".
        cases = {"no id": [{"name": "Blue mug", "status": "active"}], "id not text": [P(5, "Blue mug")], "name missing": [{"id": "mug", "status": "active"}],
                 "name None": [P("mug", None)], "name not text": [P("mug", 7)], "product is text": ["x"], "product is None": [None],
                 "bad one among good": [P("tea", "Tea"), {"name": "Mug"}]}
        for label, products in cases.items():
            with self.subTest(label):
                self.refused({"products": products}, {})
        for label, content in {"products None": {"products": None}, "products a dict": {"products": {}}, "products text": {"products": "x"},
                               "no products": {}, "content a list": [], "content None": None}.items():
            with self.subTest(label):
                self.refused(content, {})

    def test_links_not_a_dict_refused(self):
        # Contract: the link table is a dict of product id to link. Bug: a list was accepted and used as if it were the table.
        for label, table in {"list": [], "list of ids": ["avocado"], "None": None, "text": "avocado"}.items():
            with self.subTest(label):
                self.refused(PRODUCTS, table)

    def test_healthy_catalog_unchanged(self):
        # Control: the shape check changes nothing for a good catalog - the pairing, the clash and one-sided lists and their labels as before.
        snapshot = self.snap()
        found = links.suggest(snapshot, PRODUCTS, {})
        self.assertEqual(found, ({"avocado": {"cloverId": "FAKEITEM00002"}, "oil": {"cloverId": "FAKEITEM00001", "sku": "AS-PAN-SUNSHINE-OLIVE-OIL-01"}},
                                 ["Eggs, dozen (eggs-1)", "eggs, dozen (eggs-2)", "Eggs, dozen (EGG12)"], ["Heirloom tomato", "Lemons"],
                                 ["Heirloom tomatoes", "Market special (ring up price)", "Old honey jar"]))
        self.assertEqual(links.draft(self.state, snapshot, PRODUCTS, {})[1:], found)
        self.assertEqual(links.suggest(snapshot, {"products": []}, {})[:3], ({}, [], []))   # an empty catalog is healthy, not malformed
        self.assertEqual(links.suggest(snapshot, {"products": [P("mug", "Blue mug", "hidden"), {"id": "x", "name": "X"}]}, {})[0], {})   # status stays optional

    def test_cli_saves_one_private_draft_and_a_private_list_and_prints_counts_only(self):
        out, stdout = self.suggest()
        self.assertEqual({k: v for k, v in out.items() if k != "code"}, {"result": "ok", "matches": 2, "sameName": 3, "siteOnly": 2, "tillOnly": 3,
                                                                          "asOf": "2026-11-10T20:00:00+00:00"})
        for name in ("avocado", "Eggs", "tomato", "Hass"):
            self.assertNotIn(name, stdout)
        folder = self.state / "clover"
        self.assertIsNone(self.links())   # a suggestion links nothing
        for path in (folder / links.DRAFT, folder / "reports/link-suggest.md"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertIn(f"Will link: link all {out['code']} (2)", (folder / "reports/link-suggest.md").read_text())

    def test_one_yes_writes_every_link_and_the_mismatch_report_reads_it_unchanged(self):
        # Contract: all-or-nothing under one code, in the shape reports.read_inputs already reads. Bug: only the first pair is written.
        code = self.suggest()[0]["code"]
        self.assertEqual(self.ask(f"link all {code}"), "Linked 2 website items to till items. No website word was changed.")
        self.assertEqual(sorted(self.links()), ["avocado", "oil"])
        self.assertEqual(stat.S_IMODE((self.state / "clover/links.json").stat().st_mode), 0o600)
        snapshot, _ = cache.read(self.state, cache.identity_of(from_settings(BLOCK)))
        sections = reports.till_vs_site(snapshot, *reports.read_inputs(self.state, self.wt))["sections"]
        self.assertEqual((sections["Broken links"], sections["Different names"]), ([], []))
        self.assertNotIn("Hass avocado (avocado)", sections["Site items without a till link"])
        self.assertIn("Unlinked", self.ask("unlink hass avocado"))
        self.assertEqual(sorted(self.links()), ["oil"])
        self.assertEqual(self.ask(f"link all {code}"), chat.LINK_NO["unknown"])   # the draft is spent: the same code never writes twice

    def test_a_changed_cache_or_a_changed_pair_makes_the_draft_stale_and_writes_nothing(self):
        # Bug: the code is accepted against a till or website that changed after Mike was shown the list.
        code = self.suggest()[0]["code"]
        seed(self.state, now=T0 + timedelta(minutes=15))
        self.assertEqual(self.ask(f"link all {code}"), chat.LINK_NO["stale"])
        self.assertIsNone(self.links())
        self.assertEqual(self.ask("link all 00000000"), chat.LINK_NO["unknown"])
        seed(self.state)
        code = self.suggest()[0]["code"]
        (self.wt / "hass/content/products.json").write_text(json.dumps({"products": [P("avocado", "Hass avocados"), *PRODUCTS["products"][1:]]}))
        self.assertEqual(self.ask(f"link all {code}"), chat.LINK_NO["stale"])
        self.assertIsNone(self.links())

    def test_a_wrong_sender_or_a_group_changes_nothing(self):
        code = self.suggest()[0]["code"]
        for text in (f"link all {code}", "link lemons to egg12", "unlink avocado", "stock yes stk-000000000001"):
            for sender, room in ((STRANGER, CHAT), (OWNER, GROUP), (STRANGER, GROUP)):
                with self.subTest(text=text, sender=sender, room=room), mock.patch.object(stock_site, "approve") as approve:
                    self.assertEqual(self.ask(text, sender, room), chat.NOT_OWNER)
                    approve.assert_not_called()
        self.assertIsNone(self.links())
        self.assertEqual(self.ask(f"link all {code}"), "Linked 2 website items to till items. No website word was changed.")   # the draft was not spent

    def test_link_to_a_sku_and_unlink_are_exact_and_never_touch_the_site(self):
        # Contract: linking sets no website word, so the editor is never called. Bug: a link command also publishes a stock word.
        with mock.patch.object(editor, "prepare", side_effect=AssertionError), mock.patch.object(editor, "apply", side_effect=AssertionError):
            self.assertIn("exactly one website item", self.ask("link eggs, dozen to egg12"))   # two products share that name
            self.assertEqual(self.ask("link eggs-2 to EGG12"), "Linked eggs-2 to SKU EGG12. No website word was changed.")
            self.assertEqual(self.links(), {"eggs-2": {"cloverId": "FAKEITEM00003", "sku": "EGG12"}})
            for text in ("link eggs-1 to EGG12", "link eggs-2 to AS-PAN-SUNSHINE-OLIVE-OIL-01", "link honey to egg12"):
                self.assertIn("nothing was changed", self.ask(text), text)   # a SKU taken, a product already linked, a hidden product
            self.assertIsNone(self.desk.parse("link the lemons to the hike page"))   # not a till SKU: not claimed, the usual handling goes on
            self.assertEqual(self.ask("unlink lemons"), "lemons is not linked, so nothing was changed.")
            self.assertIn("Unlinked", self.ask("unlink eggs-2"))
        self.assertEqual(self.links(), {})

    def test_a_till_item_held_by_sku_through_an_old_link_is_never_offered_or_linked_again(self):
        # Contract: "taken" means what mapper.match resolves (stored id, else the one till item with the stored SKU). Bug: only a current
        # id counted, so a recreated till item (new id, same SKU) was offered to a second product and broke the first product's link.
        oil_sku = "AS-PAN-SUNSHINE-OLIVE-OIL-01"
        snapshot, _ = cache.read(self.state, cache.identity_of(from_settings(BLOCK)))
        recreated = {"lemons": {"cloverId": "OLD1", "sku": oil_sku}}   # OLD1 is gone from the till; the oil item now holds that SKU
        self.assertEqual(links.reserved(snapshot.items, recreated), {"FAKEITEM00001"})
        pairs, _, site_only, till_only = self.distinct(snapshot, PRODUCTS, recreated)
        self.assertEqual(pairs, {"avocado": {"cloverId": "FAKEITEM00002"}})   # oil is not offered
        self.assertNotIn("Sunshine olive oil", till_only)
        self.assertIn("Sunshine  olive OIL", site_only)
        links.write(links.table(self.state), recreated)
        self.assertEqual(self.ask(f"link oil to {oil_sku}"), "That needs one website item and one till SKU, both not linked yet, so nothing was changed. Say unlink first to move a link.")
        self.assertEqual(self.links(), recreated)   # no conflicting link was written
        content, written = reports.read_inputs(self.state, self.wt)
        self.assertNotIn("lemons", reports.till_vs_site(snapshot, content, written)["sections"]["Broken links"])
        # A link whose id and SKU match no till item holds nothing; a current id still holds its item.
        self.assertEqual(links.reserved(snapshot.items, {"lemons": {"cloverId": "OLD1", "sku": "NOPE"}, "x": {"cloverId": "FAKEITEM00002"}}), {"FAKEITEM00002"})

    def test_help_lists_the_link_and_stock_words(self):
        for word in ("link all <code>", "unlink Sunshine olive oil", "stock yes <code>", "stock no <code>"):
            self.assertIn(word, chat.HELP)


class StockWordTests(Fixture, CliCase):
    def setUp(self):
        super().setUp()
        self.stage(self.state, self.root / "writer")
        queue = stock_site.StockSite(self.state, None, None)
        queue.data = dict(counts={}, pending={}, inflight=None, asOf="", itemCount=0, sets={code: dict(
            hash=stock_site.digest({}), words={}, approved_by=None, approved_at=None, state=state, at="2026-11-10", summary="x") for code, state in STOCK.items()})
        queue.save()

    def test_stock_yes_and_no_call_approve_and_decline_once_for_an_open_code_only(self):
        open_code = "stk-000000000001"
        with mock.patch.object(stock_site, "approve", return_value=True) as approve, mock.patch.object(stock_site, "decline", return_value=True) as decline:
            self.assertIn("will go up", self.ask(f"stock yes {open_code}"))
            self.assertIn("dropped", self.ask(f"stock no {open_code}"))
            approve.assert_called_once_with(str(self.state), open_code, "owner")
            decline.assert_called_once_with(str(self.state), open_code, "owner")
            for text in ("stock yes stk-000000000002", "stock no stk-000000000002", "stock yes stk-999999999999", "stock no nonsense"):
                self.assertEqual(self.ask(text), chat.STOCK_NO, text)   # stale and unknown codes make no call
            self.assertEqual((approve.call_count, decline.call_count), (1, 1))

    def test_a_code_already_approved_is_not_approved_twice(self):
        # Bug: a repeated yes calls approve again. The real approve is used, so the file itself shows the first one.
        self.assertIn("will go up", self.ask("stock yes stk-000000000001"))
        self.assertEqual(stock_site.StockSite(self.state, None, None).load()["sets"]["stk-000000000001"]["approved_by"], "owner")
        self.assertEqual(self.ask("stock yes stk-000000000001"), chat.STOCK_NO)


class ChatDispatch(Fixture, ConversationTestCase):
    def test_the_conversation_hands_the_link_words_to_the_desk_not_the_interpreter(self):
        with mock.patch.object(conversation.Outbox, "strict", True):
            self.stage(self.repo.state, self.repo.wt)
            self.conv.till = self.desk
            seen = []
            self.interp.interpret = lambda text, *a, **k: seen.append(text)
            for who, text in ((OWNER, "link all 00000000"), (STRANGER, "link all 00000000")):
                self.say(text, sender=who, chat=CHAT if who == OWNER else "chat-stranger")
            self.assertEqual((seen, self.replies()), ([], [chat.LINK_NO["unknown"]]))


class NewlyLinked(ss.StockCase):
    locals().update({name: None for name in dir(ss.StockCase) if name.startswith("test")})   # only this contract, not StockCase's own tests

    def test_a_link_written_by_links_py_is_new_to_stock_site_and_sets_no_word(self):
        # Contract: LINK writes the table stock_site already reads; the first read after it is "newly linked" (one preview, no release).
        pid, table = self.ids[0], links.table(self.repo.state)
        link = self.links.pop(pid)
        self.write_links()
        self.pull()
        self.runq()
        self.assertNotIn(pid, self.data()["counts"])
        self.links[pid] = link
        links.write(table, self.links)
        self.pull(**{pid: 0})
        self.assertEqual(self.runq(), "held")
        self.assertTrue(self.data()["pending"][pid]["new"])
        summary = next(iter(self.sets().values()))["summary"]
        self.assertTrue(summary.startswith("First stock sync / stock set: 1 words (1 Sold out, 0 Limited, 0 Available today)"), summary)
        self.assertEqual((self.live.calls, json.loads(self.products_path.read_text())["products"][0].get("available")), ([], "yes"))
