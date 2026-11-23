"""Private restartable saga, NOT a cross-system transaction; no chat wiring.
Create drafts may include after.stock: it becomes a second literal-ID engine draft
under the same approval. Pending notifications await the later outbox seam.
"""
import fcntl
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable
from hass import release_journal as releases
from hass.clover import drafts as d
from hass.clover.cache import _private_dir, _private_file
from hass.clover.chat import SITE_NOT_YET
from hass.clover.mapper import parse_item
from hass.conversation import sender_key

STATES = ("proposed", "till-intent", "till-applied", "till-uncertain", "link-written",
          "site-intent", "site-live", "done", "split", "partial", "failed", "undone")
LinkWriter = Callable[[str, str, str], None]

@dataclass(frozen=True)
class Bundle:
    code: str
    site_ops: tuple[dict, ...]
    till: d.Draft | None
    link: dict | None
    lines: tuple[str, ...]
    bundle_hash: str
def _hash(code, ops, till, link):
    return hashlib.sha256(json.dumps([code, ops, till.draft_hash if till else None, link],
                                    sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
def _first(till):
    if till.kind != "create_item": return till
    return replace(till, after={k: v for k, v in till.after.items() if k != "stock"},
                   requests=tuple(r for r in till.requests if r["path"] != "/item_stocks/{newItemId}"))
class BundleJournal:
    def __init__(self, state):
        self.path = Path(state) / "clover" / "bundles.sqlite3"
        _private_dir(self.path.parent, True)
        _private_file(self.path, True)
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS bundles(code TEXT PRIMARY KEY, row TEXT NOT NULL)")
    @contextmanager
    def db(self):
        _private_file(self.path, False)
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            yield db
    @contextmanager
    def locked(self):
        lock = self.path.with_suffix(".lock")
        _private_file(lock, True)
        with lock.open("r+b") as guard:
            fcntl.flock(guard, fcntl.LOCK_EX)
            yield
    def put(self, bundle, *, sender, chat, expires):
        row = dict(bundle=asdict(bundle), sender=sender, chat=chat, expires=expires, state="proposed",
                   till="pending" if bundle.till else "omitted", site="pending" if bundle.site_ops else "omitted", notifications={})
        with self.db() as db:
            db.execute("INSERT INTO bundles VALUES(?,?)", (bundle.code, json.dumps(row)))

    def advance(self, code, state, **facts):
        if state not in STATES: raise ValueError("bundle state")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = json.loads(db.execute("SELECT row FROM bundles WHERE code=?", (code,)).fetchone()[0])
            row.update(facts, state=state)
            db.execute("UPDATE bundles SET row=? WHERE code=?", (json.dumps(row), code))
            db.commit()

    def get(self, code):
        with self.db() as db:
            row = db.execute("SELECT row FROM bundles WHERE code=?", (code,)).fetchone()
        return json.loads(row[0]) if row else None

    def open_rows(self):
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT row FROM bundles ORDER BY code")
                    if json.loads(r[0])["state"] not in ("done", "failed", "undone")]

def _owner(sender, chat, engine, site):
    cfg, key = site.settings, sender_key(sender)
    allowed = ((sender, chat) in engine.owners) if engine is not None else (
        key in cfg.get("chatKeys", {}).get(chat, cfg.get("ownerKeys", ()))
        and chat in (cfg.get("ownerChats") or (cfg.get("ownerChat"),)))
    if not allowed or ";+;" in chat: raise d.DraftRefused("Owner private chat only.")

def _paused(engine, site):
    if site.stopped() or getattr(site.conv, "_paused", lambda: False)(): return True
    if engine is not None:
        with engine.journal.locked() as db:
            return bool(db.execute("SELECT 1 FROM meta WHERE k='paused'").fetchone())
    return False

def _out(journal, code, state, text, **facts):
    journal.advance(code, state, reply=text, notifications={who: {"text": text, "state": "pending"}
                    for who in ("owner", "operator")}, **facts)
    return state, text

def propose(*, site_ops, till_draft, link, sender, chat, journal, engine, site):
    with journal.locked():
        _owner(sender, chat, engine, site)
        if _paused(engine, site): raise d.DraftRefused("Changes are paused.")
        till, code = till_draft, secrets.token_hex(4)
        if till:
            try:
                if engine is None: raise d.DraftRefused("Till unavailable.")
                code, _ = engine.offer(_first(till), sender=sender, chat=chat)
            except d.DraftRefused: till = None
        ops, link = tuple(site_ops), link if till else None
        lines = ("On the website: " + ", ".join(o["op"] for o in ops), "The website shows no prices",
                 "On the till: " + "\n".join(x for x in till.lines if x != "Nothing goes on the website.")
                 if till else "I can't add it to the till yet")
        bundle = Bundle(code, ops, till, link, lines, _hash(code, ops, till, link))
        journal.put(bundle, sender=sender, chat=chat, expires=(engine.clock() if engine else time.time()) + 600)
        if ops:
            prepared = site.prepare(list(ops))
            if prepared.get("result") != "ok":
                _out(journal, code, "failed", "The website draft was refused.")
                raise d.DraftRefused("The website draft was refused.")
            draft = prepared["draft"]
            journal.advance(code, "proposed", change_id=draft["change_id"], draft_hash=draft["draft_hash"])
        return code, "\n".join((*lines, f"Reply yes {code} to apply the prepared change."))

def _result(engine, code):
    with engine.journal.locked() as db:
        row = db.execute("SELECT result FROM changes WHERE code=? AND status='applied'", (code,)).fetchone()
    return json.loads(row[0]) if row and row[0] else None

def _till(code, row, journal, engine, sender, chat):
    journal.advance(code, "till-intent", till="intent")
    try: status = engine.handle("yes " + code, sender=sender, chat=chat)
    except d.DraftRefused: status = "failed"
    result = _result(engine, code) if status == "applied" else None
    if not result:
        return _out(journal, code, "failed" if status == "failed" else "till-uncertain",
                    "Check the till; I will not send this again.", till=status)
    journal.advance(code, "till-applied", till="applied", clover_id=result["result_item_id"], undo_result=result)
    till = row["bundle"]["till"]
    if till["kind"] == "create_item" and "stock" in till["after"]:
        try:
            item = parse_item(engine._client().get_item(result["result_item_id"]))
            # Confirm zero on the same unchanged item; an uncounted item still needs a stock write.
            if (till["after"]["stock"] == "0" and item.stock == 0
                    and item.id == result["result_item_id"] and d._base(item) == result["result_base"]):
                return
            stock = replace(d.build_set_stock(item, till["after"]["stock"], engine.config), base=result["result_base"])
            subcode, _ = engine.offer(stock, sender=sender, chat=chat)
            journal.advance(code, "till-intent", till="partial", stock_code=subcode)
            status = engine.handle("yes " + subcode, sender=sender, chat=chat)
            counted = _result(engine, subcode) if status == "applied" else None
            if not counted: raise d.DraftRefused("Count not confirmed.")
        except Exception:
            return _out(journal, code, "partial", "Till item added; count not confirmed. Website unchanged; check or undo.", till="partial")
        journal.advance(code, "till-applied", till="applied", undo_result={**result, "result_base": counted["result_base"]})

def apply(code, *, sender, chat, journal, engine, site, link_writer, now):
    with journal.locked():
        _owner(sender, chat, engine, site)
        row = journal.get(code)
        if not row or (sender, chat) != (row["sender"], row["chat"]): raise d.DraftRefused("Not your bundle.")
        if _paused(engine, site): raise d.DraftRefused("Changes are paused.")
        if row["state"] not in ("proposed", "split"): return row["state"], row.get("reply", "Reconcile before continuing.")
        if row["state"] == "proposed":
            if now >= row["expires"] or (row["bundle"]["site_ops"] and "change_id" not in row):
                raise d.DraftRefused("Expired or incomplete bundle.")
            b = row["bundle"]
            till = d.Draft(**b["till"]) if b["till"] else None
            if b["bundle_hash"] != _hash(code, b["site_ops"], till, b["link"]): raise d.DraftRefused("Changed bundle.")
            if till and (outcome := _till(code, row, journal, engine, sender, chat)): return outcome
        row = journal.get(code)
        if row["till"] not in ("applied", "omitted"): return row["state"], "Check the till before continuing."
        try:
            link = row["bundle"]["link"]
            if link and row.get("link_state") != "written": link_writer(link["product_id"], row["clover_id"], link["sku"])
            journal.advance(code, "link-written", link_state="written")
        except Exception: return _out(journal, code, "split", SITE_NOT_YET + " Say 'retry'.")
        return _site_apply(journal, code, row, site, chat)

def _site_apply(journal, code, row, site, chat):
    journal.advance(code, "site-intent", site="intent" if row["bundle"]["site_ops"] else "omitted")
    try:
        if row["bundle"]["site_ops"]: site.apply(row["change_id"], row["draft_hash"], chat)
        return _finish(journal, code, site)
    except Exception: return _out(journal, code, "split", SITE_NOT_YET + " Say 'retry'.")

def _finish(journal, code, site):
    row = journal.get(code)
    if row["bundle"]["site_ops"]:
        landed = site.went_live(row["change_id"])
        if not landed and row.get("undo_of") and hasattr(site, "load"):
            _, entries = site.load()  # went_live deliberately excludes undo releases on main.
            landed = any(j["change_id"] == row["change_id"] and j["kind"] == "undo" and j["state"] in releases.LANDED for j in entries)
        if not landed:
            return _out(journal, code, "split", SITE_NOT_YET + " Say 'retry'.", site="not-confirmed")
        journal.advance(code, "site-live", site="live")
    text = ("The website is live; " if row["bundle"]["site_ops"] else "Website unchanged; ") + (
        "the till was read back." if row["till"] == "applied" else "the till was not changed.")
    if row.get("undo_of") and row["till"] == "applied": journal.advance(row["undo_of"], "undone")
    return _out(journal, code, "done", text)

def reconcile(*, journal, engine, site, now):
    outcomes = []
    with journal.locked():
        for row in journal.open_rows():
            code, state = row["bundle"]["code"], row["state"]
            if state == "proposed": continue
            if state in ("till-intent", "till-uncertain"):
                active = row.get("stock_code", code)
                status, _ = engine.reconcile(active, sender=row["sender"], chat=row["chat"])
                result = _result(engine, active) if status == "applied" else None
                partial = bool(row.get("undo_result")) or bool(result and row["bundle"]["till"]["kind"] == "create_item"
                                                          and "stock" in row["bundle"]["till"]["after"] and active == code)
                state = "split" if result and not (partial and active == code) else "partial" if partial else "till-uncertain"
                facts: dict = dict(till="applied" if state == "split" else "partial" if partial else "uncertain")
                if result: facts.update(clover_id=result["result_item_id"], undo_result={**row.get("undo_result", result), "result_base": result["result_base"]})
                outcomes.append(_out(journal, code, state, "Check both halves; no till write was repeated.", **facts))
            elif state in ("site-intent", "site-live", "split"): outcomes.append(_finish(journal, code, site))
            else:
                partial = state == "partial" or (state == "till-applied" and row["bundle"]["till"]["kind"] == "create_item"
                                                and "stock" in row["bundle"]["till"]["after"] and not row.get("stock_code"))
                outcomes.append(_out(journal, code, "partial" if partial else "split", "Check both halves; the bundle is incomplete."))
    return outcomes

def undo(code, *, sender, chat, journal, engine, site):
    _owner(sender, chat, engine, site)
    row = journal.get(code)
    if not row or row["state"] not in ("done", "partial", "split") or (sender, chat) != (row["sender"], row["chat"]):
        raise d.DraftRefused("No applied bundle to undo.")
    till = None
    if entry := row.get("undo_result"):
        try: till = d.build_undo(entry, parse_item(engine._client().get_item(entry["result_item_id"])), engine.config)
        except d.DraftRefused: pass  # Keep newer till values; conflict-checked website inverse can still go.
    ops = [{"op": "history.revert", "args": {"changeId": row["change_id"]}}] if row.get("change_id") and site.went_live(row["change_id"]) else []
    if not ops and till is None: raise d.DraftRefused("No half can safely be undone.")
    new, text = propose(site_ops=ops, till_draft=till, link=None, sender=sender, chat=chat, journal=journal, engine=engine, site=site)
    journal.advance(new, "proposed", undo_of=code)
    return new, text
