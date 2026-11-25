"""HCI-10: the exact reverse of an applied till inventory change. This module only PLANS and PREVIEWS the reverse; it sends nothing.

`undo <code>` reverses what a bundle did and nothing else. Clover has no delete here (hide only) and cannot remove a count record, so the
reverse of "new item with 30" is: hide the item on the register, remove its link, and put back the website word the change set. The preview
says so plainly. The reverse is a NEW change with its own code and its own `yes` (the till engine and bundle saga carry it out, cap-exempt,
exactly as they carry out any other undo); `finish` is the one step that happens after the till half has read back.

* `reverse(bundle_row, current_item, site_product, links)` -> `Reverse` or `Refusal`.
* `render(reverse, code)` -> the owner-facing preview, ending with the one yes line.
* `finish(reverse, state, till)` -> removes the link only after the till half read back `applied`.

Nothing here builds a DELETE, a price write, a checkout or a network call: the drafts come from `hass.clover.drafts`, the link file from
`hass.clover.links`.
"""
import json
from dataclasses import dataclass, replace

from hass.clover import drafts as d
from hass.clover import links as linkmod
from hass.clover import reports
from hass.clover.mapper import format_quantity

APPLIED = ("done", "partial", "split")   # bundle states that left something applied (the same set bundle.undo accepts)
CHANGED_AGAIN = "The item was changed again; I will not undo over a newer value."   # the wording drafts.build_undo already uses
NOTHING = "There is no applied change here that I can undo. Nothing was changed."


@dataclass(frozen=True)
class Refusal:
    """The reverse cannot be made safely. `reason` is the plain reply to the owner; nothing was prepared and nothing changes."""
    reason: str


@dataclass(frozen=True)
class Reverse:
    label: str                 # the item as the owner knows it
    item_id: "str | None"       # the till item (None for a link-only reverse)
    till: "d.Draft | None"      # the till draft (hide, old count, ...), without site ops: the engine verifies exactly what it wrote
    site_ops: tuple            # website ops that put the stock word back (the existing site path applies them)
    unlink: "dict | None"       # {product_id, clover_id, sku}: the link that finish() removes
    parts: tuple               # every reversed part, in plain words
    hides: bool                # the reverse hides the item (a created item is never deleted)
    count: str                 # the count the item's record keeps ('not counted' when none)
    undo_of: str               # the bundle code this reverses


def _owner_item(current, item_id):
    if current is None or current.id != item_id:
        raise d.DraftRefused("I can't find that item in the till any more, so I can't undo the change.")


def _check_created(entry, current, counted, count_known):
    """A created item must still be exactly as the change left it: showing, with its price, SKU and count. Nothing newer is hidden away."""
    after = entry.get("after") or {}
    same = [current.price_cents == after["price"] if "price" in after and current.price_type != "VARIABLE" else True,
            current.sku == after["sku"] if "sku" in after else True,
            not current.hidden]
    if count_known and counted is not None:
        same.append(current.stock is not None and format_quantity(current.stock) == counted)
    if not all(same):
        raise d.DraftRefused(CHANGED_AGAIN)


def _site_part(word, site_product):
    if word == d.CLEAR:
        return ({"op": "product.clear_availability", "args": {"id": site_product.id}},
                f"Website: takes the stock word off {site_product.name}, as it was before")
    return ({"op": "product.set_availability", "args": {"id": site_product.id, "available": word}},
            f"Website: puts {site_product.name} back to {d.SITE_WORDS[word]}")


def _unlink(row, entry, links):
    link = row["bundle"].get("link")
    if not link or row.get("link_state") != "written":
        return None
    item_id = row.get("clover_id") or (entry or {}).get("result_item_id")
    held = links.get(link["product_id"]) if isinstance(links, dict) else None
    if held is None:
        return None   # already gone: nothing to remove
    if not isinstance(held, dict) or held.get("cloverId") != item_id:
        raise d.DraftRefused(CHANGED_AGAIN)   # the link now joins something else: leave it alone
    return {"product_id": link["product_id"], "clover_id": item_id, "sku": held.get("sku", "")}


def _plan(row, current, site_product, links, config):
    if not isinstance(row, dict) or row.get("state") not in APPLIED or not isinstance(row.get("bundle"), dict):
        raise d.DraftRefused(NOTHING)
    entry = row.get("undo_result")
    asked = row["bundle"].get("till")
    if asked and not entry:
        raise d.DraftRefused("I have no record of what the till change did, so I can't undo it safely. Nothing was changed.")
    unlink = _unlink(row, entry, links)
    till, site_ops, parts, hides, label, item_id, count = None, (), [], False, "the link", None, "not counted"
    if entry:
        item_id = entry["result_item_id"]
        _owner_item(current, item_id)
        label = current.name
        count = "not counted" if current.stock is None else format_quantity(current.stock)
        created = entry["kind"] == "create_item"
        if created:
            counted = (asked or {}).get("after", {}).get("stock")
            _check_created(entry, current, counted, row.get("till") == "applied" and row["state"] != "partial")
        draft = d.build_undo(entry, current, config, site_product=site_product)   # also refuses when modifiedTime / stock moved
        if created:
            word = d._site_restore(entry, site_product)
            parts.append(f"Register: {d._label(current)} goes from showing to hidden")
            if word:
                op, part = _site_part(word, site_product)
                site_ops, parts = (op,), parts + [part]
            hides = True
        else:
            site_ops = draft.site_ops
            parts += [line.strip() for line in draft.lines[1:] if line.strip()]
        till = replace(draft, site_ops=(), before={k: v for k, v in draft.before.items() if k != "site"},
                       after={k: v for k, v in draft.after.items() if k != "site"})
    if unlink:
        parts.append(f"Link: removes the link between website product {unlink['product_id']} and this till item")
    if till is None and not unlink:
        raise d.DraftRefused(NOTHING)
    return Reverse(label, item_id, till, tuple(site_ops), unlink, tuple(parts), hides, count, row["bundle"]["code"])


def reverse(bundle_row, current_item, site_product, links, *, config=None):
    """The exact reverse of one applied bundle (a journal row: `BundleJournal.get(code)`), or a Refusal.
    `current_item` is the till item read right now (None when it cannot be found), `site_product` the website product or None, `links`
    the private link table ({product id: {cloverId, sku}}). A created counted item is hidden (never deleted), its link removed and the
    website word the change set put back; a count change gets its old count back; a link added to an existing item is removed. If the till
    item changed after the change (count, price, SKU, hidden, modifiedTime) it refuses with the "changed again" sentence and prepares nothing."""
    try:
        return _plan(bundle_row, current_item, site_product, links, config)
    except d.DraftRefused as exc:
        return Refusal(str(exc))


def render(reverse, code):
    """The owner-facing preview of the reverse: every part, the honest hide-not-delete words, then the one yes line for its own code."""
    lines = [f"Undo: reverse the last change to {reverse.label} exactly? This does these parts:"]
    lines += [f"  {n}. {part}" for n, part in enumerate(reverse.parts, 1)]
    if reverse.hides:
        lines.append(f"The item is hidden, not deleted: nothing is deleted, and its count record stays (it still says {reverse.count}; the till "
                     "cannot remove a count record). You can show it again.")
    else:
        lines.append("Nothing is deleted.")
    lines.append("This is a new change with its own code and its own yes; the first yes does not cover it.")
    lines.append(f"Reply yes {code} to do this, or no {code} to drop it. Nothing changes until you say yes.")
    return "\n".join(lines)


def finish(reverse, state, till=None):
    """After the reverse ran: remove the link, but ONLY once the till half read back `applied` (`till` is the status the engine returned
    or the bundle row's `till` field). A failed, uncertain or unknown till half (the default) leaves the link, because the item may still be
    showing on the register. `state` is the private state folder. Returns 'unlinked', 'link-kept', 'link-gone' (already absent) or 'no-link'."""
    if reverse.unlink is None:
        return "no-link"
    if reverse.till is not None and till != "applied":
        return "link-kept"
    path = linkmod.table(state)
    try:
        table = json.loads(reports._read_regular(path))
    except FileNotFoundError:
        return "link-gone"
    held = table.get(reverse.unlink["product_id"]) if isinstance(table, dict) else None
    if held is None:
        return "link-gone"
    if not isinstance(held, dict) or held.get("cloverId") != reverse.unlink["clover_id"]:
        return "link-kept"   # it joins something else now: not ours to remove
    linkmod.write(path, {k: v for k, v in table.items() if k != reverse.unlink["product_id"]})
    return "unlinked"
