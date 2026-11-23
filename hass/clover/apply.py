"""Fixture-qualified till engine. No chat wiring or site apply; ambiguous intents are never replayed."""
import json
import secrets
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from hass.clover import drafts as d
from hass.clover.credential import load_write_token
from hass.clover.journal import Journal
from hass.clover.mapper import parse_item, format_quantity

REFUSED = "I can read the till but I can't change it yet."

class ApplyEngine:
    def __init__(self, state, config, client_factory, *, mike, g=None, g_is_owner=False, clock=time.time):
        self.config, self.factory, self.clock = config, client_factory, clock
        self.owners = {mike} | ({g} if g_is_owner and g else set())  # explicit (sender, private chat) pairs
        self.journal = Journal(state, config)

    def _client(self):
        if not self.config.writes_allowed:
            raise d.DraftRefused(REFUSED)
        return self.factory(load_write_token(self.config))

    def _day(self):
        return datetime.fromtimestamp(self.clock(), ZoneInfo("America/Los_Angeles")).date().isoformat()

    def offer(self, draft, *, sender, chat):
        if (sender, chat) not in self.owners or draft.site_ops:
            raise d.DraftRefused("Owner-only till draft; site bundles require the existing site apply path.")
        with self.journal.locked() as db:
            self._gate(db, draft.undo_of)
            code = secrets.token_hex(4)
            db.execute("INSERT INTO changes VALUES(?,?,?,?,?,'draft',NULL,NULL)",
                       (code, json.dumps(draft.to_dict()), sender, chat, self.clock() + 600))
        return code, draft.render(code)

    def _gate(self, db, undo):
        if not self.config.writes_allowed:
            raise d.DraftRefused(REFUSED)
        if db.execute("SELECT 1 FROM meta WHERE k='paused'").fetchone():
            raise d.DraftRefused("Till changes are paused.")
        used = db.execute("SELECT count(*) FROM changes WHERE day=? AND json_extract(draft,'$.undo_of') IS NULL", (self._day(),)).fetchone()[0]
        if not undo:
            d._gate(self.config, used)  # includes uncertain/failed attempts, conservatively

    def handle(self, text, *, sender, chat, edited=False, reaction=False, group=False):
        if (sender, chat) not in self.owners or edited or reaction or group:
            raise d.DraftRefused("Only an owner's original private message can approve a till change.")
        with self.journal.locked() as db:
            if text == "stop changes":
                db.execute("INSERT OR REPLACE INTO meta VALUES('paused','1')")
                return "Till changes are paused."
            row = db.execute("SELECT * FROM changes WHERE code=? AND sender=? AND chat=?", (text.removeprefix("yes "), sender, chat)).fetchone()
            if not text.startswith("yes ") or row is None or row["status"] != "draft" or row["expires"] <= self.clock():
                raise d.DraftRefused("That is not a current till approval code.")
            entry = json.loads(row["draft"])
            self._gate(db, entry["undo_of"])
            client = self._client()
            db.execute("UPDATE changes SET status='intent',day=? WHERE code=?", (self._day(), row["code"]))
            draft = d.Draft(**{k: entry[k] for k in d.Draft.__dataclass_fields__})
            item_id = draft.item_id
            try:
                if item_id:
                    fresh = parse_item(client.get_item(item_id))
                    if fresh.id != item_id or d.is_stale(draft, fresh):
                        raise d.DraftRefused("The till changed; ask for a fresh draft and approve its new code.")
                sku = entry["after"].get("sku")
                if sku and (draft.kind == "set_sku" or not item_id):
                    if any(i.get("id") != item_id and any(
                            (i.get(field) or "").casefold() == sku.casefold() for field in ("sku", "code"))
                           for i in client.list_items()):
                        raise d.DraftRefused("That SKU is now taken; ask for a fresh draft.")
                for request in draft.requests:
                    payload = json.loads(json.dumps(request["json"]).replace("{newItemId}", item_id or "{newItemId}"))
                    result = client.write(request["method"], request["path"], payload)
                    if request["path"] == "/items":
                        item_id = result["id"]
                raw = client.get_item(item_id)
                status = "applied" if self._matches(entry, raw) else "failed"
                wrong_item = bool(entry["item_id"]) and raw.get("id") != entry["item_id"]
                self.journal.settle(db, row["code"], status, None if wrong_item else self._result(entry, raw))
                return status
            except d.DraftRefused:
                self.journal.settle(db, row["code"], "failed")
                raise
            except Exception:
                return "uncertain"  # leave intent durable; never resend even if the call succeeded

    @staticmethod
    def _matches(entry, raw):
        if entry["item_id"] and raw.get("id") != entry["item_id"]:
            return False  # an existing-item change is bound to the approved item id
        item = parse_item(raw)
        values = {"price": item.price_cents, "stock": None if item.stock is None else format_quantity(item.stock),
                  "sku": item.sku, "hidden": item.hidden, "name": item.name}
        if entry.get("kind") == "create_item" and entry["after"].get("priceType") == "PER_UNIT":
            values.update(priceType=raw.get("priceType"), unitName=raw.get("unitName"))
        categories = {e["id"] for e in raw.get("categories", {}).get("elements", [])}
        return all(values.get(k) == v for k, v in entry["after"].items()) and all(
            r["json"]["elements"][0]["category"]["id"] in categories for r in entry["requests"] if r["path"] == "/category_items")

    @staticmethod
    def _result(entry, raw):
        return {**entry, "result_item_id": raw["id"], "result_base": d._base(parse_item(raw))}

    def reconcile(self, code, *, sender, chat):
        """Durable approval hook: inspect under the journal lock, never resend an intent.

        Settled results need only an outbox outcome. An interrupted intent stays
        explicitly uncertain for attended reconciliation, even if no call ran.
        """
        with self.journal.locked() as db:
            row = db.execute("SELECT * FROM changes WHERE code=? AND sender=? AND chat=?", (code, sender, chat)).fetchone()
            if row is None or (sender, chat) not in self.owners:
                return "held", False
            status = row["status"]
            if status == "intent":
                self.journal.settle(db, code, "uncertain")
                status = "uncertain"
            return status, bool(json.loads(row["draft"]).get("site_ops"))

    def recover(self):
        with self.journal.locked() as db:
            client = self._client()
            for row in db.execute("SELECT * FROM changes WHERE status='intent'").fetchall():
                entry = json.loads(row["draft"])
                candidates = [client.get_item(entry["item_id"])] if entry["item_id"] else client.find_by_sku(entry["after"]["sku"])
                raw = candidates[0] if len(candidates) == 1 else None
                applied = raw is not None and self._matches(entry, raw)
                self.journal.settle(db, row["code"], "applied" if applied else "uncertain", self._result(entry, raw) if applied else None)

    def undo(self, code, *, sender, chat):
        if (sender, chat) not in self.owners:
            raise d.DraftRefused("Owner only.")
        with self.journal.locked() as db:
            row = db.execute("SELECT result FROM changes WHERE code=? AND status='applied'", (code,)).fetchone()
            if not row:
                raise d.DraftRefused("No applied till change to undo.")
            entry = json.loads(row[0])
            draft = d.build_undo(entry, parse_item(self._client().get_item(entry["result_item_id"])), self.config)
        return self.offer(draft, sender=sender, chat=chat)
