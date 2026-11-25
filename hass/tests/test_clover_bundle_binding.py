"""Offline contracts: one yes binds to exactly the till change the owner was shown (fake till only)."""
import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from hass.clover import bundle as b, drafts as d
from hass.clover.apply import ApplyEngine
from hass.clover.client import CloverClient, CloverWriteClient
from hass.clover.config import from_settings
from hass.clover.credential import Token
from hass.clover.dryrun import DryRunEngine, DryRunWriteClient
from hass.tests.clover_fake import FakeClover
from hass.tests.test_clover_client import FAKE_TOKEN, NoNetwork
from hass.tests.test_conversation import CHAT, OWNER
from hass.tests.test_item_both import Site

MID = "FAKEMERCH0001"
CATEGORIES = [{"id": "FAKECAT000001", "name": "Pantry"}, {"id": "FAKECAT000002", "name": "Goods"}]
CATS = tuple((c["id"], c["name"]) for c in CATEGORIES)
PREVIEW = "Add Blue mug to the till, 30 in stock. Reply yes <code>."
LINK = {"product_id": "photo-product-175", "sku": "AS-PAN-BLUE-MUG-01"}
OPS = [{"op": "product.add", "args": {"name": "Blue mug"}}]
YES = "yes "


class BindingTests(NoNetwork):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name)
        self.cfg = from_settings({"environment": "sandbox", "merchantId": MID, "tokenFile": "/fixture/read",
                                  "writeTokenFile": "/fixture/write", "writes": True, "liveApproved": True,
                                  "categoryMap": {"pantry": "Pantry", "general": "Goods"}})
        self.fake = FakeClover(MID, categories=CATEGORIES)
        token = mock.patch("hass.clover.apply.load_write_token", return_value=Token(FAKE_TOKEN))
        token.start()
        self.addCleanup(token.stop)
        self.engine = ApplyEngine(self.state, self.cfg, lambda t: CloverWriteClient(MID, t, self.fake, min_interval=0),
                                  mike=(OWNER, CHAT), clock=lambda: 1000)
        self.site, self.links, self.journal = Site(), [], b.BundleJournal(self.state)

    def counted(self, name="Blue mug", price="14.00", category="pantry", count=30):
        return d.build_create_counted(name, price, category, count, [], self.cfg, categories=CATS)

    def propose(self, draft=None, **kw):
        args = dict(site_ops=list(OPS), till_draft=draft or self.counted(), link=dict(LINK), sender=OWNER, chat=CHAT,
                    journal=self.journal, engine=self.engine, site=self.site, preview=PREVIEW)
        return b.propose(**(args | kw))

    def yes(self, code, **kw):
        args = dict(sender=OWNER, chat=CHAT, journal=self.journal, engine=self.engine, site=self.site,
                    link_writer=lambda *row: self.links.append(row), now=1001)
        return b.apply(code, **(args | kw))

    def writes(self):
        return [entry for entry in self.fake.log if entry[0] != "GET"]

    def edit_row(self, code, edit):
        row = self.journal.get(code)
        edit(row["bundle"])
        self.journal.advance(code, "proposed", bundle=row["bundle"])

    def engine_draft(self, code, edit):
        with self.engine.journal.locked() as db:
            entry = json.loads(db.execute("SELECT draft FROM changes WHERE code=?", (code,)).fetchone()[0])
            edit(entry)
            db.execute("UPDATE changes SET draft=? WHERE code=?", (json.dumps(entry), code))

    def test_c1_bind_preview(self):
        # C1: the text the owner read is bound; a stored preview, till, link or website edit must not reach
        # the till. Bug caught: a bundle hash that skips the preview, or checks only some stored fields.
        code, text = self.propose()
        self.assertEqual(text, PREVIEW)  # the exact text shown, with nothing appended
        row = self.journal.get(code)
        self.assertEqual(row["bundle"]["preview_hash"], hashlib.sha256(PREVIEW.encode()).hexdigest())
        edits = {
            "preview hash": lambda x: x.update(preview_hash=hashlib.sha256(b"Add a different mug").hexdigest()),
            "preview hash removed": lambda x: x.update(preview_hash=None),
            "till price": lambda x: x["till"]["after"].update(price=1)
                or x["till"]["requests"][0]["json"].update(price=1),
            "till count": lambda x: x["till"]["after"].update(stock="31"),
            "till request": lambda x: x["till"]["requests"][0]["json"].update(name="Other mug"),
            "till shape": lambda x: x["till"].update(draft_hash="forged"),
            "link": lambda x: x["link"].update(product_id="photo-product-999"),
            "website op": lambda x: x["site_ops"][0]["args"].update(name="Other mug"),
            "bundle hash": lambda x: x.update(bundle_hash="0" * 64),
        }
        for name, edit in edits.items():
            with self.subTest(edit=name):
                code, _ = self.propose()
                self.edit_row(code, edit)
                with self.assertRaisesRegex(d.DraftRefused, "^Changed bundle\\.$"):
                    self.yes(code)
                self.assertEqual(self.writes(), [])
                self.assertEqual((self.links, self.site.calls), ([], []))
        with self.subTest(edit="engine draft"):  # the draft the engine will really send must match the stored one
            code, _ = self.propose()
            self.engine_draft(code, lambda x: x["requests"][0]["json"].update(price=1))
            with self.assertRaisesRegex(d.DraftRefused, "^Changed bundle\\.$"):
                self.yes(code)
            self.assertEqual(self.writes(), [])
        code, text = self.propose(preview=None)  # without a preview, the old text and hash are kept
        self.assertIn(f"Reply yes {code} to apply the prepared change.", text)
        self.assertIsNone(self.journal.get(code)["bundle"]["preview_hash"])
        self.assertEqual(self.yes(code)[0], "done")  # control: an untouched bundle does apply

    def test_c2_each_field_rebinds(self):
        # C2: every owner-visible field is in the hash. Bug caught: hashing only the name, or only text
        # that the owner reads, so a changed count or price shares the earlier yes.
        base = self.counted()
        sku = base.after["sku"]
        by_sku = replace(base, after={**base.after, "sku": "AS-PAN-OTHER-01"})
        by_sku = replace(by_sku, requests=tuple({**r, "json": {**r["json"], "sku": "AS-PAN-OTHER-01"}}
                                                if r["path"] == "/items" else r for r in by_sku.requests))
        variants = {
            "baseline": (OPS, base, LINK, PREVIEW),
            "count": (OPS, self.counted(count=31), LINK, PREVIEW),
            "price": (OPS, self.counted(price="15.00"), LINK, PREVIEW),
            "name": (OPS, self.counted(name="Green mug"), LINK, PREVIEW),
            "sku": (OPS, by_sku, LINK, PREVIEW),
            "category": (OPS, self.counted(category="general"), LINK, PREVIEW),
            "link product": (OPS, base, {**LINK, "product_id": "photo-product-176"}, PREVIEW),
            "website word": ([{"op": "product.add", "args": {"name": "Blue mugs"}}], base, LINK, PREVIEW),
            "preview": (OPS, base, LINK, PREVIEW + " "),
        }
        self.assertNotEqual(by_sku.draft_hash, base.draft_hash)
        self.assertIn(sku, json.dumps(base.requests))
        hashes = {name: b._hash("fixedcode", ops, till, link, hashlib.sha256(text.encode()).hexdigest())
                  for name, (ops, till, link, text) in variants.items()}
        self.assertEqual(len(set(hashes.values())), len(variants), hashes)
        seen = set()
        for name, (ops, till, link, text) in variants.items():  # the same through propose: a new code and hash
            code, _ = self.propose(till, site_ops=ops, link=link, preview=text)
            seen.add((code, self.journal.get(code)["bundle"]["bundle_hash"]))
        self.assertEqual(len({c for c, _ in seen}), len(variants))
        self.assertEqual(len({h for _, h in seen}), len(variants))

    def test_c3_existing_refusals(self):
        # C3: binding a preview must not loosen the old gates. Bug caught: a preview-bound bundle that skips
        # the owner, chat, group, expiry or pause checks. test_item_both covers the same gates unchanged.
        code, _ = self.propose()
        refusals = (("Owner private chat only.", dict(sender="stranger")),
                    ("Owner private chat only.", dict(chat="other-chat")),
                    ("Owner private chat only.", dict(chat="iMessage;+;group")),
                    ("Expired or incomplete bundle.", dict(now=1700)))
        for message, kwargs in refusals:
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(d.DraftRefused, "^" + message.replace(".", "\\.") + "$"):
                self.yes(code, **kwargs)
        for attr in ("paused", "stop"):
            setattr(self.site, attr, True)
            with self.subTest(attr=attr), self.assertRaisesRegex(d.DraftRefused, "^Changes are paused\\.$"):
                self.yes(code)
            setattr(self.site, attr, False)
        self.assertEqual((self.writes(), self.links, self.site.calls), ([], [], []))
        self.engine.handle("stop changes", sender=OWNER, chat=CHAT)
        with self.assertRaisesRegex(d.DraftRefused, "^Changes are paused\\.$"):
            self.yes(code)
        with self.assertRaisesRegex(d.DraftRefused, "^Changes are paused\\.$"):
            self.propose()
        self.assertEqual(self.writes(), [])

    def test_c3b_refused_till_never_shows_the_till_preview(self):
        # C3b: a preview that promises a till change is never shown when the engine refuses that draft. Bug caught:
        # dropping the till but still returning the supplied text, so one yes runs a website-only change.
        with mock.patch.object(self.engine, "offer", side_effect=d.DraftRefused("no")):
            with self.assertRaisesRegex(d.DraftRefused, "nothing was proposed"):
                self.propose()
            self.assertEqual((self.journal.open_rows(), self.site.drafts, self.site.calls), ([], {}, []))
            code, text = self.propose(preview=None)  # no supplied promise: the honest website-only text stays
            self.assertIn("I can't add it to the till yet", text)
            self.assertNotIn("Blue mug to the till", text)
            self.assertIsNone(self.journal.get(code)["bundle"]["till"])

    def test_c4_dry_run_state(self):
        # C4: a rehearsal result is its own final state, not a failure. Bug caught: reading the engine's
        # "dry-run" status as uncertain, or preparing/applying the website or writing the link anyway.
        dry = DryRunEngine(self.state, self.cfg, lambda t: DryRunWriteClient(CloverClient(MID, t, self.fake, min_interval=0)),
                           read_loader=lambda path: Token(FAKE_TOKEN), mike=(OWNER, CHAT), clock=lambda: 1000)
        self.engine = dry
        code, text = self.propose()
        self.assertEqual(text, PREVIEW)
        self.assertEqual(self.site.drafts, {})  # no website op prepared
        state, reply = self.yes(code)
        self.assertEqual((state, reply), ("dry-run", "Dry run: nothing was sent to the till or the website."))
        row = self.journal.get(code)
        self.assertEqual((row["state"], row["till"], row["site"]), ("dry-run", "dry-run", "omitted"))
        self.assertEqual(row["reply"], reply)
        self.assertNotIn("link_state", row)
        self.assertEqual((self.links, self.site.calls, self.writes()), ([], [], []))
        with dry.journal.locked() as db:  # the engine recorded its exact requests locally; stock is never offered
            (status, result), = db.execute("SELECT status, result FROM changes").fetchall()
        self.assertEqual(status, "dry-run")
        self.assertEqual([(r["method"], r["path"]) for r in json.loads(result)], [("POST", "/items"), ("POST", "/category_items")])
        self.assertEqual(b.reconcile(journal=self.journal, engine=dry, site=self.site, now=1002), [])
        self.assertEqual(self.journal.get(code), row)
        self.assertEqual(self.yes(code), ("dry-run", reply))  # a second yes repeats nothing
        self.assertEqual((self.links, self.site.calls, self.writes(), self.site.drafts), ([], [], [], {}))
        with self.assertRaisesRegex(d.DraftRefused, "No applied bundle to undo"):
            b.undo(code, sender=OWNER, chat=CHAT, journal=self.journal, engine=dry, site=self.site)
        code, _ = self.propose(site_ops=[], till_draft=None)  # nothing for the till at all: still a clean dry run
        self.assertEqual(self.yes(code), ("dry-run", reply))
        self.assertIn("dry-run", b.STATES)

    def test_c5_counted_create_one_yes(self):
        # C5: one yes does the whole counted create. Bug caught: stopping after the first draft, applying
        # the stock draft under a second yes, or reporting done without reading the count back.
        draft = self.counted()
        code, text = self.propose(draft, link={"product_id": "photo-product-175", "sku": draft.after["sku"]})
        self.assertEqual(text, PREVIEW)
        self.assertEqual(self.yes(code)[0], "done")
        found = self.fake.register_search("Blue mug")
        self.assertEqual([i["name"] for i in found], ["Blue mug"])
        self.assertEqual(found[0]["itemStock"]["quantity"], 30)
        item_id = found[0]["id"]
        self.assertEqual([(m, p) for m, p, _ in self.writes()], [
            ("POST", "/v3/merchants/{id}/items"), ("POST", "/v3/merchants/{id}/category_items"),
            ("PUT", "/v3/merchants/{id}/item_stocks/{id}")])
        with self.engine.journal.locked() as db:
            rows = [json.loads(r[0]) for r in db.execute("SELECT draft FROM changes WHERE status='applied' ORDER BY expires, code")]
        self.assertEqual(len(rows), 2)
        self.assertEqual(sorted(r["kind"] for r in rows), ["create_item", "set_stock"])
        stock = next(r for r in rows if r["kind"] == "set_stock")
        self.assertEqual([(r["method"], r["path"], r["json"]) for r in stock["requests"]],
                         [("PUT", f"/item_stocks/{item_id}", {"quantity": 30})])  # literal id, never the {newItemId} placeholder
        first = next(r for r in rows if r["kind"] == "create_item")
        self.assertEqual(first["draft_hash"], b._first(draft).draft_hash)
        row = self.journal.get(code)
        self.assertEqual((row["state"], row["till"], row["site"]), ("done", "applied", "live"))
        self.assertEqual(self.links, [("photo-product-175", item_id, draft.after["sku"])])
        self.assertEqual(len(self.site.calls), 1)
        self.assertEqual(self.yes(code)[0], "done")
        self.assertEqual(len(self.writes()), 3)


if __name__ == "__main__":
    unittest.main()
