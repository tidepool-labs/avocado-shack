"""Reports pack: `report`, `margin`, `cost` and `post` (Conversation mixin).

AVB-12: moved verbatim out of hass/conversation.py, which imports every name back (hass.conversation.<name> is
unchanged). The methods run on the Conversation (self is the conversation): they use its store, replies and
settings exactly as before. Command routing stays in Conversation._command.
"""
import os, re, stat  # noqa: E401
from datetime import datetime

from hass import editor as editor_mod, margins, memory as memory_mod, morning_report, social_draft, voice
from hass.chat.shared import CANT_READ, CONTROL, COST_USAGE, _iso, load_content, LOCAL_TZ, q, SHELF_ASK
from hass import sitegen
from hass.content_model import ContentError, load_and_validate, shop_today
from hass.ops import catalog

POST_ILLUSTRATION = "This picture is an illustration made from a shelf photo, not a photo of the product. Send a photo with the product name as its caption to post a real one."  # AV1352-03
POST_USAGE = "Which product is the post for? Say " + q("post <id, name or alias>") + ", like " + q("post Hass avocado") + "; " + q("find <words>") + " looks it up."  # AV1322-07; AV1052-07
MAKER_USAGE = "Send " + q("post maker") + " and a maker key; " + q("find <words>") + " gives keys."  # AV1937-10
MAKER_REFUSALS = {"no such maker": "No maker {id}; send " + q("find <words>") + " for keys.",
                  "not on the site": "Maker {id} is hidden; nothing to draft.",
                  "no active products": "Maker {id} has no active products on the site."}  # other reasons: "Cannot draft a post for {id}: {reason}."
MAKER_CANT_READ = q("Catalog unavailable right now; nothing changed.")  # the spec's exact line; quoted so the voice list of tech words ("catalog") leaves it alone
NOTICE_NONE = "There is no notice on the website to post."  # AV1104-07: none, not shown yet, or its last day has passed
HIKE_USAGE = "Which hike is the post for? Say it like " + q("post hike Point Buchon") + "."  # AV1222-11
HIKE_REFUSALS = {"no such hike": "I don't know a hike called {id}. Try " + q("find") + " and a word from its name.",
                 "hike is cancelled": "{id} is cancelled, so there is nothing to announce.",
                 "hike already happened": "{id} has already happened.", "not scheduled": "{id} isn't scheduled yet."}  # other reasons: POST_CANT
POST_REFUSALS = {"no such product": "I don't know a product called {id}. Try " + q("find") + " and a word from its name.",
                 "not on the site": "{id} isn't on the website right now.",
                 "no photo on the site": "{id} has no photo on the website yet, so I can't make a post for it."}  # other reasons: POST_CANT
POST_CANT = "I can't make a post for {id} right now. Nothing was posted."
_NUM = r"[-+]?[0-9.][0-9.,_]*(?:e[-+]?[0-9]+)?"  # AV1102-12: looks like a number; margins.compute is the only validator
_END = r"(?:\s+(?i:ending)\s+\.(49|99))?"  # AV1352-09: round the price up to the next .49 / .99 (margins.compute round_to)
MARGIN_RE = re.compile(rf"\$?({_NUM})\s+for\s+({_NUM})\s+at\s+({_NUM})\s*%(?:\s+shrink\s+({_NUM})\s*%)?{_END}")
MARGIN_ID_RE = re.compile(rf"(?!\$?{_NUM}\s+for\s)(\S.*?)\s+at\s+({_NUM})\s*%(?:\s+shrink\s+({_NUM})\s*%)?{_END}")  # AV1222-10: saved cost
_PRICE = rf"\s+price\s+\$?({_NUM})(?:\s+shrink\s+({_NUM})\s*%)?"  # AV1352-08: the shelf price to check; margins.check is the only validator
PRICE_RE = re.compile(rf"\$?({_NUM})\s+for\s+({_NUM})" + _PRICE, re.IGNORECASE)
PRICE_ID_RE = re.compile(rf"(?!\$?{_NUM}\s+for\s)(\S.*?)" + _PRICE, re.IGNORECASE)
COST_RE = re.compile(r"\$?(\S+)\s+for\s+(\S+)", re.IGNORECASE)  # AV1222-10: margins.compute is the only number validator

MARGIN_USAGE = ("Tell me what you pay for a pack (or a product with a saved cost), how many are in it and the margin you want, like "
                + q("margin 24 for 12 at 35%") + ", or the shelf price to check, like " + q("margin 24 for 12 price 3.49") + ". Add " + q("shrink 5%") + " if some is lost, or " + q("ending .99") + " (or " + q(".49") + ") to round the price up.")

_STEP_WORDS = {"unit_cost": "Each one costs you", "sellable_cost": "Each one you can sell costs you", "price": "Shelf price", "margin_actual": "Your margin"}


def _margin_steps(r) -> str:
    """AV1352-08: margins.check's steps and below-cost line (same numbers as margins.render) in plain words for chat, which has no computer names."""
    below = ["Below cost: this price does not cover the cost per sellable unit."] if r.get("below_cost") is True else []
    return "\n".join([f"{_STEP_WORDS[x['name']]}: {x['expression']} = {x['value']}" for x in r["steps"]] + below + [r["note"]])


class ReportsPack:
    """Reports pack commands, mixed into Conversation."""

    def _report(self, msg, now) -> str:
        """AV1322-05 (F04): the morning shelf report from the writer worktree content, Pacific today; read-only for the site.
        HASS-SHELFCHECK-FLOW-1: when today's shelf check is missing, the first report of the day also asks the owner
        SHELF_ASK (a yes then drafts the check; nothing is written by asking)."""
        ask = False
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
            facts = morning_report.facts(content, shop_today(now))
            text = morning_report.render(facts)
            ask = facts["checked_on"] != shop_today(now).isoformat() and not facts["future"] and self._report_asked(msg, now)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "report-unreadable")
            text = "I can't read the shelf report right now, so I can't tell you what's on the shelves. Nothing has changed."
        notice = self._notice_line(now)  # AV1937-07: the home notice and its last day, once, before the waiting block
        text += f"\n{notice}" if notice else ""
        waiting = self._waiting_lines(now) + [l for l in self._photo_lines(now) if "waiting for details" in l]
        self._reply(f"{text}\n\n" + "\n".join(["Waiting for you:"] + waiting if waiting else ["Nothing is waiting for you."])
                    + (f"\n\n{SHELF_ASK}" if ask else ""), long_ok=True)
        return "report"

    def _report_asked(self, msg, now) -> bool:
        """HASS-SHELFCHECK-FLOW-1: True the first time today that the report asks SHELF_ASK (and keeps it open); once a day."""
        day = shop_today(now).isoformat()
        self.db.execute(CONTROL)
        if (row := self.db.execute("SELECT value FROM control WHERE name = 'shelf-asked'").fetchone()) and row["value"] == day: return False
        self.db.execute("INSERT INTO control(name, value, set_at, provider_id) VALUES ('shelf-asked', ?, ?, ?)"
                        " ON CONFLICT(name) DO UPDATE SET value = excluded.value, set_at = excluded.set_at,"
                        " provider_id = excluded.provider_id", (day, _iso(now), msg.provider_id))
        self._open_ask(msg, now, [], {"ops": [], "revises": None})
        return True

    def _margin(self, rest) -> str:
        """AV1102-12 (F03): margins.render for one purchase line, text in and text out. Read-only: nothing is stored or
        drafted, no interpreter call or usage count; works while paused."""
        found = MARGIN_RE.fullmatch(rest)
        by_id = None if found else MARGIN_ID_RE.fullmatch(rest.strip())  # AV1222-10: the saved cost of a product (by name or id)
        priced = None if found or by_id else PRICE_RE.fullmatch(rest.strip())  # AV1352-08: the margin a shelf price gives
        by_price = None if found or by_id or priced else PRICE_ID_RE.fullmatch(rest.strip())
        listing = False  # AV2137-05: a product name that fits several is answered with the find lines (ids shown)
        try:
            if found: text = margins.say(margins.compute(found[1], found[2], found[4] or "0", found[3], found[5] and "." + found[5]))
            elif by_id: text, listing = self._margin_saved(*by_id.groups())
            elif priced: text = _margin_steps(margins.check(priced[1], priced[2], priced[4] or "0", priced[3]))
            elif by_price: text, listing = self._margin_saved(by_price[1], None, by_price[3], price=by_price[2])
            else: text = MARGIN_USAGE
        except margins.InputError as exc:
            self._problem("did-not-understand", "margin-numbers")
            text = "I couldn't work that out. " + margins.plain_input_error(exc)
        self._reply(text, long_ok=listing, ids_ok=listing)
        return "margin"

    def _purchase_product(self, content, typed):
        """AV2137-05: (product, None, False) for what a cost or saved-cost margin names, else (None, reply, several). An exact id
        acts as before; else exactly one product of ANY status (a private cost needs no website listing) by name, brand or
        saved nickname acts as that id; several give the find lines (<= 10, with ids), none says to use find. Read-only: the
        memory table is only read when it exists, and nothing is guessed."""
        by_id = next((p for p in content.products if p["id"] == typed), None)
        if by_id: return by_id, None, False
        has_memory = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
        found = catalog.lookup(content, "product", typed, aliases=self.aliases() if has_memory else None)
        if "match" in found: return next(p for p in content.products if p["id"] == found["match"]), None, False
        if found["candidates"]: return None, self._many_lines(found["candidates"]), True
        return None, f"I don't know a product called {q(typed)}. Try {q('find')} and a word from its name.", False

    def _margin_saved(self, ident, margin, shrink, ending=None, *, price=None):
        """AV1222-10: margins for the saved cost.<id> (read-only; the memory table is not created for a read).
        AV2137-05: the product may be named by id, name or nickname; returns (reply, True when the reply lists several products)."""
        try:
            product, reply, several = self._purchase_product(load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content"), ident)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            return CANT_READ, False
        if product is None: return reply, several
        has_table = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
        if self.memory is None and has_table: self.memory = memory_mod.Memory.on_connection(self.db, self.clock)
        shown = f"{q(product['name'])} ({q(product['id'])})"
        row = next((r for r in self.memory.list() if r["key"] == f"cost.{product['id']}"), None) if has_table else None
        if row is None: return f"I don't have a cost saved for {shown}. Tell me first, like " + q(f"cost {product['id']}: 24 for 12") + ".", False
        pack, _, units = row["value"].partition(" for ")
        calc = _margin_steps(margins.check(pack, units, shrink or "0", price)) if price is not None else \
            margins.say(margins.compute(pack, units, shrink or "0", margin, ending and "." + ending))
        try:  # RF1221-12: the saved date is only a label; an unreadable one never drops the calculation
            saved = datetime.fromisoformat(row["created_at"])
            if saved.utcoffset() is None: raise ValueError("naive")
            when = f"For {shown}, using the cost you gave me {voice.natural(saved.astimezone(LOCAL_TZ), self._now())}."
        except (TypeError, ValueError, OverflowError, OSError):
            when = f"For {shown}, using your saved cost; I can't read when you gave it to me."
        return when + "\n" + calc, False

    def _post_names_something(self, text) -> bool:
        """HASS-VOICE-1: post takes a name, so several words only count as the post command when they point at one product
        or hike; anything else keeps going to the interpreter as before. Unreadable content counts as a name so the usual
        'can't read' answer follows. AV1052-07: a product of any status counts, and a name may fit several (they are listed)."""
        try:
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            return True
        words = text.split()
        if words[0].lower() == "maker": return True  # AV1937-10: a maker key may be several words; it is never a sentence
        if words[0].lower() == "hike" and len(words) == 2: return True  # one id after 'hike': the usual 'I don't know a hike' answer
        if words[0].lower() == "hike": return self._pick_hike(content, text[4:].strip()) != text[4:].strip()
        return not self._bad_query(text) and self._names_a_product(content, text)

    def _post(self, pid) -> str:
        """AV1322-07 (F07 prepare half): social_draft's caption for one active product plus its site photo, from the
        writer worktree content. Read-only: nothing is posted, scheduled, written or drafted; works while paused."""
        photo = None
        if pid.strip().lower() == "today": return self._post_today()  # AV1104-08: the whole argument; before the product-id fallback
        if pid.strip().lower() == "notice": return self._post_notice()  # AV1104-07: the whole argument; before the product-id fallback
        if pid.lower().split(None, 1)[:1] == ["maker"]: return self._post_maker(pid[5:].strip())  # AV1937-10: before the product-id fallback
        if pid.lower().split(None, 1)[:1] == ["hike"]: return self._post_hike(pid[4:].strip())
        try:
            if self._bad_query(pid): raise LookupError  # AV1052-07: blank, over 60 characters or several lines
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_content(wt / "hass" / "content")
            pid, many = self._product_for(content, pid)  # an id, or the one active name or alias as that id; else several or none
            if many:
                self._reply(many, long_ok=True, ids_ok=True)
                return "post"
            out = social_draft.build(content, pid, wt / "storefront-mockup", today=shop_today(self._now()))
            if out["draft"] and stat.S_ISREG(os.lstat(photo := wt / "storefront-mockup" / out["image"]).st_mode):
                text = f"Here's a post you can copy. I haven't posted anything.\n{q(out['caption'])}\nWhat the photo shows: {q(out['alt'])}"
                if out.get("availability") in ("Sold out", "Limited"): text = self._post_stock_line(content, pid, out["availability"]) + text  # AV2137-08
                if out.get("illustration"): text = POST_ILLUSTRATION + "\n" + text  # AV1352-03: only after the photo is eligible
            else:  # a refusal, or a photo that is itself a link: never attached
                reason = out.get("reason", "no photo on the site")
                text = POST_REFUSALS[reason].format(id=q(pid)) if reason in POST_REFUSALS else POST_CANT.format(id=q(pid))
                if reason not in POST_REFUSALS: self._problem("could-not-do", "post-refused")
                photo = None
                if reason == "cannot read content": raise OSError
        except LookupError:
            text = POST_USAGE
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            text, photo = CANT_READ, None
        self._reply(text, [str(photo)] if photo else [], long_ok=True)
        return "post"

    @staticmethod
    def _post_stock_line(content, pid, word) -> str:
        """AV2137-08: the warning line (with its newline) for a product whose card shows Sold out or Limited; the product's own day."""
        product = next(p for p in content.products if p.get("id") == pid)
        day = sitegen._day_text(sitegen.iso_day(product.get("available_on")))
        return f"The website shows {q(product['name'])} as {word} (checked {day}). A post now may send people in for something that is not on the shelf.\n"

    def _post_caption(self, out, failure) -> str:
        """AV1104-07: one text reply, no attachment: a builder's caption draft as is (never posted, scheduled or stored), else ``failure``."""
        self._reply("Draft post (not posted; copy it yourself):\n" + q(out["caption"]) if out["draft"] else failure, long_ok=True, ids_ok=True)
        return "post"

    def _post_notice(self) -> str:
        """AV1104-07 (F07/H13): social_draft.build_notice's caption for the home notice the saved content shows today.
        Read-only: nothing is posted, scheduled, stored or drafted; works while paused; no interpreter call or usage count."""
        try:
            out = social_draft.build_notice(load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content"), self._now())
            if not out["draft"] and out["reason"] == "cannot read content": raise OSError
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            return self._post_caption({"draft": False}, MAKER_CANT_READ)
        if out["draft"] or out["reason"] == "no notice on the website": return self._post_caption(out, NOTICE_NONE)
        self._problem("could-not-do", "post-refused")
        return self._post_caption(out, q(f"Cannot draft a notice post: {out['reason']}."))

    def _post_today(self) -> str:
        """AV1104-08 (F07/SHOP-1): social_draft.build_today's caption for the products Michael's shelf check marked Available today or
        Limited, only when that check is Pacific today. Read-only: nothing is posted, scheduled, stored or drafted; works while paused."""
        try:
            out = social_draft.build_today(load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content"), self._now())
            if not out["draft"] and out["reason"] == "cannot read content": raise OSError
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            return self._post_caption({"draft": False}, MAKER_CANT_READ)
        if out["draft"]: return self._post_caption(out, "")
        if out["reason"].endswith("."): return self._post_caption(out, out["reason"])  # the three complete-sentence reasons, verbatim
        self._problem("could-not-do", "post-refused")
        return self._post_caption(out, q(f"Cannot draft a today post: {out['reason']}."))

    def _post_maker(self, key) -> str:
        """AV1937-10 (F07): social_draft.build_maker's caption for one maker key, exactly as the builder wrote it, in chat.
        Read-only: nothing is posted, scheduled, stored or drafted; works while paused; no interpreter call or usage count."""
        try:
            if not key: raise LookupError
            out = social_draft.build_maker(load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content"), key)
            if out["draft"]: text = "Draft post (not posted; copy it yourself):\n" + q(out["caption"])
            elif out["reason"] == "cannot read content": raise OSError
            elif out["reason"] in MAKER_REFUSALS: text = MAKER_REFUSALS[out["reason"]].format(id=q(key))
            else:
                text = f"Cannot draft a post for {q(key)}: {out['reason']}."
                self._problem("could-not-do", "post-refused")
        except LookupError: text = MAKER_USAGE
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            text = MAKER_CANT_READ
        self._reply(text, long_ok=True, ids_ok=True)
        return "post"

    def _post_hike(self, hid) -> str:
        """AV1222-11 (F07): social_draft.build_hike's caption for one scheduled upcoming hike. Read-only, nothing is stored."""
        try:
            if not hid: raise LookupError
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            out = social_draft.build_hike(content, self._pick_hike(content, hid), self._now())
            if out["draft"]: text = f"Here's a post you can copy. I haven't posted anything.\n{q(out['caption'])}"
            elif out["reason"] == "cannot read content": raise OSError
            else:
                text = HIKE_REFUSALS[out["reason"]].format(id=q(hid)) if out["reason"] in HIKE_REFUSALS else POST_CANT.format(id=q(hid))
                if out["reason"] not in HIKE_REFUSALS: self._problem("could-not-do", "post-refused")
        except LookupError: text = HIKE_USAGE
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            text = CANT_READ
        self._reply(text, long_ok=True)
        return "post"

    def _pick(self, kind, text, content=None) -> str:
        """The id for what Mike typed: an exact id or maker key as before, else the one record whose name or nickname fits
        (catalog.lookup); anything else comes back unchanged so the usual 'I don't know that one' answer follows."""
        try:
            content = content or load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            ids = {p["id"] for p in content.products} if kind == "product" else set(content.makers)
            if text in ids: return text
            has_memory = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
            found = catalog.lookup(content, kind, text, aliases=self.aliases() if has_memory else None)
            matched = found.get("match")
            # Maker keys keep their exact case; only names and nicknames are folded.
            if kind == "maker" and isinstance(matched, str) and not found.get("via") \
                    and catalog._fold(text) not in catalog._fold(content.makers[matched]["name"]):
                return text
            return matched if isinstance(matched, str) else text
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            return text

    def _pick_hike(self, content, text, key="events") -> str:
        """A hike's (or, with key="routeIdeas", a route idea's) id from what Mike typed: an exact id, else the one whose
        title holds every word."""
        events = content.community.get(key) if isinstance(content.community, dict) else None
        events = [e for e in events if isinstance(e, dict)] if isinstance(events, list) else []
        if any(e.get("id") == text for e in events): return text
        words = catalog._fold(text).split()
        hits = [e for e in events if words and isinstance(e.get("title"), str) and all(w in catalog._fold(e["title"]) for w in words)]
        return hits[0]["id"] if len(hits) == 1 and isinstance(hits[0].get("id"), str) else text

    def _cost(self, msg, ident, rest) -> str:
        """AV1222-10 (F03): `cost <id>: <pack> for <units>` saves memory cost.<id> = "<pack> for <units>" (the dated,
        owner-stated, private purchase cost for an existing product, any status). Never the site or the interpreter."""
        typed, product, problem, value = ident, None, None, ""
        found = COST_RE.fullmatch(rest)
        try:
            if not found or not ident or re.fullmatch(rf"\$?{_NUM}\s+for\s+{_NUM}", ident, re.IGNORECASE): problem = COST_USAGE  # AV2137-05: a pack form is never a name
            else:
                shown = margins.compute(found[1], found[2], "0", "0")["inputs"]  # validates and normalises both numbers
                value = f"{shown['pack_cost']} for {shown['units']}"
                content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
                product, reply, several = self._purchase_product(content, ident)  # AV2137-05: an id, or the one name or nickname as that id
                if several:
                    self._reply(reply, long_ok=True, ids_ok=True)  # several fit: the find lines; nothing is saved or changed
                    return "memory-ambiguous"
                ident = product["id"] if product else ident
                problem = None if product else reply
        except margins.InputError as exc:
            problem = "I couldn't read those numbers. " + margins.plain_input_error(exc)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            problem = CANT_READ
        key, old, source = f"cost.{ident}", None, f"owner-stated:{msg.provider_id}"
        shown = f"{q(product['name'])} ({q(product['id'])})" if product else ""  # AV2137-05: the product is always named by name and id
        try:
            old = self.memory.get(key) if product else None
            if product and old == value:
                self._reply(f"I already have that cost for {shown}, so nothing changed.")
                return "memory-unchanged"
            if product: self.memory.remember(key, value, "fact", source) if old is None else self.memory.correct(key, value, source)
        except ValueError:  # e.g. an id too long for a memory key
            problem = "I couldn't keep that one. Could you say it another way?"
        if problem:
            self._problem("could-not-do", "cost-refused")
            self._reply(f"I couldn't save that. {problem}" if not problem.startswith(("Tell me", "I ")) else problem)
            return "memory-invalid"
        pack, _, units = value.partition(" for ")
        self._reply((f"Saved. {shown} costs you {pack} for {units}." if old is None else
                     f"Updated. {shown} now costs you {pack} for {units}.")
                    + f" That stays private and is never on the website. Say {q('forget cost.' + ident)} to remove it.")
        return "memory-saved" if old is None else "memory-updated"
