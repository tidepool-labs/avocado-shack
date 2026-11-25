"""Offline contracts for the exact reverse of a till inventory change (HCI-10). Fake till only; sockets are patched."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from hass.clover import bundle, drafts, inventory_undo as undo, links
from hass.clover.apply import ApplyEngine
from hass.clover.client import CloverClient, CloverWriteClient
from hass.clover.config import from_settings
from hass.clover.credential import Token
from hass.clover.mapper import SiteProduct, parse_item
from hass.tests.clover_fake import FakeClover
from hass.tests.test_clover_client import FAKE_TOKEN, NoNetwork

MERCHANT = "FAKEMERCH0001"
SEED = "FAKESEED00001"
PRODUCT = "blue-mug"
CATEGORY = "FAKECAT000001"
CHANGED_AGAIN = "The item was changed again; I will not undo over a newer value."


def yes_line(code):
    return f"Reply yes {code} to do this, or no {code} to drop it. Nothing changes until you say yes."


def site_product(word):
    return SiteProduct(PRODUCT, "Blue mug", "", None, "general", "", word, "active")


class FakeSite:
    """The website side of the bundle saga: it numbers each prepared change and says whether it went live (as `test_item_both.Site`)."""

    def __init__(self):
        self.settings, self.conv, self.drafts, self.live = {}, None, {}, set()

    def stopped(self):
        return False

    def prepare(self, ops):
        cid = f"chg-{len(self.drafts)}"
        self.drafts[cid] = list(ops)
        return {"result": "ok", "draft": {"change_id": cid, "draft_hash": "fixture-hash"}}

    def apply(self, cid, digest, chat):
        self.live.add(cid)
        return {"result": "applied"}

    def went_live(self, cid):
        return cid in self.live


SITE_OPS = [{"op": "product.set_availability", "args": {"id": PRODUCT, "available": "yes"}}]   # what a counted create tells the site


class Rig:
    """A fake till (one seeded item counted 12), the real apply engine and bundle saga on a temp state folder: the reverse is run
    against what really happened, not against a hand-written journal."""

    def __init__(self, case):
        self.case = case
        tmp = TemporaryDirectory()
        case.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        write_token = self.root / "fake-write"
        write_token.touch(mode=0o600)
        write_token.write_text(FAKE_TOKEN, encoding="utf-8")
        self.cfg = from_settings({"environment": "sandbox", "merchantId": MERCHANT, "tokenFile": str(self.root / "fake-read"),
                                  "writeTokenFile": str(write_token), "writes": True, "liveApproved": True})
        seed = {"id": SEED, "name": "Green bowl", "sku": "AS-GEN-GREEN-BOWL-01", "price": 2000, "priceType": "FIXED",
                "hidden": False, "modifiedTime": 100, "itemStock": {"item": {"id": SEED}, "quantity": 12, "modifiedTime": 100}}
        self.fake = FakeClover(MERCHANT, [seed], [{"id": CATEGORY, "name": "Goods"}])
        self.reader = CloverClient(MERCHANT, Token(FAKE_TOKEN), self.fake, min_interval=0, max_retries=0)
        self.writer = CloverWriteClient(MERCHANT, Token(FAKE_TOKEN), self.fake, min_interval=0, max_retries=0)
        self.owner = {"sender": "fixture-owner", "chat": "fixture-private"}
        self.engine = ApplyEngine(self.root, self.cfg, lambda token: CloverWriteClient(MERCHANT, token, self.fake, min_interval=0,
                                                                                       max_retries=0), mike=tuple(self.owner.values()))
        self.journal = bundle.BundleJournal(self.root)
        self.site = FakeSite()

    def link_writer(self, product_id, clover_id, sku):
        links.write(links.table(self.root), {**self.links(), product_id: {"cloverId": clover_id, "sku": sku}})

    def links(self):
        path = links.table(self.root)
        return json.loads(path.read_text("utf-8")) if path.exists() else {}

    def applied(self, draft, link=None, site_ops=()):
        """Propose and apply one bundle, the way the owner's one yes does; returns the journal row."""
        code, _ = bundle.propose(site_ops=site_ops, till_draft=draft, link=link, journal=self.journal, engine=self.engine, site=self.site,
                                 **self.owner)
        state, _ = bundle.apply(code, journal=self.journal, engine=self.engine, site=self.site, link_writer=self.link_writer,
                                now=self.engine.clock(), **self.owner)
        self.case.assertEqual(state, "done")
        return self.journal.get(code)

    def create_mug(self, quantity=30, site_ops=SITE_OPS):
        draft = drafts.build_create_counted("Blue mug", "14.00 each", None, quantity, [], self.cfg)
        return self.applied(draft, {"product_id": PRODUCT, "sku": draft.after["sku"]}, site_ops)

    def set_count(self, quantity, link=None):
        return self.applied(drafts.build_set_stock(self.item(SEED), quantity, self.cfg), link)

    def item(self, item_id):
        return parse_item(self.reader.get_item(item_id))

    def stock(self, item_id):
        return self.reader.get_item(item_id)["itemStock"]["quantity"]

    def reverse(self, row, site=None, **kw):
        return undo.reverse(row, self.item(row["clover_id"]), site, self.links(), **kw)

    def run_till_half(self, rev):
        code, _ = self.engine.offer(rev.till, **self.owner)
        return self.engine.handle("yes " + code, **self.owner)

    def methods(self):
        return [method for method, _, _ in self.fake.log]

    def writes(self):
        return [entry for entry in self.fake.log if entry[0] in ("POST", "PUT")]


class InventoryUndoTests(NoNetwork):
    def setUp(self):
        super().setUp()
        self.rig = Rig(self)

    def test_c1_reverse_parts(self):
        # C1: a reverse that hides but forgets the link or the website word, or rewrites a count instead of putting back the journalled
        # old one, leaves a dead link, a wrong site word or a changed count behind.
        rig = self.rig
        row = rig.create_mug()
        item_id, entry = row["clover_id"], row["undo_result"]
        rev = rig.reverse(row, site_product("yes"))
        self.assertIsInstance(rev, undo.Reverse)
        self.assertEqual((rev.till.kind, rev.till.item_id, rev.till.undo_of), ("set_hidden", item_id, entry["change_id"]))
        self.assertEqual(rev.till.requests, ({"method": "POST", "path": f"/items/{item_id}", "json": {"hidden": True}},))
        self.assertEqual(rev.unlink, {"product_id": PRODUCT, "clover_id": item_id, "sku": entry["after"]["sku"]})
        # the REAL journal row: the website half is recorded as the bundle's own change, not in the till result, and the reverse puts
        # that whole change back (a reverse that read only `undo_result` would hide the item and leave the website word changed)
        self.assertNotIn("site", entry["after"])
        self.assertEqual((row["site"], row["bundle"]["site_ops"]), ("live", SITE_OPS))
        self.assertEqual(rev.site_ops, ({"op": "history.revert", "args": {"changeId": row["change_id"]}},))
        self.assertEqual(rev.till.site_ops, ())   # the engine verifies only what it wrote
        self.assertTrue(rev.hides)
        # it is the very inverse the bundle saga's own undo drafts for that change
        saga = Rig(self)
        saga_row = saga.create_mug()
        code, _ = bundle.undo(saga_row["bundle"]["code"], journal=saga.journal, engine=saga.engine, site=saga.site, **saga.owner)
        self.assertEqual(saga.site.drafts[saga.journal.get(code)["change_id"]], list(saga.reverse(saga_row).site_ops))
        # a bundle with no website half has no website part, and one whose website half never ran has nothing to put back
        plain = Rig(self).create_mug(site_ops=())
        self.assertEqual(rig.reverse(plain).site_ops, ())
        self.assertEqual(rig.reverse({**row, "site": "pending"}).site_ops, ())
        # a website half the journal cannot place is refused (never guessed); the site's own answer settles it
        unsure = {**row, "site": "not-confirmed"}
        refused = rig.reverse(unsure)
        self.assertIsInstance(refused, undo.Refusal)
        self.assertEqual(refused.reason, undo.SITE_UNSURE)
        self.assertEqual(rig.reverse(unsure, went_live=lambda cid: cid == row["change_id"]).site_ops, rev.site_ops)
        self.assertEqual(rig.reverse(unsure, went_live=lambda cid: False).site_ops, ())
        # a count change: the old count, from drafts.build_undo, with no link part
        counted = rig.set_count(30)
        rev = rig.reverse(counted)
        self.assertEqual((rev.till.kind, rev.till.requests[0]["json"], rev.hides, rev.unlink), ("set_stock", {"quantity": 12}, False, None))
        self.assertIn("Count: 30 -> 12", rev.parts)

        # a link added to an existing item: the link comes off together with the count part
        other = Rig(self)
        linked = other.set_count(30, {"product_id": "green-bowl", "sku": "AS-GEN-GREEN-BOWL-01"})
        rev = other.reverse(linked)
        self.assertEqual(rev.unlink, {"product_id": "green-bowl", "clover_id": SEED, "sku": "AS-GEN-GREEN-BOWL-01"})
        self.assertEqual(rev.till.requests[0]["json"], {"quantity": 12})
        self.assertTrue(any(part.startswith("Link: removes the link") and "green-bowl" in part for part in rev.parts))
        self.assertNotIn("DELETE", rig.methods() + other.methods())

    def test_c2_refuses_newer(self):
        # C2: undoing over a sale, a price or SKU edit, a hide or any other newer write destroys a value nobody approved to lose; a reverse
        # that only compared the count would miss the price, SKU, hidden and modifiedTime-only cases.
        newer = {
            "count": lambda r, i: r.fake.sell(i, 1),
            "price": lambda r, i: r.writer.write("POST", f"/items/{i}", {"price": 1500}),
            "sku": lambda r, i: r.writer.write("POST", f"/items/{i}", {"sku": "AS-GEN-BLUE-MUG-02"}),
            "hidden": lambda r, i: r.writer.write("POST", f"/items/{i}", {"hidden": True}),
            "modifiedTime": lambda r, i: r.writer.write(
                "POST", "/category_items", {"elements": [{"category": {"id": CATEGORY}, "item": {"id": i}}]}),
        }
        for name, change in newer.items():
            with self.subTest(name):
                case = Rig(self)
                row = case.create_mug()
                change(case, row["clover_id"])
                item = case.item(row["clover_id"])
                before = list(case.fake.log)
                self.assertEqual(undo.reverse(row, item, None, case.links()), undo.Refusal(CHANGED_AGAIN))
                self.assertEqual(case.fake.log, before)   # the reverse sends nothing
                self.assertNotIn("DELETE", case.methods())
        # a counted change that a sale overtook is refused the same way
        row = self.rig.set_count(30)
        self.rig.fake.sell(SEED, 2)
        self.assertEqual(self.rig.reverse(row), undo.Refusal(CHANGED_AGAIN))
        # a link that now joins something else, an item that cannot be found and a bundle that applied nothing are refused too
        row = self.rig.create_mug()
        item = self.rig.item(row["clover_id"])
        self.assertEqual(undo.reverse(row, item, None, {PRODUCT: {"cloverId": "FAKEOTHER0001", "sku": "X"}}), undo.Refusal(CHANGED_AGAIN))
        self.assertIsInstance(undo.reverse(row, None, None, self.rig.links()), undo.Refusal)
        self.assertIsInstance(undo.reverse({**row, "state": "failed"}, item, None, self.rig.links()), undo.Refusal)
        self.assertNotIn("DELETE", self.rig.methods())

    def test_c3_preview_names_all(self):
        # C3: a preview that lists only the hide, calls it a delete, hides that the count record stays, or reuses the first change's code
        # makes the owner say yes to something other than the exact reverse.
        row = self.rig.create_mug()
        rev = self.rig.reverse(row, site_product("yes"))
        text = undo.render(rev, "zz99")
        self.assertEqual(text.split("\n")[-1], yes_line("zz99"))
        self.assertEqual(text.count("zz99"), 2)   # only the one yes line names the new code
        self.assertNotIn(row["bundle"]["code"], text)
        self.assertEqual(len(rev.parts), 3)
        for part in rev.parts:
            self.assertIn(part, text)
        self.assertIn("Register: Blue mug (SKU AS-GEN-BLUE-MUG-01) goes from showing to hidden", text)
        self.assertIn("Link: removes the link between website product blue-mug and this till item", text)
        self.assertIn(f"Website: puts the website back as it was before this change (undoes website change {row['change_id']})", text)
        self.assertIn("hidden, not deleted", text)
        self.assertIn("count record stays", text)
        self.assertIn("still says 30", text)
        self.assertIn("its own code and its own yes", text)
        self.assertNotIn("Delete", text)
        # a count change names the count and does not claim an item was hidden
        plain = undo.render(self.rig.reverse(self.rig.set_count(30)), "ab12")
        self.assertIn("Count: 30 -> 12", plain)
        self.assertIn("Nothing is deleted.", plain)
        self.assertNotIn("hidden", plain)
        self.assertEqual(plain.split("\n")[-1], yes_line("ab12"))

    def test_c4_unlink_after_till(self):
        # C4: unlinking before the till half reads back (or after a failed one) leaves a visible register item with no website link, or
        # a link to an item the owner thinks is gone.
        rig = self.rig
        rev = rig.reverse(rig.create_mug())
        path = links.table(rig.root)
        other = {"other-product": {"cloverId": "FAKEOTHER0001", "sku": "X"}}
        links.write(path, {**rig.links(), **other})
        held = rig.links()
        self.assertIn(PRODUCT, held)
        with mock.patch.object(links, "write", wraps=links.write) as write:
            self.assertEqual(undo.finish(rev, rig.root), "link-kept")   # no word from the till half is not an applied till half
            for status in ("failed", "uncertain", "partial", "intent", "pending"):
                with self.subTest(till=status):
                    self.assertEqual(undo.finish(rev, rig.root, status), "link-kept")
                    self.assertEqual(rig.links(), held)
            # a till write that fails on the fake leaves the link, and the failed write is not repeated
            rig.fake.fail_next(503)
            status = rig.run_till_half(rev)
            self.assertEqual(status, "uncertain")
            self.assertEqual(undo.finish(rev, rig.root, status), "link-kept")
            self.assertEqual(rig.links(), held)
            write.assert_not_called()
        # a link that now joins something else is not ours to remove, even after an applied till half
        links.write(path, {**held, PRODUCT: {"cloverId": "FAKEOTHER0002", "sku": "X"}})
        self.assertEqual(undo.finish(rev, rig.root, "applied"), "link-kept")
        links.write(path, held)
        # the till half reads back applied: now, and only now, the link comes off; the other links stay
        self.assertEqual(rig.run_till_half(rev), "applied")
        self.assertEqual(undo.finish(rev, rig.root, "applied"), "unlinked")
        self.assertEqual(rig.links(), other)
        self.assertEqual(undo.finish(rev, rig.root, "applied"), "link-gone")
        # a reverse with no link has nothing to remove; a link-only reverse has no till half to wait for
        self.assertEqual(undo.finish(undo.Reverse("x", None, None, (), None, (), False, "", "c"), rig.root), "no-link")
        link_only = undo.Reverse("the link", None, None, (), {"product_id": "other-product", "clover_id": "FAKEOTHER0001", "sku": "X"},
                                 (), False, "", "c")
        self.assertEqual(undo.finish(link_only, rig.root), "unlinked")
        self.assertEqual(rig.links(), {})
        self.assertNotIn("DELETE", rig.methods())

    def test_c5_fake_till_scenarios(self):
        # C5: the join. Create x30 then undo, 12 -> 30 then undo, and 12 -> 30 with a sale then undo, on the fake till as it really behaves:
        # a reverse that deleted, dropped the count record, or undid over a sale would pass unit checks and fail here.
        rig = self.rig
        # scenario 1: create Blue mug x30 -> undo: hidden, count 30 still recorded, link gone
        row = rig.create_mug()
        item_id = row["clover_id"]
        self.assertEqual(rig.links()[PRODUCT]["cloverId"], item_id)
        self.assertEqual([i["id"] for i in rig.fake.register_search("Blue mug")], [item_id])
        rev = rig.reverse(row)
        self.assertIsInstance(rev, undo.Reverse)
        self.assertEqual(rig.run_till_half(rev), "applied")
        self.assertEqual(undo.finish(rev, rig.root, "applied"), "unlinked")
        raw = rig.reader.get_item(item_id)
        self.assertIs(raw["hidden"], True)
        self.assertEqual(raw["itemStock"]["quantity"], 30)
        self.assertEqual(rig.fake.register_search("Blue mug"), [])
        self.assertEqual(rig.fake.register_search(raw["sku"]), [])
        self.assertNotIn(PRODUCT, rig.links())
        # scenario 2: set 12 -> 30 -> undo -> 12
        row = rig.set_count(30)
        self.assertEqual(rig.stock(SEED), 30)
        self.assertEqual(rig.run_till_half(rig.reverse(row)), "applied")
        self.assertEqual(rig.stock(SEED), 12)
        # scenario 3: set 12 -> 30, a sale of 2, then undo is refused and nothing is written
        row = rig.set_count(30)
        rig.fake.sell(SEED, 2)
        wrote = rig.writes()
        self.assertEqual(rig.reverse(row), undo.Refusal(CHANGED_AGAIN))
        self.assertEqual((rig.writes(), rig.stock(SEED)), (wrote, 28))
        # nothing was ever deleted: the log holds only reads and POST/PUT writes
        self.assertEqual(set(rig.methods()) - {"GET", "POST", "PUT"}, set())
