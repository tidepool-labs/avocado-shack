"""Behavioral contract for the shared offline till, not a live Clover check."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hass.clover.apply import ApplyEngine
from hass.clover.client import (
    CloverClient, CloverError, CloverNotFound, CloverUnavailable, CloverWriteClient, Request, SecretHeaders,
)
from hass.clover.config import from_settings
from hass.clover.credential import Token
from hass.clover.drafts import build_create_item
from hass.tests.clover_fake import FakeClover
from hass.tests.test_clover_client import FAKE_TOKEN, NoNetwork, fixture


MERCHANT = "FAKEMERCH0001"
ITEM = "FAKEITEM00001"
CATEGORY = "FAKECAT000001"
PREFIX = "/v3/merchants/{id}"


class FakeCloverTests(NoNetwork):
    def setUp(self):
        super().setUp()
        self.items = fixture("items.json")["elements"]
        self.categories = fixture("categories.json")["elements"]
        self.fake = FakeClover(merchant=MERCHANT, items=self.items, categories=self.categories)
        self.reader = self.client(CloverClient)
        self.writer = self.client(CloverWriteClient)

    def client(self, client_type):
        return client_type(MERCHANT, Token(FAKE_TOKEN), self.fake, page_size=2, min_interval=0, max_retries=0)

    def test_c1_reads_match_client(self):
        # C1: A fake that ignores offset, expand, or filters would hide broken sync/read-back requests.
        self.assertEqual(self.reader.get_merchant(), fixture("merchant.json"))
        first = self.items[0]
        unexpanded = {k: v for k, v in first.items() if k not in ("itemStock", "categories", "tags")}
        self.assertEqual(self.reader.first_items(), {"elements": [unexpanded]})
        self.assertEqual(self.reader.list_items(), self.items)
        cutoff = self.items[3]["modifiedTime"]
        self.assertEqual(self.reader.list_items(modified_since_ms=cutoff), self.items[3:])
        self.assertEqual(self.reader.find_by_sku(first["sku"]), [unexpanded])
        self.assertEqual(self.reader.find_by_sku(first["sku"][:-1]), [])
        self.assertEqual(self.reader.get_item(ITEM), first)
        request = self.reader.build("GET", f"/items/{ITEM}", {"expand": "categories"})
        self.assertEqual(json.loads(self.fake(request).body), {k: v for k, v in first.items() if k not in ("itemStock", "tags")})
        self.assertEqual(self.reader.get_stock(ITEM), fixture("item_stock.json"))
        self.assertEqual(self.reader.list_stocks(), [i["itemStock"] for i in self.items if "itemStock" in i])
        self.assertEqual(self.reader.list_categories(), self.categories)

    def test_c2_writes_set_not_add(self):
        # C2: Whole-record replacement would clear unrelated fields; additive PUT would inflate the count.
        payload = {"name": "Synthetic mug", "price": 123, "priceType": "FIXED", "sku": "FAKE-MUG", "hidden": False}
        created = self.writer.write("POST", "/items", payload)
        item_id = created["id"]
        self.assertRegex(item_id, r"^FAKEITEM[0-9]{5}$")
        self.assertNotIn(item_id, {i["id"] for i in self.items})
        self.assertGreater(created["modifiedTime"], self.items[-1]["modifiedTime"])
        self.assertEqual({k: created[k] for k in payload}, payload)
        self.assertEqual(self.reader.get_item(item_id), created)
        self.assertNotEqual(self.writer.write("POST", "/items", {"name": "Synthetic cup", "price": 456})["id"], item_id)

        self.writer.write("POST", f"/items/{item_id}", {"price": 321})
        edited = self.reader.get_item(item_id)
        self.assertGreater(edited["modifiedTime"], created["modifiedTime"])
        self.assertEqual(edited, {**created, "price": 321, "modifiedTime": edited["modifiedTime"]})
        self.writer.write("POST", "/category_items", {"elements": [{"category": {"id": CATEGORY}, "item": {"id": item_id}}]})
        filed = self.reader.get_item(item_id)
        self.assertGreater(filed["modifiedTime"], edited["modifiedTime"])
        self.assertEqual(filed["categories"], {"elements": [{"id": CATEGORY, "name": self.categories[0]["name"]}]})

        with self.assertRaises(CloverNotFound):
            self.reader.get_stock(item_id)
        previous = filed["modifiedTime"]
        stock_time = 0
        for count in (18, 5):
            stock = self.writer.write("PUT", f"/item_stocks/{item_id}", {"quantity": count})
            self.assertEqual(stock["item"], {"id": item_id})
            self.assertEqual(stock["quantity"], count)
            self.assertGreater(stock["modifiedTime"], stock_time)
            self.assertEqual(stock, self.reader.get_stock(item_id))
            item = self.reader.get_item(item_id)
            self.assertEqual(item["itemStock"], stock)
            self.assertGreater(item["modifiedTime"], previous)
            previous = item["modifiedTime"]
            stock_time = stock["modifiedTime"]

        before = (self.reader.list_items(), self.reader.list_stocks(), self.reader.list_categories())
        # Exercise closed routing without issuing a deletion, even to the fake.
        for method, path in (("PATCH", f"/items/{item_id}"), ("PUT", f"/items/{item_id}"),
                             ("POST", "/categories"), ("GET", "/unknown")):
            with self.subTest(method=method, path=path):
                request = Request(method, f"/v3/merchants/{MERCHANT}{path}", SecretHeaders(), b'{"price": 999}')
                self.assertEqual(self.fake(request).status, 405)
        self.assertEqual((self.reader.list_items(), self.reader.list_stocks(), self.reader.list_categories()), before)

    def test_c3_log_has_no_header(self):
        # C3: Retaining Requests or copying their headers would retain the bearer value, even if repr hid it.
        self.reader.get_merchant()
        self.reader.get_item(ITEM)
        self.writer.write("PUT", f"/item_stocks/{ITEM}", {"quantity": 5})
        # Templating only supported routes would leak the ID of a rejected category request.
        rejected = Request("GET", f"/v3/merchants/{MERCHANT}/categories/{CATEGORY}", SecretHeaders())
        self.assertEqual(self.fake(rejected).status, 405)
        self.assertEqual(self.fake.log, [
            ("GET", PREFIX, None),
            ("GET", PREFIX + "/items/{id}", None),
            ("PUT", PREFIX + "/item_stocks/{id}", {"quantity": 5}),
            ("GET", PREFIX + "/categories/{id}", None),
        ])
        self.assertNotIn(FAKE_TOKEN, repr(self.fake.log))
        self.assertNotIn(FAKE_TOKEN, repr(self.fake))

    def test_c4_controls(self):
        # C4: A failed reply isn't a lost acknowledgement; mutating on rejection (or not on loss) hides uncertain writes.
        first = self.items[0]
        stock = first["itemStock"]
        self.fake.sell(ITEM, 3)
        sold = self.reader.get_stock(ITEM)
        self.assertEqual(sold["quantity"], stock["quantity"] - 3)
        self.assertGreater(sold["modifiedTime"], stock["modifiedTime"])
        self.assertEqual(self.reader.get_item(ITEM)["itemStock"], sold)
        for status in (403, 503):
            self.fake.fail_next(status)
            with self.assertRaises(CloverError) as error:
                self.writer.write("PUT", f"/item_stocks/{ITEM}", {"quantity": 7})
            self.assertEqual(error.exception.status, status)
            self.assertEqual(self.reader.get_stock(ITEM), sold)

        self.fake.lose_next_response()
        self.assertEqual(self.reader.get_stock(ITEM), sold)  # Reads don't consume the write fault.
        with self.assertRaises(CloverUnavailable):
            self.writer.write("PUT", f"/item_stocks/{ITEM}", {"quantity": 7})
        self.assertEqual(self.reader.get_stock(ITEM)["quantity"], 7)
        self.assertEqual(self.writer.write("PUT", f"/item_stocks/{ITEM}", {"quantity": 6})["quantity"], 6)

        # Search must not hide a name match due to case, accept partial codes, or offer a hidden item.
        for text in ("oLiVe OiL", first["sku"], first["code"]):
            self.assertEqual([i["id"] for i in self.fake.register_search(text)], [ITEM])
        for text in (first["sku"][:-1], first["code"][:-1], self.items[3]["name"]):
            self.assertEqual(self.fake.register_search(text), [])

    def test_c5_engine_round_trip(self):
        # C5: Returning a created ID without serving the filed item on read-back would leave the real journal unsettled.
        with TemporaryDirectory() as root:
            state = Path(root)
            token_file = state / "fake-write"
            token_file.touch(mode=0o600)
            token_file.write_text(FAKE_TOKEN, encoding="utf-8")
            cfg = from_settings({"environment": "sandbox", "merchantId": MERCHANT,
                                 "tokenFile": str(state / "fake-read"), "writeTokenFile": str(token_file),
                                 "writes": True, "liveApproved": True, "categoryMap": {"pantry": self.categories[0]["name"]}})
            owner = {"sender": "synthetic-owner", "chat": "synthetic-chat"}
            engine = ApplyEngine(state, cfg, lambda token: CloverWriteClient(MERCHANT, token, self.fake, min_interval=0),
                                 mike=(owner["sender"], owner["chat"]))
            draft = build_create_item("Synthetic blue mug", 123, "pantry", [], cfg,
                                      categories=[(c["id"], c["name"]) for c in self.reader.list_categories()])
            code, preview = engine.offer(draft, **owner)
            self.assertIn(code, preview)
            self.assertEqual(self.fake.register_search("blue mug"), [])
            self.assertEqual(engine.handle("yes " + code, **owner), "applied")
            self.assertEqual(self.fake.log[-1], ("GET", PREFIX + "/items/{id}", None))
            (created,) = self.fake.register_search(draft.after["sku"])
            item_id = created["id"]
            self.assertEqual(self.reader.get_item(item_id), created)
            self.assertEqual(created["categories"]["elements"][0]["id"], CATEGORY)

            undo, preview = engine.undo(code, **owner)  # Uses the original journal record and build_undo.
            self.assertIn(undo, preview)
            self.assertEqual(self.fake.register_search("blue mug"), [created])
            self.assertEqual(engine.handle("yes " + undo, **owner), "applied")
            self.assertEqual(self.fake.log[-1], ("GET", PREFIX + "/items/{id}", None))
            self.assertEqual(self.fake.register_search(draft.after["sku"]), [])
            hidden = self.reader.get_item(item_id)
            self.assertEqual(hidden, {**created, "hidden": True, "modifiedTime": hidden["modifiedTime"]})
            self.assertEqual(engine.reconcile(code, **owner), ("applied", False))
            self.assertEqual(engine.reconcile(undo, **owner), ("applied", False))
