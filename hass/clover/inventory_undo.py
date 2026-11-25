"""HCI-10: the exact reverse of an applied till inventory change. This module only PLANS and PREVIEWS the reverse; it sends nothing.

`undo <code>` reverses what a bundle did and nothing else. Clover has no delete here (hide only) and cannot remove a count record, so the
reverse of "new item with 30" is: hide the item on the register, remove its link, and revert the website change the bundle made (the
journalled `history.revert`, never a recomputed word). The preview
says so plainly. The reverse is a NEW change with its own code and its own `yes` (the till engine and bundle saga carry it out, cap-exempt,
exactly as they carry out any other undo); `finish` is the one step that happens after the till half has read back.

* `reverse(bundle_row, current_item, site_product, links, site_change=...)` -> `Reverse` or `Refusal`.
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
    site_ops: tuple            # website ops that undo the bundle's website half (its `history.revert`; the existing site path applies them)
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


_MISSING = object()   # a website field that is absent (distinct from an explicit null)
SITE_UNSURE = ("I can't tell whether the website change from that bundle went live, so I can't undo it safely. Nothing was changed. "
               "Check the website, then ask me again.")


SITE_DETAILS = ("I can't read what that website change did, so I can't show you what undoing it would put back. Nothing was changed. "
                "Check the website, then ask me again.")
SITE_UNDONE = "That website change was already undone, so there is nothing on the website to put back. Nothing was changed."
_ABSENT = {"available": "no word"}   # a website field that was not there before the change


def _shown(value, field):
    """One website value in plain, short words: an absent field says what absent means ('no word'), anything else is quoted."""
    if value is _MISSING or value is None:
        return _ABSENT.get(field, "not set")
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "'" + (text if len(text) <= 60 else text[:57] + "...") + "'"


def _site_parts(change_id, change):
    """The website records one applied change wrote, as owner-facing parts: for each record the product (or other record), and each field
    it takes back with the value now on the website and the value it goes back to (the record's own `before`; `no word` when the field
    was not there). Reads only the site's change record, the same one `history.revert` restores from; anything unreadable is refused."""
    if not isinstance(change, dict) or not isinstance(change.get("records"), list) or not change["records"]:
        raise d.DraftRefused(SITE_DETAILS)
    if change.get("state") != "applied":
        raise d.DraftRefused(SITE_DETAILS)
    if change.get("revertedBy"):
        raise d.DraftRefused(SITE_UNDONE)
    first, last = {}, {}   # per record: the value before the change and the value the change finally wrote (as history.revert reads them)
    for record in change["records"]:
        if not (isinstance(record, dict) and isinstance(record.get("collection"), str) and isinstance(record.get("key"), str)
                and "before" in record and "after" in record
                and all(v is None or isinstance(v, dict) for v in (record["before"], record["after"]))):
            raise d.DraftRefused(SITE_DETAILS)
        ref = (record["collection"], record["key"])
        first.setdefault(ref, record["before"])
        last[ref] = record["after"]
    parts = []
    for (collection, key), before in first.items():
        after = last[(collection, key)] or {}
        name = after.get("name") or after.get("title") or (before or {}).get("name") or (before or {}).get("title")
        label = f"{collection} {key}" + (f" ({name})" if isinstance(name, str) and name else "")
        if before is None:   # this change added the record; history.revert hides or cancels it, never deletes it
            parts.append(f"Website: {label} was added by this change; it is taken off the website (hidden or cancelled, not deleted)")
            continue
        fields = sorted(k for k in before.keys() | after.keys() if before.get(k, _MISSING) != after.get(k, _MISSING))
        if fields:
            parts.append(f"Website: {label} goes back as it was: " + "; ".join(
                f"{k} {_shown(after.get(k, _MISSING), k)} -> {_shown(before.get(k, _MISSING), k)}" for k in fields))
    if not parts:
        raise d.DraftRefused(SITE_DETAILS)   # the change left nothing to put back: not a reverse the owner can be shown
    return parts


def _bundle_site(row, went_live, site_change):
    """The website half of the bundle, as the bundle journal really recorded it: its site ops ran under `row['change_id']`, and the exact
    inverse is the existing `history.revert` of that change (the same op `bundle.undo` drafts; the site path refuses it, with no draft, if a
    later edit touched those records). Returns (ops, parts), the parts naming each website record and the value it goes back to, read from
    that change's own record (`site_change(change_id)`); with no way to read it the reverse is refused, since the owner could not see what
    they approve. No site ops, or ops that never ran, mean nothing to put back. When the journal cannot say whether the change landed
    (`went_live(change_id)` is the site's own answer, if given) the reverse is refused, never guessed."""
    if not row["bundle"].get("site_ops"):
        return (), []
    change_id, site = row.get("change_id"), row.get("site")
    if site in ("intent", "not-confirmed"):
        if not callable(went_live) or not change_id:
            raise d.DraftRefused(SITE_UNSURE)
        site = "live" if went_live(change_id) else "never"
    if site != "live":
        return (), []   # pending / confirmed not live: the website never changed
    if not change_id:
        raise d.DraftRefused(SITE_UNSURE)
    if not callable(site_change):
        raise d.DraftRefused(SITE_DETAILS)
    try:
        change = site_change(change_id)
    except Exception:   # noqa: BLE001 - an unreadable record is a refusal, never a guess
        raise d.DraftRefused(SITE_DETAILS) from None
    return (({"op": "history.revert", "args": {"changeId": change_id}},), _site_parts(change_id, change))


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


def _plan(row, current, site_product, links, config, went_live=None, site_change=None):
    if not isinstance(row, dict) or row.get("state") not in APPLIED or not isinstance(row.get("bundle"), dict):
        raise d.DraftRefused(NOTHING)
    entry = row.get("undo_result")
    asked = row["bundle"].get("till")
    if asked and not entry:
        raise d.DraftRefused("I have no record of what the till change did, so I can't undo it safely. Nothing was changed.")
    unlink = _unlink(row, entry, links)
    bundle_ops, bundle_parts = _bundle_site(row, went_live, site_change)   # the website half the journal really recorded
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
            parts.append(f"Register: {d._label(current)} goes from showing to hidden")
            hides = True
        else:
            # a count change journalled with its own website word (chat path) restores that word; a bundle's website half is reverted whole
            site_ops = () if bundle_ops else draft.site_ops
            parts += [line.strip() for line in draft.lines[1:] if line.strip() and not (bundle_ops and line.strip().startswith("Website:"))]
        till = replace(draft, site_ops=(), before={k: v for k, v in draft.before.items() if k != "site"},
                       after={k: v for k, v in draft.after.items() if k != "site"})
    if bundle_ops:
        site_ops, parts = bundle_ops, parts + bundle_parts
    if unlink:
        parts.append(f"Link: removes the link between website product {unlink['product_id']} and this till item")
    if till is None and not unlink and not site_ops:
        raise d.DraftRefused(NOTHING)
    return Reverse(label, item_id, till, tuple(site_ops), unlink, tuple(parts), hides, count, row["bundle"]["code"])


def reverse(bundle_row, current_item, site_product, links, *, config=None, went_live=None, site_change=None):
    """The exact reverse of one applied bundle (a journal row: `BundleJournal.get(code)`), or a Refusal.
    `current_item` is the till item read right now (None when it cannot be found), `site_product` the website product or None, `links`
    the private link table ({product id: {cloverId, sku}}). A created counted item is hidden (never deleted), its link removed and the
    bundle's own website change reverted (`history.revert` of the journalled `change_id`, the same inverse `bundle.undo` drafts); a count
    change gets its old count back; a link added to an existing item is removed. `site_change(change_id)` returns that website change's
    own record (the editor's `show(change_id)['change']`: its records with their `before` and `after`), from which the preview names each
    website record and the value it goes back to; a bundle whose website half landed is refused when that record cannot be read.
    `went_live(change_id)` is the site's answer, used only
    when the journal row says the website half was left uncertain; with no answer that bundle is refused. If the till
    item changed after the change (count, price, SKU, hidden, modifiedTime) it refuses with the "changed again" sentence and prepares nothing."""
    try:
        return _plan(bundle_row, current_item, site_product, links, config, went_live, site_change)
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
