"""HASS-CLOVER-1/2: read-only answers from a snapshot of the till, with the staleness label and the unreachable behaviour.

A Snapshot is the last items-and-stock pull plus when it was taken. Answers are plain text from fixed templates: no model writes or reads them.
Nothing here asks Clover anything; `hass/clover/cli.py sync` fills the private cache and `hass/clover/chat.py` reads it (docs/hass/CLOVER.md).

Staleness (design question 6): a count under 20 minutes old is quoted as is; older gets "as of <time>"; when Clover cannot be reached the
answer says so and quotes the last count labelled as old; a snapshot over 24 hours old is not quoted at all.

`show` (HASS-CLOVER-2) formats an item name or SKU for the reply; the chat passes voice.quote, so a till name ("Eggs, dozen") or a SKU
("AS-PAN-OIL-01") is shown as the till has it and never judged by the voice rules. The default shows the text as is.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from hass.clover.mapper import format_quantity, norm_name, suggest

PACIFIC = ZoneInfo("America/Los_Angeles")
FRESH = timedelta(minutes=20)
TOO_OLD = timedelta(hours=24)
SKEW = timedelta(minutes=5)    # a stamp this far ahead of `now` is ordinary clock skew; further ahead is not quoted
LIST_LIMIT = 15


@dataclass(frozen=True)
class Snapshot:
    items: tuple
    fetched_at: datetime       # timezone-aware


def when(moment, now):
    t = moment.astimezone(PACIFIC)
    clock = f"{t.hour % 12 or 12}:{t.minute:02d} {'am' if t.hour < 12 else 'pm'}"
    return clock if t.date() == now.astimezone(PACIFIC).date() else f"{t:%a} {clock}"


def freshness(snapshot, now, reachable=True):
    """(state, label): state is fresh | stale | unreachable | too-old; label is the sentence to put before or after an answer."""
    # Elapsed time between instants: same-zone aware datetimes would subtract wall clocks and ignore a DST change between them.
    age = now.astimezone(timezone.utc) - snapshot.fetched_at.astimezone(timezone.utc)
    if age < -SKEW:
        # Stamped in the future (clock jump, restored backup, edited cache): nobody can say how old it is, so it is never quoted.
        return "too-old", "I can't tell how old the till count is, so I will not quote it. Check the till, or ask me again in a few minutes."
    if age > TOO_OLD:
        return "too-old", (f"I have not been able to read the till since {when(snapshot.fetched_at, now)}, "
                           "so I will not quote a count that old. Check the till, or ask me again in a few minutes.")
    if not reachable:
        return "unreachable", f"I can't reach the till right now. The last count I have is from {when(snapshot.fetched_at, now)}, so treat it as old."
    if age > FRESH:
        return "stale", f"(till count as of {when(snapshot.fetched_at, now)})"
    return "fresh", ""


def _as_is(text):
    return text


def _count(item):
    return "the till keeps no count" if item.stock is None else f"{format_quantity(item.stock)} in the till"


def _wrap(state, label, body):
    if state == "too-old":
        return label
    if state == "unreachable":
        return f"{label} {body}"
    return f"{body} {label}".strip()


def exact(query, snapshot):
    """The items `query` names exactly (name or SKU); visible ones first, hidden ones only when no visible item matches."""
    hits = [i for i in snapshot.items if norm_name(i.name) == norm_name(query) or (i.sku and i.sku.casefold() == norm_name(query))]
    return [i for i in hits if not i.hidden] or hits


def names_something(query, snapshot):
    """HASS-CLOVER-2: True when `query` names a till item exactly or as a 'did you mean'; the chat only claims such a question."""
    return bool(exact(query, snapshot) or suggest(query, snapshot.items))


SEVERAL_LIMIT = 5


def _several(items, show):
    text = "More than one item is called that: " + "; ".join(f"{show(i.name)} (SKU {show(i.sku) if i.sku else 'none'}): {_count(i)}"
                                                             for i in items[:SEVERAL_LIMIT]) + "."
    # Say so when the list stops short, so a short list is never read as the whole list.
    return text + f" And {len(items) - SEVERAL_LIMIT} more." if len(items) > SEVERAL_LIMIT else text


def _not_exact(query, snapshot, show):
    near = suggest(query, snapshot.items)
    if len(near) == 1:
        return f"I can't find exactly that. The closest is {show(near[0].name)}: {_count(near[0])}."
    if near:
        return "I can't find exactly that. Did you mean " + ", ".join(show(i.name) for i in near) + "?"
    return "I can't find anything like that in the till."


def how_many(query, snapshot, now, reachable=True, show=_as_is):
    """'how many Sunshine olive oil do we have'."""
    state, label = freshness(snapshot, now, reachable)
    if state == "too-old":
        return label
    visible = exact(query, snapshot)
    if len(visible) > 1:
        body = _several(visible, show)
    elif visible:
        i = visible[0]
        body = f"{show(i.name)}: {_count(i)}." + (" It is hidden on the till." if i.hidden else "")
    else:
        body = _not_exact(query, snapshot, show)
    return _wrap(state, label, body)


def _in_stock(i, show, sold_out=False):
    """The yes/no answers the question as asked: "in stock?" is yes at a count above 0, "sold out?" is yes at 0 or below."""
    if i.stock is None:
        return f"The till keeps no count for {show(i.name)}, so I can't tell."
    if i.stock <= 0:
        return f"{'Yes' if sold_out else 'No'}, {show(i.name)} is sold out in the till."
    if sold_out:
        return f"No, {show(i.name)} is not sold out: {format_quantity(i.stock)} in the till."
    return f"Yes, {show(i.name)}: {format_quantity(i.stock)} in the till."


def in_stock(query, snapshot, now, reachable=True, show=_as_is, sold_out=False):
    """HASS-CLOVER-2: 'is Sunshine olive oil in stock'. Yes with the count, no when it is at 0, or says the till keeps no count.

    sold_out=True answers 'is Sunshine olive oil sold out' with the opposite yes/no and the same facts."""
    state, label = freshness(snapshot, now, reachable)
    if state == "too-old":
        return label
    visible = exact(query, snapshot)
    if len(visible) > 1:
        body = _several(visible, show)
    elif visible:
        i = visible[0]
        body = _in_stock(i, show, sold_out) + (" It is hidden on the till." if i.hidden else "")
    else:
        body = _not_exact(query, snapshot, show)
    return _wrap(state, label, body)


def low_stock(snapshot, now, threshold, reachable=True, show=_as_is):
    """'low stock': counted, visible items at or under `threshold`, sold out ones first."""
    state, label = freshness(snapshot, now, reachable)
    if state == "too-old":
        return label
    counted = [i for i in snapshot.items if not i.hidden and i.stock is not None]
    low = sorted((i for i in counted if i.stock <= threshold), key=lambda i: (i.stock, i.name))
    # One combined limit across both groups (sold out first), so "And N more" counts exactly the items not shown.
    out = [i for i in low if i.stock <= 0][:LIST_LIMIT]
    more = [i for i in low if i.stock > 0][:LIST_LIMIT - len(out)]
    parts = []
    if out:
        parts.append("Sold out: " + ", ".join(show(i.name) for i in out) + ".")
    if more:
        parts.append(f"Low ({threshold} or fewer): " + ", ".join(f"{show(i.name)} {format_quantity(i.stock)}" for i in more) + ".")
    omitted = len(low) - len(out) - len(more)
    if omitted:
        parts.append(f"And {omitted} more.")
    untracked = sum(1 for i in snapshot.items if not i.hidden and i.stock is None)
    body = " ".join(parts) or "Nothing is low."
    if untracked:
        body += f" {untracked} item(s) have no count in the till, so I can't tell."
    return _wrap(state, label, body)
