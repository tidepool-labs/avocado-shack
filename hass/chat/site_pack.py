"""Site pack: read-only catalog commands `find`, `listing`, `hidden` and `photos to take` (Conversation mixin).

AVB-12: moved verbatim out of hass/conversation.py, which imports every name back (hass.conversation.<name> is
unchanged). The methods run on the Conversation (self is the conversation): they use its store, replies and
settings exactly as before. Command routing stays in Conversation._command.
"""
import os, stat, unicodedata  # noqa: E401
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from hass import editor as editor_mod, preview as preview_mod, sitegen, voice
from hass.chat.shared import CANT_READ, FIND_TEXT_MAX, load_content, LOCAL_TZ, q, STATUS_PLAIN
from hass.content_model import _text as checked_text, ContentError, DEFAULT_HEADLINE, DEFAULT_INTRO, DEFAULT_STORY, HOME_IMAGE_RE, iso_day, load_and_validate, SHELF_LABELS, shop_today, validate
from hass.ops import catalog

SHELF_MAX = 60  # AV1052-05: products listed by `shelf <name>`, then "... and N more"
SHELF_NEW_DAYS = 14  # AV0222-09 / shop.js NEW_BADGE_DAYS: a product added 0..13 Pacific days ago shows New and comes first
PHOTOS_TO_TAKE_MAX = 5  # AV0222-04, HASS-VOICE-1: names listed by `photos to take` (a short list, then ask again)

HIDDEN_MAX = 20  # AV1222-13: lines of the hidden list
HELD_MAX = 20  # AV2137-07: held products listed by `held`, then "... and N more"
LISTING_DESC_MAX = 120  # AV1622-09: characters of a product description in `listing`

LISTING_STORY_MAX = 80  # AV1052-06: characters of the story in `listing store`
LISTING_HEAD = "This is from my saved copy, not a live look at the website:"
LISTING_USAGE = "Which one? Say " + q("listing <id, name or alias>") + ", like " + q("listing Etto") + "; " + q("find <words>") + " looks it up."  # AV1052-07
LISTING_NONE = "I don't know that one. Try " + q("find") + " and a word from its name."
LISTING_MANY = "That fits more than one thing. Could you say a bit more of its name?"

FIND_MAX, FIND_USAGE = 10, "Tell me a word or two to look for, like " + q("find lion's mane") + "."  # AV1537-04


LOOK_OK = "The website now (private preview, phone):"  # AV1922-01
LOOK_FAIL = "I could not take a picture of the site right now; nothing changed."
LOOK_USAGE = "Send " + q("look") + ", " + q("look hike") + ", or " + q("look <product id or name>") + "; use " + q("find") + " for ids."
LOOK_ABSENT = "{id} is not on the site; send " + q("find <words>") + " for ids."
LOOK_NONE = "No active product matches {id}; send " + q("find <words>") + " for ids."
LOOK_MANY = "That fits more than one active product; send " + q("look") + " and the id:"
NAME_MORE = "There are more. Add a word to narrow it down."  # AV1052-07: a lookup that filled its 10 may have more


class SitePack:
    """Site pack commands, mixed into Conversation."""

    def _look_product(self, content, query):
        """AV1922-01: ("one", record) for the one active product the query names (exact id first, then name or saved alias),
        ("absent", id) for an exact id that is hidden or held, ("none", None) or ("many", [records]). Read-only."""
        for p in content.products:
            if p.get("id") == query: return ("one", p) if p.get("status") == "active" else ("absent", query)
        hits = self._active_hits(content, query)
        return ("one", hits[0]) if len(hits) == 1 else ("many", hits) if hits else ("none", None)

    def _active_hits(self, content, query):
        """AV1052-07: the active products a name or saved alias names (catalog.lookup, <= 10, sorted by id). Only active
        products are in the view the lookup sees, so held or hidden rows can neither match nor use up its 10; the memory
        table is read only when it already exists (aliases() would create it). Read-only."""
        active = [p for p in content.products if p.get("status") == "active"]
        has_memory = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
        found = catalog.lookup(SimpleNamespace(products=active, makers={}), "product", query,
                               aliases=self.aliases() if has_memory else None)
        ids = [found["match"]] if "match" in found else [c["id"] for c in found["candidates"]]
        return [p for p in active if p["id"] in ids]

    def _names_a_product(self, content, query) -> bool:
        """AV1052-07: True when the query fits a product of ANY status by name, brand or saved alias (so it is a name, not a
        sentence). Read-only; the memory table is never created."""
        has_memory = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
        found = catalog.lookup(content, "product", query, aliases=self.aliases() if has_memory else None)
        return "match" in found or bool(found["candidates"])

    @staticmethod
    def _many_lines(hits) -> str:
        """AV1052-07: find-style lines (id, name, status) for several matches; the tail when the lookup was full.
        AV2137-05: cost and margin list products of any status, so each line carries its own (post and listing pass active ones)."""
        lines = [f"product {p['id']}: " + q(p["name"]) + f" ({p.get('status', 'active')})" for p in sorted(hits, key=lambda p: p["id"])[:FIND_MAX]]
        return "\n".join(lines + ([NAME_MORE] if len(hits) >= catalog.MAX_CANDIDATES else []))

    @staticmethod
    def _bad_query(query) -> bool:
        """AV1052-07: a product query is 1 to FIND_TEXT_MAX characters on one line."""
        return not query or len(query) > FIND_TEXT_MAX or any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in query)

    def _product_for(self, content, query):
        """AV1052-07: (product id, None) for what a post or listing names, or (None, reply). An exact id of any status acts as
        before (never case-repaired or rematched by name); else exactly one active product by name or alias acts as its id,
        several give the find lines and none says to use find. One unknown word keeps the old 'I don't know' answer."""
        if any(p.get("id") == query for p in content.products): return query, None
        hits = self._active_hits(content, query)
        if len(hits) == 1: return hits[0]["id"], None
        if hits: return None, self._many_lines(hits)
        return (query, None) if len(query.split()) == 1 else (None, LOOK_NONE.format(id=q('"' + query + '"')))

    def _look_path(self, now):
        """A fresh private screenshot path look-<UTC stamp>.png (microseconds; never an existing name), or None when the
        screenshots folder is a link or not a folder."""
        folder = self.sdir / "screenshots"
        if os.path.lexists(folder) and (os.path.islink(folder) or not os.path.isdir(folder)): return None
        at = now.astimezone(timezone.utc)
        for _ in range(1000):
            path = folder / f"look-{at.strftime('%Y%m%dT%H%M%S%fZ')}.png"
            if not os.path.lexists(path): return path
            at += timedelta(microseconds=1)
        return None

    def _look(self, arg) -> str:
        """AV1922-01 (H06/H17): a fresh phone-width picture of the private preview as it is now: `look` the home page,
        `look hike` /hike, `look <product>` that product's card. Same previewer as the proposal pictures, no overlay files,
        a target from the current writer-worktree content. Read-only: no draft, expiry sweep, interpreter call or usage
        count; works while paused. Any failure is the one fixed sentence and no picture."""
        if arg is None:
            self._reply(LOOK_USAGE, ids_ok=True)
            return "look"
        text, photo = LOOK_FAIL, []
        try:
            now = self._now()
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            record, refusal = None, None
            if not arg: record = {"collection": "store", "after": content.store}
            elif arg.lower() == "hike": record = {"collection": "events", "key": "", "after": {}}
            else:
                kind, found = self._look_product(content, arg)
                if kind == "one": record = {"collection": "products", "key": found["id"], "after": found}
                elif kind == "absent": refusal = LOOK_ABSENT.format(id=found)
                elif kind == "none": refusal = LOOK_NONE.format(id='"' + arg + '"')
                else:
                    lines = [f"{p['id']} - {p['name']}" for p in sorted(found, key=lambda p: p["id"])]
                    refusal = "\n".join([LOOK_MANY] + lines[:FIND_MAX] + (["There are more. Add a word to narrow it down."] if len(found) >= catalog.MAX_CANDIDATES else []))
            if refusal: text = refusal
            elif self.previewer is not None:
                out = self._look_path(now)
                shot = out and self.previewer.capture({}, preview_mod.target_for(record, shop_today(now)), out, viewports=("phone",))
                checks = shot.get("checks") if isinstance(shot, dict) else None
                if (out and shot["ok"] is True and shot.get("png") == str(out) and isinstance(checks, dict) and checks
                        and all(v is True for v in checks.values()) and stat.S_ISREG(os.lstat(out).st_mode)):
                    text, photo = LOOK_OK, [str(out)]
        except Exception:  # noqa: BLE001 - never raise past a chat reply, never show the cause
            text, photo = LOOK_FAIL, []
        self._reply(text, photo, long_ok=True, ids_ok=True)
        return "look"

    def _listing_names_something(self, text) -> bool:
        """Like post, a multiword listing needs a known name; unreadable content gets the usual read error. AV1052-07: a product
        of any status counts (the answer then lists the active ones or says none is active); a sentence stays a sentence."""
        try:
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            return True
        return not self._bad_query(text) and (self._names_a_product(content, text) or self._pick("maker", text, content) != text
                                             or self._pick_hike(content, text) != text or self._pick_hike(content, text, "routeIdeas") != text
                                             or self._title_matches(content, text))

    @staticmethod
    def _title_matches(content, text) -> bool:
        """True when some hike or route idea title holds every word, even if several do (the listing then says it is not sure)."""
        words = catalog._fold(text).split()
        if not words or not isinstance(content.community, dict): return False
        return any(isinstance(e, dict) and isinstance(e.get("title"), str) and all(w in catalog._fold(e["title"]) for w in words)
                   for key in ("events", "routeIdeas") for e in (content.community.get(key) if isinstance(content.community.get(key), list) else []))

    def _find(self, query) -> str:
        """AV1537-04: read-only lookup, products then makers; id/name/status only, never a draft or a memory table."""
        try:  # the current catalog, read from the writer worktree as _hike_lines does
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_content(wt / "hass" / "content")
            try:  # AV1322-04: a malformed event/route idea is worded or skipped below; any other problem is unavailable
                validate(content, wt / "storefront-mockup")
            except ContentError as exc:
                if any(not p.startswith(("events[", "routeIdeas[")) for p in exc.problems): raise
            shown = []  # the fields a reply line repeats get the validator's text checks: no line break/markup injection
            for key in ("events", "routeIdeas"):
                for i, r in enumerate(content.community[key] if isinstance(content.community[key], list) else []):
                    for field in ("id", "title", "status") if isinstance(r, dict) else ():
                        if r.get(field) is not None and (field != "title" or isinstance(r[field], str)):
                            checked_text(shown, f"{key}[{i}].{field}", r[field])
            if shown: raise ContentError(shown)
            has_memory = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
            aliases, lines, capped = self.aliases() if has_memory else {}, [], False
            records = {"product": {p["id"]: (p["name"], p["status"]) for p in content.products},
                       "maker": {k: (m["name"], "hidden" if m.get("hidden") else "visible") for k, m in content.makers.items()}}
            for kind in ("product", "maker"):
                found = catalog.lookup(content, kind, query, aliases=aliases)
                ids = [found["match"]] if "match" in found else [c["id"] for c in found["candidates"]]
                capped |= len(ids) >= catalog.MAX_CANDIDATES
                lines += [f"{q(records[kind][i][0])} ({STATUS_PLAIN.get(records[kind][i][1], 'not sure')}"
                          + (", your nickname" if found.get("via") else "") + ")" for i in ids]
            words = catalog._fold(query).split()  # AV1322-04: hikes by start, then route ideas by title
            def hits(recs): return [r for r in recs if isinstance(r, dict) and isinstance(r.get("title"), str)
                                    and words and all(w in catalog._fold(r["title"]) for w in words)]
            def when(event):  # Pacific start, or None when startsAt does not parse (never raises)
                try:
                    at = datetime.fromisoformat(event["startsAt"].replace("Z", "+00:00"))
                    return at.astimezone(LOCAL_TZ) if at.tzinfo else None
                except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
                    return None
            dated = sorted(((e, when(e)) for e in hits(content.community["events"])),
                           key=lambda pair: (pair[1] is None, pair[1].timestamp() if pair[1] else 0))
            lines += [f"{q(e['title'])} (hike, " + (voice.natural(at, self._now()) if at else "no date I can read")
                      + f", {STATUS_PLAIN.get(e.get('status'), 'not sure')})" for e, at in dated]
            lines += [f"{q(r['title'])} (route idea, {STATUS_PLAIN.get(r.get('status'), 'not sure')})"
                      for r in sorted(hits(content.community["routeIdeas"]), key=lambda r: catalog._fold(r["title"]))]
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            self._problem("error", "shop-list-unreadable")
            self._reply(CANT_READ)
            return "find"
        more = len(lines) - FIND_MAX
        tail = ["There are more. Add a word to narrow it down."] if more > 0 or capped else []
        self._reply("\n".join(lines[:FIND_MAX] + tail) if lines
                    else f"I couldn't find anything called {q(query)}.", long_ok=True)
        return "find"

    def _listing_store(self) -> str:
        """AV1052-06 (H13/H17): `listing store` replies the saved store words as the site shows them (effective defaults, no
        HTML): address, hours, phone, intro, headline, the first 80 characters of the story, home photo, home notice, last
        shelf check. Read-only, writer worktree content strictly validated; one safe reply (nothing partial) when it cannot be read."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            store = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup").store
            now = self._now()
            today = shop_today(now)  # one Pacific day for the notice and the shelf-check sentences
            first, second = store.get("headline") or DEFAULT_HEADLINE
            story = store.get("story") or DEFAULT_STORY
            home = store.get("homeImage")  # every saved word goes through q(): shown as saved, never judged by the voice check
            lines = [LISTING_HEAD, "Store", f"Address: {q(store['streetAddress'])} · {q(store['town'])}", "Hours:"]
            lines += [f"- {q(line)}" for line in store["hours"]]
            if store.get("phone"): lines.append(f"Phone: {q(sitegen.phone_text(store['phone']))}")
            lines += [f"Intro: {q(store.get('intro') or DEFAULT_INTRO)}", f"Headline: {q(first)}", q(second),
                      "Story: " + q(story[:LISTING_STORY_MAX]) + ("…" if len(story) > LISTING_STORY_MAX else ""),
                      f"Home photo: yours - {q(home['imageAlt'])}" if home else "Home photo: the shop's own photo"]
            if store.get("notice"):
                notice = self._notice_line(now)
                if notice is None: raise ValueError("notice")
                lines.append(q(notice))
            checked = sitegen.checked_line(store, today)
            lines.append(q(checked) if checked else "Shelf check: not done yet")
            text = "\n".join(lines)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            text = CANT_READ
        self._reply(text, long_ok=True)
        return "listing"

    def _listing(self, ident) -> str:
        """AV1622-09 (H17): read-only view of one saved product, maker, hike or route idea by exact id, from the writer
        worktree content (strictly validated). Nothing is drafted or stored; works while paused.
        AV1052-06: the whole word `store` (any case) is the store itself, reserved ahead of any id."""
        if not ident:
            self._reply(LISTING_USAGE)
            return "listing"
        if ident.casefold() == "store": return self._listing_store()
        if self._bad_query(ident):  # AV1052-07: a blank, over-long or several-line name is the usage, never the interpreter
            self._reply(LISTING_USAGE, ids_ok=True)
            return "listing"
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_content(wt / "hass" / "content")
            validate(content, wt / "storefront-mockup")
            def collect(i):
                f = [("product", p) for p in content.products if p.get("id") == i]
                f += [("maker", m) for k, m in content.makers.items() if k == i]
                return f + [(kind, r) for kind, key in (("hike", "events"), ("route idea", "routeIdeas"))
                            for r in content.community[key] if r.get("id") == i]
            found = collect(ident)  # an exact id/key of any kind beats every name/title fallback
            hits = []
            if not found:  # AV1052-07: one active product by name or alias, else a maker, hike or route idea as before
                typed, hits = ident, self._active_hits(content, ident)
                ident = hits[0]["id"] if len(hits) == 1 else typed
                if ident == typed: ident = self._pick("maker", typed, content)
                if ident == typed: ident = self._pick_hike(content, typed)
                if ident == typed: ident = self._pick_hike(content, typed, "routeIdeas")
                found = collect(ident)
            if len(found) != 1:
                text = LISTING_MANY if found else self._many_lines(hits) if hits else LISTING_NONE
            else:
                kind, rec = found[0]
                nope = "nothing yet"
                if kind == "product":
                    maker = content.makers.get(rec.get("producerKey"))
                    desc = rec.get("description")
                    if isinstance(desc, str) and desc:  # held records skip validate_products' description check
                        bad = []
                        checked_text(bad, "description", desc)
                        if bad: raise ValueError(bad[0])
                    desc = nope if not isinstance(desc, str) or not desc else desc[:LISTING_DESC_MAX] + ("…" if len(desc) > LISTING_DESC_MAX else "")
                    avail = (sitegen.availability_label(rec, content.store, shop_today(self._now())) or "not confirmed") \
                        if rec["status"] == "active" else "not showing"
                    fields = [("Name", rec["name"]), ("Maker", (maker or {}).get("name") or rec.get("brand") or nope),
                              ("Shelf", SHELF_LABELS.get(rec.get("category"), rec.get("category")) or nope), ("Description", desc),
                              ("Availability", avail), ("Status", STATUS_PLAIN.get(rec["status"], "not sure"))]
                    if rec["status"] == "active" and "sellingPrice" in rec:
                        fields.append(("Selling price", f"${rec['sellingPrice']}"))
                elif kind == "maker":
                    fields = [("Name", rec["name"]), ("Place", rec.get("place") or nope),
                              ("Products showing", sum(1 for p in content.products if p["status"] == "active" and p.get("producerKey") == ident)),
                              ("Status", "hidden" if rec.get("hidden") else "on the website")]
                elif kind == "hike":
                    fields = [("Title", rec["title"]), ("Starts", voice.natural_iso(rec["startsAt"], self._now())),
                              ("Status", STATUS_PLAIN.get(rec["status"], "not sure")),
                              ("Meeting place", rec.get("meetingPoint") or nope), ("Guest limit", rec.get("capacity", nope))]
                else:
                    fields = [("Title", rec["title"]), ("Place", rec.get("place") or nope), ("Status", STATUS_PLAIN.get(rec["status"], "not sure"))]
                text = "\n".join(["This is from my saved copy, not a live look at the website:"] + [f"{k}: {q(v)}" for k, v in fields])
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            text = CANT_READ
        self._reply(text, long_ok=True, ids_ok=True)
        return "listing"

    def _photos_to_take(self) -> str:
        """AV0222-04 (H10/H17): active products whose image is not an installed photo-<16 hex> file, by shelf in site order;
        saved content only, read-only, works while paused. A filename convention, not proof of where a picture came from."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
            order = tuple(SHELF_LABELS)
            todo = sorted((p for p in content.active_products() if not HOME_IMAGE_RE.fullmatch(p["image"])),
                          key=lambda p: (order.index(p["category"]), p["name"].casefold(), p["id"]))
            lines, shelf = [], None
            for p in todo[:PHOTOS_TO_TAKE_MAX]:
                lines.append(f"- {q(' '.join(str(p['name']).split()))} ({SHELF_LABELS[p['category']]})")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            self._reply(CANT_READ)
            return "photos"
        if not todo:
            self._reply("Every product on the website has your own photo.")
            return "photos"
        more = ["When you've sent those, ask again and I'll show the next few."] if len(todo) > PHOTOS_TO_TAKE_MAX else []
        self._reply("\n".join(["Some products still show a stock picture instead of your own photo. The first few:"] + [
            l if l.startswith("- ") else f"{l}" for l in lines] + more
            + ["To replace one, send a photo with the product's name as the caption."]), long_ok=True)
        return "photos"

    def _shelf(self, rest, now) -> str:
        """AV1052-05 (H17/SHOP-1): one shelf's active products in site order, each with the word the site shows for it.
        Read-only: the saved writer worktree, never the live site; hidden and held products are left out; works while paused."""
        wanted = " ".join(str(rest or "").split()).lower()
        key = next((k for k, label in SHELF_LABELS.items() if wanted in (k, label.lower())), None)
        if key is None:
            self._reply("Choose a shelf: " + ", ".join(SHELF_LABELS.values()) + ".", long_ok=True)
            return "shelf"
        try:  # the current catalog from the writer worktree, as report; never a default or partial list
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
            today = shop_today(now)
            records = [p for p in content.active_products() if p.get("category") == key]
            day = today.toordinal()

            def age(p):  # the site's New rule (shop.js isNew): added 0..13 Pacific days ago
                added = iso_day(p.get("addedOn"))
                return day - added.toordinal() if added is not None and 0 <= day - added.toordinal() < SHELF_NEW_DAYS else None
            fresh = sorted((p for p in records if age(p) is not None), key=lambda p: -iso_day(p["addedOn"]).toordinal())
            records = fresh + [p for p in records if age(p) is None]  # sorted() is stable: ties keep site order
            one = lambda name: " ".join(str(name).split())
            lines = []
            for p in records[:SHELF_MAX]:
                word = sitegen.availability_label(p, content.store, today)
                lines.append(f"- {one(p['name'])}" + (f" - {word}" if word else ""))
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shelf-unreadable")
            self._reply(CANT_READ)  # the spec's wording names the catalog, which voice.check refuses; nothing changed is said
            return "shelf"
        more = [f"... and {len(records) - SHELF_MAX} more"] if len(records) > SHELF_MAX else []
        self._reply("\n".join([f"Shelf: {SHELF_LABELS[key]}"] + (lines + more if lines else ["No products on this shelf."])), long_ok=True)
        return "shelf"

    def _hidden(self) -> str:
        """AV1222-13 (H03): read-only list of hidden products then hidden makers; held products and visible makers never."""
        try:  # the current catalog from the writer worktree, as _find
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            one = lambda name: " ".join(str(name).split())  # stored text on one line
            lines = [f"- {q(one(p['name']))}" for p in sorted(content.products, key=lambda p: p["id"])
                     if p["status"] == "hidden"]
            first = next((one(p["name"]) for p in sorted(content.products, key=lambda p: p["id"]) if p["status"] == "hidden"), None)
            lines += [f"- {q(one(m['name']))} (maker)" for k, m in sorted(content.makers.items()) if m.get("hidden") is True]
            first = first or next((one(m["name"]) for k, m in sorted(content.makers.items()) if m.get("hidden") is True), "")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            self._reply(CANT_READ)
            return "hidden"
        more = ["And a few more."] if len(lines) > HIDDEN_MAX else []
        self._reply("\n".join(["These are hidden right now:"] + lines[:HIDDEN_MAX] + more
                               + ["To bring one back, tell me, like " + q(f"Bring back {first}") + "."])
                    if lines else "Nothing is hidden right now.", long_ok=True)
        return "hidden"

    def _held(self) -> str:
        """AV2137-07 (H03/H17): the held products (id, name, the recorded hold reason and source), by id, up to HELD_MAX. Read-only:
        the saved copy only, never a release, a restore or a safety verdict; stored text that cannot be read refuses the whole list."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_content(wt / "hass" / "content")
            validate(content, wt / "storefront-mockup")
            one = lambda text: " ".join(text.split())  # stored text on one line, nothing cut
            held = []
            for p in sorted((p for p in content.products if p["status"] == "held"), key=lambda p: p["id"]):
                hold = p["hold"]
                reason, source = one(hold["reason"]), hold["source"]
                if not reason or not isinstance(source, str) or source != source.strip() or any(c.isspace() or not c.isprintable() for c in source):
                    raise ValueError("unreadable hold")
                held.append(f"- {q(p['id'])}: {q(one(p['name']))} \u2014 {q(reason)} (source {q(source)})")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            self._reply(CANT_READ)
            return "held"
        if not held:
            self._reply("No products are held.")
            return "held"
        more = [f"... and {len(held) - HELD_MAX} more"] if len(held) > HELD_MAX else []
        self._reply("\n".join(["Held products:"] + held[:HELD_MAX] + more + [voice.HELD_GUIDANCE]), long_ok=True)
        return "held"
