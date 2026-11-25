"""HCI-08: the one preview message that names the exact till change, and the plain questions that come before it.

Pure rendering: a till `Draft` (from `drafts.build_create_counted` or `build_set_stock` / `build_received`), the website product it
matches, the link and the approval code go in; text comes out. Nothing here reads a file, the clock, the till or the network, and it
builds no request, so it cannot change anything. Prices and counts are finance-local: they are only ever taken from the draft.

`render` shows every value the one yes will write, in a fixed order: a headline, the till field lines (item, SKU, price, category, count
before and after, register visibility), the website line, the link line, then one last line that names the code. Only whitelisted field
lines of the draft are copied, so a cost, a tax value or a barcode can never reach Mike. The text is fail-closed: when it would show a
barcode-like or token-like string, or the word yes anywhere before the last line (an item literally named "Yes mug"), it raises
ValueError instead of sending a preview it cannot stand behind. The chat route (HCI-13) decides what Mike hears then.
Warnings on a draft (a hidden item, a first count) are not repeated: the planner asks first through `render_ask`.

`render_ask` is the same for the questions (`which-product`, `price`, `count-conflict`, `price-mismatch`, `not-live`, `hidden`): one
plain question, no code, no yes line. The kinds are plain strings on purpose; this module does not import the planner.

Names are Mike's own words and are wrapped with `voice.quote`; SKUs, the arrow in `before -> after` and the code are wrapped by
`voice.till`, as the till replies already do. The marks are removed with `voice.plain` when the message is sent.
"""
import re

from hass import voice
from hass.clover.drafts import SITE_WORDS, Draft
from hass.clover.mapper import MapError, format_money, norm_name, parse_selling_price

MAX_LINES = 12
MAX_LINE = 160
CODE = re.compile(r"[0-9a-f]{8}")   # the conversation layer's code shape (hass.clover.chat CODED)
LAST_LINE = "Reply yes {code} to do this, or no {code} to drop it. Nothing changes until you say yes."
_FIELD = re.compile(r"^\s*(Item|SKU|Price|Category|Count|Received|On the register):[ \t]*(.*)$")   # the only draft lines that are copied
_ORDER = ("Item", "SKU", "Price", "Category", "Count", "Received", "On the register")
_HEAD_SKU = re.compile(r"\((?:SKU (.+?)|no SKU yet)\)\??$")
_NUMBER_RUN = re.compile(r"\d{8,}")
_TOKEN_RUN = re.compile(r"[A-Za-z0-9_+/=-]{32,}|\bbearer\b", re.I)
_YES = re.compile(r"\byes\b", re.I)


def _one_line(text):
    return " ".join(str(text).split())


def _named(name):
    """A name inside plain double quotes on the website and link lines; the voice marks keep it from being judged."""
    return '"' + voice.quote(name) + '"'


def _site(record):
    """(name, selling price text or None, stock word or None) of a website product: a content record (dict) or a mapper.SiteProduct."""
    if record is None:
        return None
    if isinstance(record, dict):
        return _one_line(record.get("name") or ""), record.get("sellingPrice"), record.get("available")
    return _one_line(getattr(record, "name", "")), None, getattr(record, "availability", None)


def _price_words(after):
    cents, unit = after["price"], after.get("unitName")
    return f"{format_money(cents)} {'per ' + unit if unit else 'each'}"


def _website(draft, site, name):
    """The website line: the match (create) or the stock word change (count)."""
    q = _named(name)
    if draft.kind == "set_stock":
        for op in draft.site_ops:
            if op["op"] == "product.set_availability":
                return f"Website: marks {q} as {SITE_WORDS[op['args']['available']]}"
            if op["op"] == "product.clear_availability":
                return f"Website: takes the stock word off {q}"
        if site is None:
            return "Website: no matching product, so nothing changes there"
        return f"Website: no change to {q}"
    if site is None:
        return "Website: no matching product, so nothing changes there"
    shown = _named(site[0])
    if norm_name(site[0]) != norm_name(name):
        return f"Website: {shown} is a different name"
    wanted = _price_words(draft.after)
    try:
        cents, unit = parse_selling_price(site[1])
    except MapError:
        return f"Website: {shown} is there, but I cannot read its price"
    if (cents, unit) != (draft.after["price"], draft.after.get("unitName")):
        return f"Website: {shown} is there, but its price is not {wanted}"
    return f"Website: matches {q} at {wanted}"


def _link(link, sku, name):
    """The link line. `link` is None (no link) or a mapping with the SKU it ties to; `new` True means the change makes that link."""
    q = _named(name)
    if not link:
        return f"Link: {q} on the website is not tied to a till item"
    tied = str(link.get("sku") or "").strip()
    if not tied:
        return f"Link: {q} on the website is not tied to a till item"
    if sku and tied != sku:
        return f"Link: {q} on the website is tied to SKU {tied}, not SKU {sku}"
    return f"Link: {q} on the website {'will be' if link.get('new') else 'is'} tied to SKU {tied}"


def _fields(draft, name):
    """(headline, field lines, SKU). Only whitelisted field lines of the draft are copied."""
    q = voice.quote(name)
    found = {}
    for line in draft.lines[1:]:
        if m := _FIELD.match(line):
            found.setdefault(m[1], m[2].strip())
    if draft.kind == "create_item":
        stock = draft.after.get("stock")
        if stock is None:
            raise ValueError("this draft has no first count to preview")
        sku = draft.after["sku"]
        head = f"Add {q} to the till with {stock} in stock?"
        found["Count"] = f"not in the till yet -> {stock}"
    else:
        m = _HEAD_SKU.search(draft.lines[0])
        sku = m[1] if m and m[1] else ""
        head = f"Set the till count of {q}?"
        found["SKU"] = sku or "none yet"
    found["Item"] = q
    if found.get("Category", "none") != "none":
        found["Category"] = voice.quote(found["Category"])
    lines = [f"  {key}: {found[key]}" for key in _ORDER if key in found]
    return head, lines, sku


def render(till_draft, site_record, link, code) -> str:
    """The preview text for one till change: headline, till fields, website line, link line, and one last line that names the code."""
    if not isinstance(till_draft, Draft) or till_draft.kind not in ("create_item", "set_stock"):
        raise ValueError("only a counted create or a count change has a till preview")
    if not isinstance(code, str) or not CODE.fullmatch(code):
        raise ValueError("the code must be 8 characters of 0-9 a-f")
    name = _one_line(till_draft.label)
    head, fields, sku = _fields(till_draft, name)
    site = _site(site_record)
    body = [head, *fields, _website(till_draft, site, name), _link(link, sku, name)]
    shown = [voice.plain(line) for line in body]
    if any(_YES.search(line) for line in shown):
        raise ValueError("a name says yes, which would read as an answer")
    if any(_TOKEN_RUN.search(line) or _NUMBER_RUN.search(line) for line in shown if not line.lstrip().startswith(("SKU:", "Link:"))):
        raise ValueError("a line looks like a token or a barcode")
    text = voice.till("\n".join([*body, LAST_LINE.format(code=code)]))
    lines = voice.plain(text).split("\n")
    if len(lines) > MAX_LINES or any(len(line) > MAX_LINE for line in lines):
        raise ValueError("the preview would be too long to read")
    return text


# -- the questions ------------------------------------------------------------------------------------------------------

def _list(names):
    quoted = [voice.quote(_one_line(n)) for n in names]
    return quoted[0] if len(quoted) == 1 else ", ".join(quoted[:-1]) + " or " + quoted[-1]


def render_ask(kind, names=()) -> str:
    """One plain question for an Ask kind. No code, no yes line: a question needs no yes."""
    names = tuple(n for n in (names or ()) if _one_line(n))
    it, lead = (_list(names[:1]), _list(names[:1])) if names else ("that one", "That one")
    asks = {
        "which-product": f"Which one do you mean: {_list(names)}?" if len(names) > 1 else "Which product do you mean?",
        "price": f"What price should {it} be, like 14.00 each or 8.00 per lb?",
        "count-conflict": f"The till already counts {it}. Should I set the count to your number, or add it to what is there?",
        "price-mismatch": f"The website and the till show different prices for {it}. Which price is right?",
        "not-live": f"{lead} is not showing on the website yet. Should I set up the till count without the website?",
        "hidden": f"{lead} is hidden right now. Do you want me to bring it back first?",
    }
    if kind not in asks:
        raise ValueError("unknown question kind")
    text = asks[kind]
    if len(voice.plain(text)) > MAX_LINE:
        raise ValueError("the question would be too long to read")
    return text
