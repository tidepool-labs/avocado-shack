"""HASS-CLOVER-1: draft builders for every Clover write. A builder only BUILDS a draft; nothing here sends anything.

A draft says in plain words the exact change (item, SKU, price, count), carries the exact Clover calls it would make, what the item looked like
before and will look like after (the journal record, so `undo` can restore it), and the stale-check values for the moment of approval. It needs
the owner's `yes <code>` bound to the asker, like a site change (the conversation layer owns codes, expiry and binding; `render` only adds
the line that names the code). There is no delete call anywhere: removing an item is hiding it. Hass has no checkout, payment, refund,
discount or order call at all, and this module has no way to build one.

Rules the builders enforce (design question 4): a daily cap on changes (undo exempt), every price move needs just one owner yes, prices are whole cents above zero and under the configured ceiling, counts are non-negative and bounded, a changed item must still
be the one the draft was made from (`is_stale`), and an undo refuses to overwrite a value that changed after the draft.
"""
import hashlib
import json
from dataclasses import dataclass
from dataclasses import replace
from decimal import Decimal, InvalidOperation, localcontext
from types import SimpleNamespace

from hass.clover import sku as skumod
from hass.clover.mapper import (CATEGORIES, MapError, clean_name, create_payload, format_money, format_quantity, norm_name, pct_change,
                                site_category)
from hass.clover.mapper import parse_selling_price

DATA_CLASS = "finance-local"   # prices and counts: local code only; no cloud model ever sees a draft or a Clover answer
KINDS = ("create_item", "set_price", "set_stock", "set_sku", "set_hidden")
SITE_WORDS = {"yes": "Available today", "limited": "Limited", "no": "Sold out"}


class DraftRefused(MapError):
    """The change cannot be drafted. The message is the plain reply to the owner; nothing was prepared."""


@dataclass(frozen=True)
class Draft:
    kind: str
    item_id: "str | None"          # None until a create has run
    label: str                     # the item as the owner knows it
    lines: tuple                   # plain-words description of the exact change
    before: dict                   # journal: values before ({} for a create)
    after: dict                    # journal: values after
    requests: tuple                # the exact Clover calls: {"method", "path", "json"}; {newItemId} is filled from the create's answer
    base: dict                     # stale check: the item's modifiedTime and stock modifiedTime when the draft was made
    second_confirmation: bool = False
    warnings: tuple = ()
    site_ops: tuple = ()           # typed ops for the EXISTING site path ({"op": "product.set_availability", ...}); never a price or a count
    undo_of: "str | None" = None   # change_id of the draft this one reverses

    def core(self):
        return {"kind": self.kind, "item_id": self.item_id, "before": self.before, "after": self.after, "requests": list(self.requests),
                "base": self.base, "second_confirmation": self.second_confirmation, "site_ops": list(self.site_ops), "undo_of": self.undo_of}

    @property
    def draft_hash(self):
        return hashlib.sha256(json.dumps(self.core(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

    @property
    def change_id(self):
        return "clv-" + self.draft_hash[:12]

    def to_dict(self):
        return {**self.core(), "label": self.label, "lines": list(self.lines), "warnings": list(self.warnings), "data_class": DATA_CLASS,
                "change_id": self.change_id, "draft_hash": self.draft_hash}

    def render(self, code):
        """The owner-facing text: the change, any warnings, and the one line that names the code."""
        out = list(self.lines) + [f"Note: {w}" for w in self.warnings]
        out.append(f"Reply yes {code} to do this, or no {code} to drop it. Nothing changes until you say yes.")
        return "\n".join(out)


# ---------------------------------------------------------------------------------------------------------- shared helpers
def _label(item):
    return f"{item.name} (SKU {item.sku})" if item.sku else f"{item.name} (no SKU yet)"


def _base(item):
    return {"modifiedTime": item.modified_time, "stockModifiedTime": item.stock_modified}


def is_stale(draft, fresh_item):
    """True when the till item changed after the draft was made (price, SKU, hidden or count): approval must not apply it.
    A create has no item to compare; its guard is the live SKU check (`CloverClient.find_by_sku`) right before the call."""
    if draft.kind == "create_item":
        return False
    return fresh_item is None or draft.base != _base(fresh_item)


def _gate(config, writes_today):
    if writes_today >= config.daily_write_cap:
        raise DraftRefused(f"I have already made {writes_today} changes to the till today, which is my daily limit. Nothing was changed. "
                           "The count starts again at midnight Pacific.")


def _per(item):
    return f" per {item.unit_name}" if item.price_type == "PER_UNIT" and item.unit_name else " each"


def _qty(value, item, config):
    """A typed count -> Decimal, or DraftRefused. Whole numbers, except weighed (PER_UNIT) items, which allow three decimals."""
    try:
        q = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation:
        raise DraftRefused("I could not read that as a count. Send a number like 12.") from None
    if not q.is_finite() or q < 0:
        raise DraftRefused("A count cannot be less than 0.")
    if q > config.max_stock:
        try:
            with localcontext():  # display must not change the caller's decimal flags
                shown = f"{format_quantity(q)} "
        except InvalidOperation:  # too large to display: refuse without echoing it
            shown = "That count "
        raise DraftRefused(f"{shown}looks too high for one item. Check the number and send it again.")
    if item.price_type != "PER_UNIT" and q != q.to_integral():
        raise DraftRefused(f"{item.name} is counted in whole items, so {format_quantity(q)} is not a count I can set.")
    if q != q.quantize(Decimal("0.001")):
        raise DraftRefused("I keep counts to three decimal places at most.")
    return q


def _site_op(site_product, after):
    """The one site availability change that goes with a count, or None. The site never shows a count: only the word Sold out or Available."""
    if site_product is None or site_product.status != "active":
        return None
    if after == 0 and site_product.availability != "no":
        return "no"
    if after > 0 and site_product.availability == "no":
        return "yes"
    return None


def _number(q):
    return int(q) if q == q.to_integral() else float(q)


# ---------------------------------------------------------------------------------------------------------- the five builders
def build_create_item(name, price_cents, category, items, config, *, categories=(), writes_today=0):
    """'new item: Sunshine olive oil, 12.50, pantry' -> a draft to add a till item with a fresh SKU. `categories` is [(clover_id, name)]."""
    _gate(config, writes_today)
    name = clean_name(name)
    if category is not None and category not in CATEGORIES:
        raise DraftRefused("I know these categories: " + ", ".join(CATEGORIES) + ". Which one is it?")
    if type(price_cents) is not int or not 0 < price_cents <= config.max_price_cents:
        raise DraftRefused(f"A price has to be between $0.01 and {format_money(config.max_price_cents)}.")
    try:
        sku = skumod.generate_sku(name, category, items)
    except skumod.DuplicateItem as dup:
        have = dup.item
        raise DraftRefused(f"{have.name} is already in the till" + (f" (SKU {have.sku})" if have.sku else "")
                           + ". Did you mean to change its price or its count?") from None
    wanted = config.category_map.get(category) if category else None
    cat_id = next((cid for cid, cname in categories if wanted and norm_name(cname) == norm_name(wanted)), None)
    warnings = []
    if category and cat_id is None:
        warnings.append(f"the till has no category called {wanted or category}, so the item is added with no category")
    payload = create_payload(name, price_cents, sku)
    requests = [{"method": "POST", "path": "/items", "json": payload}]
    if cat_id:
        requests.append({"method": "POST", "path": "/category_items",
                         "json": {"elements": [{"category": {"id": cat_id}, "item": {"id": "{newItemId}"}}]}})
    lines = ("Did you mean to add this to the till?",
             f"  Item: {name}",
             f"  SKU: {sku} (made up by me, the next free number)",
             f"  Price: {format_money(price_cents)} each",
             f"  Category: {wanted if cat_id else 'none'}",
             "  Count: not counted yet (say 'received 12 " + name + "' to start counting)",
             "  Tax: your till's usual setting; I set none",
             "Nothing goes on the website.")
    return Draft("create_item", None, name, lines, {}, {"name": name, "sku": sku, "price": price_cents, "hidden": False},
                 tuple(requests), {}, warnings=tuple(warnings))


def build_create_counted(name, price_text, category, quantity, items, config, *, categories=(), writes_today=0):
    """Draft a new item and its first count for a single bundle approval."""
    try:
        cents, unit = parse_selling_price(price_text)
    except MapError as exc:
        raise DraftRefused(str(exc)) from None
    create = build_create_item(name, cents, category, items, config, categories=categories, writes_today=writes_today)
    first, *category_requests = create.requests
    price_basis = {"priceType": "PER_UNIT", "unitName": unit} if unit else {}
    if price_basis:
        first = {**first, "json": {**first["json"], **price_basis}}
    item = SimpleNamespace(name=create.label, price_type=first["json"]["priceType"], unit_name=unit)
    count = _qty(quantity, item, config)
    stock = format_quantity(count)
    headline, item_line, sku_line, _, category_line, *_ = create.lines
    lines = (headline, item_line, sku_line, f"  Price: {format_money(cents)}{_per(item)}", category_line,
             f"  Count: {stock}", "  On the register: showing")
    # The bundle removes this placeholder from the first step and builds a literal-ID stock draft after creation.
    stock_request = {"method": "PUT", "path": "/item_stocks/{newItemId}", "json": {"quantity": _number(count)}}
    return replace(create, lines=lines, after={**create.after, **price_basis, "stock": stock},
                   requests=(first, *category_requests, stock_request))


def build_set_price(item, new_cents, config, *, writes_today=0):
    """'change price of X to 14.00'. Refuses a variable-price item, no change or a bad number; one owner yes for any price move."""
    _gate(config, writes_today)
    if item.price_type == "VARIABLE" or item.price_cents is None:
        raise DraftRefused(f"{item.name} is priced at the register each time, so there is no price for me to change.")
    if type(new_cents) is not int or not 0 < new_cents <= config.max_price_cents:
        raise DraftRefused(f"A price has to be between $0.01 and {format_money(config.max_price_cents)}.")
    if new_cents == item.price_cents:
        raise DraftRefused(f"{item.name} is already {format_money(item.price_cents)}. Nothing to change.")
    pct = pct_change(item.price_cents, new_cents)
    big = abs(new_cents - item.price_cents) * 100 > config.price_confirm_pct * item.price_cents   # exact integer test, not the rounded percentage
    warnings = [f"that is a {abs(pct)}% {'increase' if pct > 0 else 'decrease'}"] if big else []
    if item.hidden:
        warnings.append("this item is hidden on the till")
    lines = (f"Change the price of {_label(item)}?",
             f"  Price: {format_money(item.price_cents)} -> {format_money(new_cents)}{_per(item)} ({'+' if pct > 0 else ''}{pct}%)")
    return Draft("set_price", item.id, item.name, lines, {"price": item.price_cents}, {"price": new_cents},
                 ({"method": "POST", "path": f"/items/{item.id}", "json": {"price": new_cents}},), _base(item),
                 warnings=tuple(warnings))


CLEAR = "clear"   # _site_restore's answer for "the product had no word before": the undo takes the word off (product.clear_availability)
UNKNOWN_SITE = ("I can't tell what the website said before that change, so I can't undo it safely. Nothing was changed. "
                "Tell me the count you want, and the website word if it needs one.")


def _site_restore(entry, site_product):
    """What puts the site back EXACTLY as it was before `entry`: a word from SITE_WORDS, CLEAR when the product had no word (the undo takes
    the word off; it never invents 'Available today'), or None for no site change. The journal (`before`/`after` "site") names the product
    and both words; the site is restored only while the product still shows the word that draft set, so a newer site change is never
    overwritten. A journal that does not say what the site showed raises DraftRefused: an undo that cannot restore it does not run."""
    mine = (entry.get("before") or {}).get("site"), (entry.get("after") or {}).get("site")
    if not all(isinstance(x, dict) for x in mine) or site_product is None or site_product.status != "active":
        return None
    prior, applied = mine
    if site_product.id != applied.get("id") or site_product.availability != applied.get("available"):
        return None
    if "available" not in prior or (prior["available"] is not None and prior["available"] not in SITE_WORDS):
        raise DraftRefused(UNKNOWN_SITE)
    word = prior["available"]
    if word == site_product.availability:
        return None
    return CLEAR if word is None else word


def _stock_draft(item, after, config, *, headline, extra, site_product, undo_of=None, site_word=None):
    before = item.stock
    if before == after:
        raise DraftRefused(f"{item.name} already shows {format_quantity(after)}. Nothing to change.")
    word = site_word if undo_of else _site_op(site_product, after)    # an undo restores the journalled word; it never recomputes one
    lines = [headline, f"  Count: {format_quantity(before) if before is not None else 'not counted'} -> {format_quantity(after)}"] + extra
    warnings = []
    if before is None:
        warnings.append("the till was not counting this item; this starts the count")
    if item.hidden:
        warnings.append("this item is hidden on the till")
    site_ops, journal_before, journal_after = (), {"stock": None if before is None else format_quantity(before)}, {"stock": format_quantity(after)}
    if word == CLEAR:   # only an undo gets here: the product had no word before, so the word comes off again
        lines.append(f"  Website: takes the stock word off {site_product.name}, as it was before (same yes; the site shows a word, never a count)")
        site_ops = ({"op": "product.clear_availability", "args": {"id": site_product.id}},)
        journal_before["site"] = {"id": site_product.id, "available": site_product.availability}
        journal_after["site"] = {"id": site_product.id, "available": None}
    elif word:
        lines.append(f"  Website: marks {site_product.name} as {SITE_WORDS[word]} (same yes; the site shows a word, never a count)")
        site_ops = ({"op": "product.set_availability", "args": {"id": site_product.id, "available": word}},)
        # the journal keeps the word the site showed before, so an undo restores it instead of recomputing one
        journal_before["site"] = {"id": site_product.id, "available": site_product.availability}
        journal_after["site"] = {"id": site_product.id, "available": word}
    return Draft("set_stock", item.id, item.name, tuple(lines), journal_before, journal_after,
                 ({"method": "PUT", "path": f"/item_stocks/{item.id}", "json": {"quantity": _number(after)}},),
                 _base(item), warnings=tuple(warnings), site_ops=site_ops, undo_of=undo_of)


def build_set_stock(item, quantity, config, *, site_product=None, writes_today=0):
    """'set Sunshine olive oil to 7'. `quantity` 0 is 'sold out'."""
    _gate(config, writes_today)
    q = _qty(quantity, item, config)
    head = f"Mark {_label(item)} as sold out?" if q == 0 else f"Set the count of {_label(item)}?"
    return _stock_draft(item, q, config, headline=head, extra=[], site_product=site_product)


def build_received(item, received, config, *, site_product=None, writes_today=0):
    """'received 12 Sunshine olive oil' -> the new count is the till's current count plus 12, shown as both numbers."""
    _gate(config, writes_today)
    got = _qty(received, item, config)
    if got == 0:
        raise DraftRefused("Received how many? The number has to be more than 0.")
    if item.stock is None:
        raise DraftRefused(f"The till is not counting {item.name} yet, so I cannot add to a count. "
                           f"Say how many there are now: set {item.name} to <number>.")
    after = _qty(item.stock + got, item, config)
    return _stock_draft(item, after, config, headline=f"Add stock to {_label(item)}?", extra=[f"  Received: {format_quantity(got)}"],
                        site_product=site_product)


def build_set_sku(item, items, config, *, category=None, writes_today=0):
    """'give Sunshine olive oil a SKU': only for an item with no SKU. An item that has one keeps it for good."""
    _gate(config, writes_today)
    if item.sku:
        raise DraftRefused(f"{item.name} already has the SKU {item.sku}. I never change a SKU once it is set.")
    cat = category or site_category(item, config.category_map)
    try:
        sku = skumod.generate_sku(item.name, cat, [i for i in items if i.id != item.id])
    except skumod.DuplicateItem as dup:
        raise DraftRefused(f"The till has another item also called {dup.item.name}. Rename one of them first, then ask me again.") from None
    return Draft("set_sku", item.id, item.name, (f"Give {item.name} a SKU?", f"  SKU: none -> {sku} (made up by me, the next free number)"),
                 {"sku": ""}, {"sku": sku}, ({"method": "POST", "path": f"/items/{item.id}", "json": {"sku": sku}},), _base(item))


def build_set_hidden(item, hidden, config, *, writes_today=0, undo_of=None):
    """Hide or show an item on the till. This is the only way an item leaves the till: nothing is deleted."""
    if undo_of is None:
        _gate(config, writes_today)
    if item.hidden == hidden:
        raise DraftRefused(f"{item.name} is already {'hidden' if hidden else 'showing'} on the till.")
    verb = "Hide" if hidden else "Show"
    return Draft("set_hidden", item.id, item.name, (f"{verb} {_label(item)} on the till?",
                 f"  On the till: {'showing' if item.hidden else 'hidden'} -> {'hidden' if hidden else 'showing'}",
                 "  Nothing is deleted; you can show it again."), {"hidden": item.hidden}, {"hidden": hidden},
                 ({"method": "POST", "path": f"/items/{item.id}", "json": {"hidden": hidden}},), _base(item), undo_of=undo_of)


# ---------------------------------------------------------------------------------------------------------- undo
def build_undo(entry, current, config, *, site_product=None):
    """The draft that restores the values before `entry` (a journalled Draft.to_dict(), plus `result_item_id` for a create).
    `current` is the till item read right now. Undo is exempt from the daily cap and from the big-change second yes, because it only
    puts back what was there; it still needs its own yes. It refuses when the item changed after the draft: it never overwrites newer values."""
    if entry.get("result_base") is not None and (current is None or _base(current) != entry["result_base"]):
        raise DraftRefused("The item was changed again; I will not undo over a newer value.")
    kind, cid = entry["kind"], entry["change_id"]
    if current is None:
        raise DraftRefused("I can't find that item in the till any more, so I can't undo the change.")
    moved = DraftRefused(f"{current.name} was changed again after that, so I will not undo over the newer value. Tell me the value you want.")
    if kind == "create_item":
        if current.id != entry.get("result_item_id") or current.hidden:
            raise moved
        return build_set_hidden(current, True, config, undo_of=cid)
    if kind == "set_price":
        if current.price_cents != entry["after"]["price"]:
            raise moved
        return _undo_price(current, entry["before"]["price"], cid)
    if kind == "set_stock":
        if current.stock is None or format_quantity(current.stock) != entry["after"]["stock"]:
            raise moved
        if entry["before"]["stock"] is None:
            raise DraftRefused("That change started the count for this item, and I never delete a count. "
                               f"Tell me the number you want: set {current.name} to <number>.")
        return _stock_draft(current, Decimal(entry["before"]["stock"]), config, headline=f"Undo: put the count of {_label(current)} back?",
                            extra=[], site_product=site_product, undo_of=cid, site_word=_site_restore(entry, site_product))
    if kind == "set_sku":
        if current.sku != entry["after"]["sku"]:
            raise moved
        return Draft("set_sku", current.id, current.name, (f"Undo: take the SKU off {current.name}?", f"  SKU: {current.sku} -> none"),
                     {"sku": current.sku}, {"sku": ""}, ({"method": "POST", "path": f"/items/{current.id}", "json": {"sku": ""}},),
                     _base(current), undo_of=cid)
    if kind == "set_hidden":
        if current.hidden != entry["after"]["hidden"]:
            raise moved
        return build_set_hidden(current, entry["before"]["hidden"], config, undo_of=cid)
    raise DraftRefused("I do not know how to undo that kind of change.")


def _undo_price(item, old_cents, undo_of):
    return Draft("set_price", item.id, item.name, (f"Undo: put the price of {_label(item)} back?",
                 f"  Price: {format_money(item.price_cents)} -> {format_money(old_cents)}{_per(item)}"),
                 {"price": item.price_cents}, {"price": old_cents},
                 ({"method": "POST", "path": f"/items/{item.id}", "json": {"price": old_cents}},), _base(item), undo_of=undo_of)
