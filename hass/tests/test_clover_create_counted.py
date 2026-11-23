"""Offline contracts for creating a till item with its first count."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hass import content_model
from hass.clover import bundle, config, drafts, mapper, sku
from hass.clover.apply import ApplyEngine
from hass.tests.test_clover_client import FAKE_TOKEN, NoNetwork


NAME = "Blue mug"
CFG = config.CloverConfig("sandbox", "FAKEMERCH0001", "", category_map={"pantry": "Pantry"})
CATS = (("FAKECAT000001", "Pantry"),)


class CountedCreateTests(NoNetwork):
    def test_c1_counted_create_shape(self):
        # C1: a missing stock field or misplaced stock request would break the bundle's second step.
        for categories in (CATS, ()):
            with self.subTest(categories=categories):
                counted = drafts.build_create_counted(NAME, "14.00", "pantry", "30.000", [], CFG, categories=categories)
                self.assertIsInstance(counted, drafts.Draft)
                self.assertEqual(counted.kind, "create_item")
                self.assertEqual(counted.after["stock"], "30")
                self.assertEqual([(r["method"], r["path"]) for r in counted.requests],
                                 [("POST", "/items")] + ([("POST", "/category_items")] if categories else [])
                                 + [("PUT", "/item_stocks/{newItemId}")])
                (stock,) = counted.requests[-1:]
                self.assertEqual(stock["json"], {"quantity": 30})
                self.assertIs(type(stock["json"]["quantity"]), int)
                if categories:
                    self.assertEqual(counted.requests[1]["json"], {"elements": [
                        {"category": {"id": "FAKECAT000001"}, "item": {"id": "{newItemId}"}}
                    ]})
                first = bundle._first(counted)
                legacy = drafts.build_create_item(NAME, 1400, "pantry", [], CFG, categories=categories)
                self.assertEqual(first.core(), legacy.core())
                self.assertEqual(first.draft_hash, legacy.draft_hash)
        with self.assertRaisesRegex(drafts.DraftRefused, "daily limit"):
            drafts.build_create_counted(NAME, "14.00", "pantry", 30, [], CFG, writes_today=CFG.daily_write_cap)

    def test_c2_price_types(self):
        # C2: stripping the price suffix but leaving FIXED would price weighed stock by the item.
        for text in ("14.00", "14.00 each"):
            with self.subTest(text=text):
                fixed = drafts.build_create_counted(NAME, text, None, 30, [], CFG)
                payload = fixed.requests[0]["json"]
                self.assertEqual((payload["price"], payload["priceType"]), (1400, "FIXED"))
                self.assertIs(type(payload["price"]), int)
                self.assertNotIn("unitName", payload)
                self.assertIn("  Price: $14.00 each", fixed.lines)
        weighed = drafts.build_create_counted("Test pears", "8.00 per lb", None, "2.375", [], CFG)
        body = bundle._first(weighed).requests[0]["json"]
        self.assertEqual((body["price"], body["priceType"], body["unitName"]), (800, "PER_UNIT", "lb"))
        self.assertIs(type(body["price"]), int)
        self.assertIn("  Price: $8.00 per lb", weighed.lines)
        self.assertEqual(weighed.after["stock"], "2.375")
        self.assertEqual(weighed.requests[-1]["json"], {"quantity": 2.375})
        for text in (None, 14, "14", "$14.00", "14.00 per kg", "14.00 each\n", "08.00", "8.000"):
            with self.subTest(text=text), self.assertRaisesRegex(drafts.DraftRefused, r"^I could not read that as a price\."):
                drafts.build_create_counted(NAME, text, None, 30, [], CFG)
        for text, quantity, reason in (("14.00 each", "0.5", "whole items"),
                                       ("8.00 per lb", "2.3751", "three decimal places")):
            with self.subTest(text=text), self.assertRaisesRegex(drafts.DraftRefused, reason):
                drafts.build_create_counted(NAME, text, None, quantity, [], CFG)

    def test_c3_general_category(self):
        # C3: a stale category list rejects website general before it can get a GEN SKU.
        self.assertIn("general", mapper.CATEGORIES)
        self.assertEqual(mapper.CATEGORIES, content_model.CATEGORIES)
        self.assertEqual(sku.generate_sku(NAME, "general", []), "AS-GEN-BLUE-MUG-01")
        with TemporaryDirectory() as root:
            cfg = config.from_settings({"environment": "sandbox", "merchantId": "FAKEMERCH0001",
                                        "tokenFile": str(Path(root) / "fake-token"), "categoryMap": {"general": "Goods"}})
            self.assertEqual(cfg.category_map, {"general": "Goods"})
            counted = drafts.build_create_counted(NAME, "14.00", "general", 30, [], cfg,
                                                  categories=(("FAKEGOODS001", "Goods"),))
        self.assertIn("  Category: Goods", counted.lines)
        self.assertEqual(counted.requests[1]["json"]["elements"][0]["category"], {"id": "FAKEGOODS001"})

    def test_c4_lines(self):
        # C4: reusing the old preview can say the item is uncounted or omit register visibility.
        for categories, display in ((CATS, "Pantry"), ((), "none")):
            with self.subTest(categories=categories):
                counted = drafts.build_create_counted(NAME, "14.00 each", "pantry", 30, [], CFG, categories=categories)
                self.assertEqual(counted.lines, ("Did you mean to add this to the till?", "  Item: Blue mug",
                                                "  SKU: AS-PAN-BLUE-MUG-01 (made up by me, the next free number)",
                                                "  Price: $14.00 each", f"  Category: {display}", "  Count: 30",
                                                "  On the register: showing"))
                self.assertEqual(counted.warnings, () if categories else (
                    "the till has no category called Pantry, so the item is added with no category",))
                body = counted.requests[0]["json"]
                self.assertEqual(set(body), {"name", "sku", "price", "priceType", "hidden"})
                self.assertIs(body["hidden"], False)

    def test_c5_existing_unchanged(self):
        # C5: folding counted creates into the old entry point could change its count-free draft or preview.
        legacy = drafts.build_create_item(NAME, 1400, None, [], CFG)
        self.assertEqual(legacy.after, {"name": NAME, "sku": "AS-GEN-BLUE-MUG-01", "price": 1400, "hidden": False})
        self.assertEqual(legacy.requests, ({"method": "POST", "path": "/items",
                                           "json": {**legacy.after, "priceType": "FIXED"}},))
        self.assertEqual(legacy.lines[-3:], ("  Count: not counted yet (say 'received 12 Blue mug' to start counting)",
                                             "  Tax: your till's usual setting; I set none", "Nothing goes on the website."))


class CountedTill:
    def __init__(self, starting_stock, price_readback):
        self.starting_stock, self.price_readback = starting_stock, price_readback
        self.writes = []
        self.item = {}

    def list_items(self):
        return []

    def get_item(self, item_id):
        assert item_id == self.item["id"]
        return {**self.item, **self.price_readback}

    def write(self, method, path, body):
        self.writes.append((method, path, body))
        if (method, path) == ("POST", "/items"):
            self.item = {**body, "id": "FAKEITEM00001", "modifiedTime": 1,
                         "itemStock": {"quantity": self.starting_stock, "modifiedTime": 1}}
            return {"id": self.item["id"]}
        if (method, path) == ("PUT", "/item_stocks/FAKEITEM00001"):
            self.item["itemStock"] = {**body, "modifiedTime": 2}
            return {}
        raise AssertionError((method, path))


class CountedApplyTests(NoNetwork):
    def apply_counted(self, price, quantity, till):
        with TemporaryDirectory() as root:
            token_file = Path(root) / "fake-write"
            token_file.write_text(FAKE_TOKEN)
            token_file.chmod(0o600)
            cfg = replace(CFG, writes=True, live_approved=True, write_token_file=str(token_file))
            owner = {"sender": "fixture-owner", "chat": "fixture-private"}
            engine = ApplyEngine(root, cfg, lambda _: till, mike=(owner["sender"], owner["chat"]))
            journal = bundle.BundleJournal(root)
            site = SimpleNamespace(settings={}, conv=None, stopped=lambda: False)
            draft = drafts.build_create_counted(NAME, price, None, quantity, [], cfg)
            code, _ = bundle.propose(site_ops=(), till_draft=draft, link=None, journal=journal,
                                     engine=engine, site=site, **owner)
            state, _ = bundle.apply(code, journal=journal, engine=engine, site=site,
                                    link_writer=None, now=engine.clock(), **owner)
            return state, journal.get(code)

    def test_c2_apply_verifies_both_price_basis_fields(self):
        # R1/C2: accepting matching cents alone can approve a fixed price or the wrong weighing unit.
        for price_readback, expected in (({"priceType": "FIXED"}, "failed"),
                                        ({"unitName": "kg"}, "failed"),
                                        ({"unitName": None}, "failed"),
                                        ({}, "done")):
            with self.subTest(price_readback=price_readback):
                till = CountedTill(0, price_readback)
                state, _ = self.apply_counted("8.00 per lb", 2, till)
                self.assertEqual(state, expected)
                self.assertEqual(till.item["price"], 800)
                expected_writes = ["POST"] if expected == "failed" else ["POST", "PUT"]
                self.assertEqual([method for method, _, _ in till.writes], expected_writes)

    def test_c1_zero_first_count_needs_no_write_when_already_zero(self):
        # R1/C1: an already-zero item must not hit the stock builder's no-change refusal.
        # A nonzero default still needs an actual stock write; don't assume that every new item is zero.
        for initial, methods in ((0, ["POST"]), (3, ["POST", "PUT"]), (None, ["POST", "PUT"])):
            with self.subTest(initial=initial):
                till = CountedTill(initial, {})
                state, row = self.apply_counted("14.00 each", 0, till)
                assert row is not None
                self.assertEqual((state, row["till"]), ("done", "applied"))
                self.assertEqual(till.item["itemStock"]["quantity"], 0)
                self.assertEqual([method for method, _, _ in till.writes], methods)
