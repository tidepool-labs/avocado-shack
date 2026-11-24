import hashlib
import json
import os
import sqlite3
import stat
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from hass.clover import drafts as d
from hass.clover.apply import ApplyEngine
from hass.clover.cache import CacheUnsafe
from hass.clover.checks import Verdict
from hass.clover.client import CloverWriteClient
from hass.clover.config import from_settings
from hass.clover.inventory_receipt import build, summary, write
from hass.tests.test_clover_apply import Till
from hass.tests.test_clover_client import FAKE_TOKEN, MID, NoNetwork

CODE, STOCK_CODE = "aabbccdd", "eeff0011"
CREATE = {"method": "POST", "path": "/items", "json": {"name": "Test mug", "price": 123,
                                                       "priceType": "FIXED", "sku": "TEST-MUG", "hidden": False}}
CATEGORY = {"method": "POST", "path": "/category_items",
            "json": {"elements": [{"category": {"id": "FIXTURE-CAT"}, "item": {"id": "{newItemId}"}}]}}
COUNT = {"method": "PUT", "path": "/item_stocks/FIXTURE-ITEM", "json": {"quantity": 7}}
DAY = "2026-01-02"
EXPIRES = 1767376800.0
PREVIEW = "Test mug: 7 at $1.23 each.\nReply yes aabbccdd."


def inputs():
    create = {"requests": [CREATE, CATEGORY], "after": {"name": "Test mug", "sku": "TEST-MUG", "price": 123, "hidden": False}}
    stock = {"requests": [COUNT], "after": {"stock": "7"}}
    rows: list[dict[str, Any]] = [
        dict(code=code, draft=json.dumps(draft), sender="Fixture@Example.test", chat="private-fixture",
             expires=EXPIRES, status="applied", day=DAY,
             result=json.dumps({**draft, "result_item_id": "FIXTURE-ITEM",
                                "result_base": {"modifiedTime": 123, "stockModifiedTime": revision}}))
        for code, draft, revision in ((CODE, create, None), (STOCK_CODE, stock, 124))
    ]
    bundle = dict(bundle=dict(code=CODE, bundle_hash="ab" * 32, till=create), state="done", till="applied", site="live",
                  expires=EXPIRES + 1, stock_code=STOCK_CODE, sender="Proposer@Example.test")
    links: dict[str, Any] = {key: {"provider_id": f"fixture-{key}", "utc": f"2026-01-02T12:00:0{i}+00:00"}
                            for i, key in enumerate(("count", "preview", "yes"))}
    links["yes"]["sender"] = rows[0]["sender"]
    return bundle, rows, links


def make_receipt():
    bundle, rows, links = inputs()
    return build(bundle, rows, PREVIEW, Verdict(True, ()), Verdict(True, ()), "mike", links)


class InventoryReceiptTests(NoNetwork):
    def test_c1_fields(self):
        # C1: catch flattening the bundle into its first draft, or tying the
        # approval to the proposer instead of the yes event's sender and ID.
        bundle, rows, links = inputs()
        links["chat_page"] = Path("private/chat-fixture.html")
        links["preview"]["provider_id"] = "aaaaaaaa-bbbb-cccc-dddd-001122334455"
        with closing(sqlite3.connect(":memory:")) as db:
            db.row_factory = sqlite3.Row
            db.execute("CREATE TABLE changes(code, draft, sender, chat, expires, status, day, result)")
            db.executemany("INSERT INTO changes VALUES (:code,:draft,:sender,:chat,:expires,:status,:day,:result)", rows)
            receipt = build(bundle, db.execute("SELECT * FROM changes ORDER BY rowid"), PREVIEW,
                            Verdict(False, ("hidden",)), Verdict(True, ("no-word",)), "g", links)
        resolved_category = {**CATEGORY, "json": {"elements": [{"category": {"id": "FIXTURE-CAT"},
                                                               "item": {"id": "FIXTURE-ITEM"}}]}}
        self.assertEqual(receipt, {
            "code": CODE, "approver_role": "g", "sender_key": hashlib.sha256(b"fixture@example.test").hexdigest(),
            "times": {"day": DAY, "expires": EXPIRES, "count": "2026-01-02T12:00:00+00:00",
                      "preview": "2026-01-02T12:00:01+00:00", "yes": "2026-01-02T12:00:02+00:00"},
            "preview_text": PREVIEW, "preview_hash": hashlib.sha256(PREVIEW.encode()).hexdigest(),
            "bundle_hash": "ab" * 32,
            "requests": [{"code": CODE, "evidence": "settled", "calls": [CREATE, resolved_category]},
                         {"code": STOCK_CODE, "evidence": "settled", "calls": [COUNT]}],
            "journal": [{"code": code, "status": "applied", "day": DAY, "expires": EXPIRES}
                        for code in (CODE, STOCK_CODE)],
            "bundle_state": "done", "till_state": "applied", "site_state": "live",
            "read_back": [{"code": CODE, "item_id": "FIXTURE-ITEM",
                           "values": {"name": "Test mug", "sku": "TEST-MUG", "price": 123, "hidden": False},
                           "revision": {"modifiedTime": 123, "stockModifiedTime": None}},
                          {"code": STOCK_CODE, "item_id": "FIXTURE-ITEM", "values": {"stock": "7"},
                           "revision": {"modifiedTime": 123, "stockModifiedTime": 124}}],
            "register_verdict": {"ok": False, "findings": ["hidden"]},
            "site_verdict": {"ok": True, "findings": ["no-word"]}, "undo_code": CODE,
            "transcript": {"count": "fixture-count", "preview": "aaaaaaaa-bbbb-cccc-dddd-001122334455", "yes": "fixture-yes",
                           "chat_page": "private/chat-fixture.html"},
        })
        rows[0].update(status="dry-run", result=json.dumps([CREATE, resolved_category]), day=None)
        dry = build(bundle, rows[:1], PREVIEW, None, None, "mike", {"yes": "fixture-yes"})
        self.assertNotIn("undo_code", dry)
        self.assertNotIn("chat_page", dry["transcript"])
        self.assertEqual(dry["transcript"]["yes"], "fixture-yes")
        self.assertEqual(dry["read_back"], [])
        self.assertEqual(dry["requests"], [{"code": CODE, "evidence": "rehearsed", "calls": [CREATE, resolved_category]}])
        rows[0].update(status="uncertain", result="null")
        uncertain = build(bundle, rows[:1], PREVIEW, None, None, "mike", links)
        self.assertNotIn("undo_code", uncertain)
        self.assertEqual(uncertain["requests"], [{"code": CODE, "evidence": "planned", "calls": [CREATE, CATEGORY]}])
        self.assertEqual(uncertain["read_back"], [])
        with self.assertRaisesRegex(ValueError, "approver role"):
            build(bundle, rows, PREVIEW, None, None, "guest", links)

    def test_c1_fields_preserve_distinct_failed_read_backs(self):
        # C1: the same approved write and revision can return different SKUs.
        # Keeping only the approved values loses both observations in the receipt.
        for observed_sku in ("FIXTURE-WRONG-A", "FIXTURE-WRONG-B"):
            with self.subTest(observed_sku=observed_sku), tempfile.TemporaryDirectory() as tmp:
                state = Path(tmp)
                token_file = state / "fake-write"
                token_file.write_text(FAKE_TOKEN)
                token_file.chmod(0o600)
                cfg = from_settings({"environment": "sandbox", "merchantId": MID, "writes": True,
                                     "liveApproved": True, "writeTokenFile": str(token_file),
                                     "tokenFile": str(state / "fake-read"), "categoryMap": {"pantry": "Pantry"}})
                till = Till()

                def transport(request):
                    response = till(request)
                    if request.method == "POST" and request.url.endswith("/category_items"):
                        till.items["NEWITEM"].update(sku=observed_sku, cost=999,
                                                     categories={"elements": [{"id": "FIXTURE-OTHER-CAT"}]})
                    return response

                engine = ApplyEngine(state, cfg, lambda token: CloverWriteClient(MID, token, transport, min_interval=0),
                                     mike=("fixture@example.test", "fixture-chat"))
                draft = d.build_create_item("Test mug", 123, "pantry", [], cfg, categories=[("FIXTURE-CAT", "Pantry")])
                code, preview = engine.offer(draft, sender="fixture@example.test", chat="fixture-chat")
                self.assertEqual(engine.handle("yes " + code, sender="fixture@example.test", chat="fixture-chat"), "failed")
                self.assertEqual([request.method for request in till.seen], ["GET", "POST", "POST", "GET"])
                with engine.journal.locked() as db:
                    row = db.execute("SELECT * FROM changes WHERE code=?", (code,)).fetchone()
                    result = json.loads(row["result"])
                    bundle = dict(bundle=dict(code=code, bundle_hash="ab" * 32), state="failed", till="failed", site="draft")
                    receipt = build(bundle, [row], preview, None, None, "mike", {"yes": "fixture-yes"})
                self.assertEqual(result["after"], draft.after)
                self.assertEqual(receipt["journal"][0]["status"], "failed")
                self.assertNotIn("undo_code", receipt)
                self.assertEqual(receipt["requests"][0]["calls"][0]["json"]["sku"], draft.after["sku"])
                self.assertEqual(receipt["read_back"], [{"code": code, "item_id": "NEWITEM",
                    "revision": {"modifiedTime": 1, "stockModifiedTime": None},
                    "values": {"name": "Test mug", "sku": observed_sku, "price": 123, "hidden": False,
                               "categories": ["FIXTURE-OTHER-CAT"]}}])
                self.assertEqual(result["read_back"], receipt["read_back"][0]["values"])

    def test_c2_private_write(self):
        # C2: catch direct overwrite (old open file would change too), chmod
        # after publishing, or following a state/output link into another tree.
        receipt = make_receipt()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            state = root / "state"
            path = write(state, receipt)
            self.assertEqual(path, state / "clover" / "receipts" / f"{DAY}-{CODE}.json")
            for folder in (state, path.parent.parent, path.parent):
                self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(json.loads(path.read_text()), receipt)
            updated = {**receipt, "bundle_state": "undone"}
            with path.open() as old:
                self.assertEqual(write(state, updated), path)
                self.assertNotEqual(os.fstat(old.fileno()).st_ino, path.stat().st_ino)
                self.assertEqual(json.load(old), receipt)
            self.assertEqual(json.loads(path.read_text()), updated)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(list(path.parent.iterdir()), [path])

            for name, linked in (("checkout", False), ("linked-checkout", True)):
                checkout = root / name
                checkout.mkdir()
                marker = checkout / ".git"
                if linked:
                    marker.write_text("gitdir: fixture\n")
                else:
                    marker.mkdir()
                with self.subTest(name=name), self.assertRaises(CacheUnsafe):
                    write(checkout / "state", receipt)
                self.assertFalse((checkout / "state").exists())
            alias = root / "alias"
            alias.symlink_to(state, target_is_directory=True)
            with self.assertRaises(CacheUnsafe):
                write(alias, receipt)
            with self.assertRaises(CacheUnsafe):
                write(alias / "nested", receipt)
            other_state = root / "other"
            other_state.mkdir(mode=0o700)
            (other_state / "clover").symlink_to(state / "clover", target_is_directory=True)
            with self.assertRaises(CacheUnsafe):
                write(other_state, receipt)
            link = path.with_name(f"{DAY}-deadbeef.json")
            link.symlink_to(path)
            with self.assertRaises(CacheUnsafe):
                write(state, {**receipt, "code": "deadbeef"})
            self.assertTrue(link.is_symlink())
            self.assertEqual(json.loads(path.read_text()), updated)

    def test_c2_private_write_across_pacific_midnight(self):
        # C2: an expiry-derived draft day can differ from the apply day.
        # Naming the replacement from the new day double-counts the change.
        bundle, rows, links = inputs()
        expires = datetime.fromisoformat("2026-01-03T08:05:00+00:00").timestamp()
        bundle.update(expires=expires, state="proposed", till="draft")
        draft = build(bundle, [], PREVIEW, None, None, "mike", {})
        bundle.update(state="done", till="applied")
        rows[0].update(expires=expires, day="2026-01-02")
        links["yes"]["utc"] = "2026-01-03T07:59:00+00:00"
        applied = build(bundle, rows, PREVIEW, None, None, "mike", links)
        self.assertEqual(draft["times"]["day"], "2026-01-03")
        self.assertEqual(applied["times"]["day"], "2026-01-02")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp).resolve() / "state"
            path = write(state, draft)
            self.assertEqual(path.name, f"2026-01-03-{CODE}.json")
            with path.open() as old:
                self.assertEqual(write(state, applied), path)
                self.assertEqual(json.load(old), draft)
            self.assertEqual(list(path.parent.iterdir()), [path])
            self.assertEqual(json.loads(path.read_text()), applied)

            other = write(state, {**applied, "code": "deadbeef"})
            foreign = path.with_name("2026-01-03-01234567.json")
            foreign.symlink_to(other)
            with self.assertRaises(CacheUnsafe):
                write(state, {**applied, "code": "01234567"})
            self.assertTrue(foreign.is_symlink())
            self.assertEqual(json.loads(other.read_text())["code"], "deadbeef")

    def test_c3_no_secrets(self):
        # C3: catch dumping raw journal/transcript data, or only masking an
        # auth field while still copying the same token in a preview or body.
        bundle, rows, links = inputs()
        token = "fixture-secret-for-redaction"
        number = "+1 (202) 555-0136"  # Fictional NANP number.
        links["yes"]["sender"] = number
        links["yes"]["text"] = number
        draft = json.loads(rows[0]["draft"])
        request = draft["requests"][0]
        request["headers"] = {"Authorization": f"Bearer {token}", "X-Fake-Marker": "header-sentinel"}
        request["json"].update(cost=999, name=f"Test mug {token}")
        rows[0]["draft"] = json.dumps(draft)
        rows[0]["result"] = json.dumps({**draft, "result_item_id": "FIXTURE-ITEM", "result_base": {},
                                        "read_back": {"name": number, "cost": 555, "stock": "7"}})
        preview = f"{PREVIEW}\n{number}\n{token}\nAuthorization: Bearer {token}"
        receipt = build(bundle, rows, preview, None, None, "mike", links)
        with tempfile.TemporaryDirectory() as tmp:
            encoded = write(Path(tmp).resolve() / "state", receipt).read_text()
        for forbidden in (number, "+12025550136", token, '"cost"', '"headers"', "Authorization", "header-sentinel"):
            self.assertNotIn(forbidden, encoded)
        self.assertIn(PREVIEW, receipt["preview_text"])
        self.assertEqual(receipt["preview_hash"], hashlib.sha256(preview.encode()).hexdigest())
        self.assertEqual(receipt["sender_key"], hashlib.sha256(b"+12025550136").hexdigest())
        self.assertEqual(receipt["read_back"][0]["values"]["stock"], "7")

    def test_c4_summary_counts_only(self):
        # C4: two steps still count as one change; a rehearsal with the older
        # bundle failure state is not a failed live write; warnings aren't failures.
        applied = make_receipt()
        failed_check = {"ok": False, "findings": ["count", "price", "count", "Test mug"]}
        undone = {**applied, "bundle_state": "undone", "register_verdict": failed_check}
        rehearsal = {**applied, "bundle_state": "failed", "till_state": "dry-run", "journal": [{"status": "dry-run"}]}
        failed = {**applied, "bundle_state": "partial", "site_verdict": {"ok": False, "findings": ["count"]},
                  "register_verdict": {"ok": True, "findings": ["no-word"]}}
        self.assertEqual(summary(iter([applied, undone, rehearsal, failed])), {
            "changes": 4, "applied": 1, "dry-run": 1, "undone": 1, "failed": 1,
            "check_failures": {"count": 2, "price": 1},
        })
