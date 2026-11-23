"""HASS-CLOVER-1: the Clover item <-> Hass site product mapper, money in cents, and exact matching.

Pure functions, no I/O. Clover is the source of truth for price and stock; the site never shows either. A Clover item is read through a
whitelist (`parse_item`): fields not named here (cost, tax rates, modifiers, employee or customer data) are dropped on the way in.

Money is integer cents everywhere; a float never touches a price. Stock is a Decimal (Clover stock may be fractional for weighed items).

Matching (design question 2): a stored link first, then the SKU recorded in the link, then the exact name (letter case, spacing and
curly apostrophes ignored; nothing else), and only when exactly one item answers on both sides. Writes never use anything looser;
`suggest` is the looser read-only helper behind "Did you mean ...?".
"""
import re
import unicodedata
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from hass.content_model import SELLING_PRICE_RE

CATEGORIES = ("fruit", "vegetables", "dairy", "eggs", "meat", "pantry", "drinks", "bread", "flowers", "general")  # hass.content_model.CATEGORIES
AVAILABILITY = ("yes", "limited", "no")                                                                # hass.content_model.AVAILABILITY
PRICE_TYPES = ("FIXED", "VARIABLE", "PER_UNIT")
MAX_PRICE_CENTS = 100_000          # $1,000.00: a typo guard (a misread number), changed in config, not a business rule
MAX_NAME = 100


class MapError(ValueError):
    """Bad input to the mapper. The message is plain words for the owner and never carries foreign text."""


# ---------------------------------------------------------------------------------------------------------- money
_MONEY = re.compile(r"\$?\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?")


def cents_from_text(text, max_cents=MAX_PRICE_CENTS):
    """'12.50', '$12.5', '12', '1,234.50' -> cents. More than two decimals, a sign, zero or a value above `max_cents` is refused."""
    m = _MONEY.fullmatch(text.strip()) if isinstance(text, str) else None
    if not m:
        raise MapError("I could not read that as a price. Say it like 12.50.")
    cents = int(m.group(1).replace(",", "")) * 100 + int((m.group(2) or "0").ljust(2, "0"))
    if cents <= 0:
        raise MapError("A price has to be more than $0.00.")
    if cents > max_cents:
        raise MapError(f"{format_money(cents)} looks too high for one item. Check the number and send it again.")
    return cents


def format_money(cents):
    if type(cents) is not int or cents < 0:
        raise MapError("not a price in cents")
    return f"${cents // 100:,}.{cents % 100:02d}"


def parse_selling_price(text):
    """Website sellingPrice -> (integer cents, Clover unit name or None)."""
    if not isinstance(text, str) or SELLING_PRICE_RE.fullmatch(text) is None:
        raise MapError("I could not read that as a price. Use a price like 12.50 each or 8.00 per lb.")
    amount = text.split(" ", 1)[0]
    return int(amount.replace(".", "")), "lb" if text.endswith(" per lb") else None


def pct_change(old_cents, new_cents):
    """Percentage change as a Decimal rounded half-up to one decimal place, by integer arithmetic (no floats)."""
    if type(old_cents) is not int or old_cents <= 0:
        raise MapError("there is no earlier price to compare with")
    return (Decimal(new_cents - old_cents) * 100 / Decimal(old_cents)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def format_quantity(q):
    """12, 12.5 (never 12.0, never an exponent)."""
    return format(Decimal(q).quantize(Decimal("0.001")).normalize(), "f")


# ---------------------------------------------------------------------------------------------------------- names
def norm_name(text):
    """The comparison form of a name: NFKC, curly quotes straightened, case folded, spaces collapsed. Accents stay significant."""
    t = unicodedata.normalize("NFKC", text or "").replace("\u2019", "'").replace("\u2018", "'").replace("\u02bc", "'")
    return " ".join(t.casefold().split())


def clean_name(text):
    """A name Hass may send to Clover: 1 to MAX_NAME characters, one line (line breaks and tabs become one space), no markup, no invisible characters."""
    t = " ".join((text or "").split()) if isinstance(text, str) else ""
    if not t or len(t) > MAX_NAME:
        raise MapError(f"An item name has to be 1 to {MAX_NAME} characters.")
    if re.search(r"[<>{}\\]", t) or any(unicodedata.category(c).startswith(("C", "Z")) and c != " " for c in t):
        raise MapError("An item name cannot contain markup or hidden characters.")
    return t


# ---------------------------------------------------------------------------------------------------------- items
@dataclass(frozen=True)
class CloverItem:
    id: str
    name: str
    sku: str                    # "" when none
    code: str                   # barcode (UPC/EAN); Hass reads it, never writes it
    price_cents: "int | None"   # None for a VARIABLE-price item
    price_type: str
    unit_name: str              # "" unless PER_UNIT
    categories: tuple           # names
    tags: tuple                 # names
    stock: "Decimal | None"     # None = Clover keeps no count for this item
    stock_modified: "int | None"
    hidden: bool
    available: bool
    modified_time: int          # ms since the epoch


def _text(raw, key, limit=200):
    v = raw.get(key)
    return v.strip()[:limit] if isinstance(v, str) else ""


def _names(raw, key):
    block = raw.get(key)
    els = block.get("elements") if isinstance(block, dict) else None
    return tuple(sorted({_text(e, "name", 100) for e in els if isinstance(e, dict) and _text(e, "name", 100)})) if isinstance(els, list) else ()


def _int(raw, key):
    v = raw.get(key)
    return v if type(v) is int and v >= 0 else None


def _decimal(v):
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return None
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def parse_item(raw):
    """A Clover item object -> CloverItem, by whitelist. Raises MapError when it has no usable id or name."""
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9]{1,32}", raw["id"]) or not _text(raw, "name"):
        raise MapError("an item from the till has no id or name")
    price_type = raw.get("priceType")
    if price_type not in PRICE_TYPES:
        price_type = "FIXED"
    stock_obj = raw.get("itemStock") if isinstance(raw.get("itemStock"), dict) else None
    return CloverItem(
        id=raw["id"], name=_text(raw, "name"), sku=_text(raw, "sku", 64), code=_text(raw, "code", 64),
        price_cents=None if price_type == "VARIABLE" else _int(raw, "price"), price_type=price_type,
        unit_name=_text(raw, "unitName", 30) if price_type == "PER_UNIT" else "",
        categories=_names(raw, "categories"), tags=_names(raw, "tags"),
        stock=_decimal(stock_obj.get("quantity")) if stock_obj else None,
        stock_modified=_int(stock_obj, "modifiedTime") if stock_obj else None,
        hidden=raw.get("hidden") is True, available=raw.get("available") is not False,
        modified_time=_int(raw, "modifiedTime") or 0)


def parse_items(elements):
    """(items, skipped): skipped counts malformed elements; one bad row never hides the rest."""
    items, skipped = [], 0
    for raw in elements:
        try:
            items.append(parse_item(raw))
        except MapError:
            skipped += 1
    return items, skipped


# ---------------------------------------------------------------------------------------------------------- site side
@dataclass(frozen=True)
class SiteProduct:
    id: str
    name: str
    brand: str
    producer_key: "str | None"
    category: str
    description: str
    availability: "str | None"   # yes | limited | no | None (no word on the card)
    status: str                  # active | hidden | held


def parse_site_product(record):
    """A hass/content product record -> SiteProduct. The record has no price, SKU or count, by the content model's design."""
    if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not isinstance(record.get("name"), str):
        raise MapError("not a site product")
    word = record.get("available")
    return SiteProduct(record["id"], record["name"], str(record.get("brand") or ""), record.get("producerKey"),
                       str(record.get("category") or ""), str(record.get("description") or ""),
                       word if word in AVAILABILITY else None, str(record.get("status") or "active"))


def availability_hint(item, low_threshold):
    """The site word the till's count suggests, or None. A hint only: the site word changes only through an approved draft."""
    if item.hidden:
        return None
    if not item.available:
        return "no"
    if item.stock is None:
        return None
    return "no" if item.stock <= 0 else "limited" if item.stock <= low_threshold else "yes"


def clover_category(site_category, category_map):
    """Hass category word -> the Clover category name in `category_map` ({'pantry': 'Pantry'}), or None when not mapped."""
    return category_map.get(site_category) if site_category in CATEGORIES else None


def site_category(item, category_map):
    """The Hass category word for a Clover item (first mapped Clover category wins, in name order), or None."""
    reverse = {norm_name(v): k for k, v in category_map.items()}
    return next((reverse[norm_name(c)] for c in item.categories if norm_name(c) in reverse), None)


def create_payload(name, price_cents, sku):
    """The body of POST /items for a new item. Cents are integers; FIXED price; tax and everything else are the till's defaults."""
    if type(price_cents) is not int or price_cents <= 0:
        raise MapError("not a price in cents")
    return {"name": clean_name(name), "price": price_cents, "priceType": "FIXED", "sku": sku, "hidden": False}


# ---------------------------------------------------------------------------------------------------------- matching
@dataclass(frozen=True)
class Pair:
    product_id: str
    item_id: str
    how: str          # link | sku | name


@dataclass(frozen=True)
class Matches:
    pairs: tuple
    ambiguous: tuple      # (product_id, (item_id, ...)) several till items share the exact name
    broken_links: tuple   # product ids whose stored link points at an item that no longer exists
    site_only: tuple      # product ids with no till item
    clover_only: tuple    # item ids with no site product


def match(products, items, links=None):
    """Pair site products with till items. `links` is the private table {product_id: {"cloverId": id, "sku": sku}}.
    Order: every stored link and its SKU first (all products), then exact name. A name pairs only when one product and one item hold it."""
    links = links or {}
    by_id, by_sku = {i.id: i for i in items}, {}
    for i in items:
        if i.sku:
            by_sku.setdefault(i.sku.casefold(), []).append(i)
    names = {}
    for i in items:
        names.setdefault(norm_name(i.name), []).append(i)
    product_names = {}
    for p in products:
        product_names.setdefault(norm_name(p.name), []).append(p)
    pairs, ambiguous, broken, claimed = [], [], [], set()
    ordered = sorted(products, key=lambda x: x.id)
    # Pass 1: every stored link (then its SKU) is resolved before any name is looked at, so a name match can never take an item
    # that another product's explicit link points at, whatever the product ids sort like.
    for p in ordered:
        link = links.get(p.id) or {}
        if not link:
            continue
        if link.get("cloverId") in by_id and link["cloverId"] not in claimed:
            pairs.append(Pair(p.id, link["cloverId"], "link")); claimed.add(link["cloverId"])
            continue
        same = by_sku.get(str(link.get("sku", "")).casefold(), [])
        if len(same) == 1 and same[0].id not in claimed:
            pairs.append(Pair(p.id, same[0].id, "sku")); claimed.add(same[0].id)
            continue
        broken.append(p.id)
    # Pass 2: exact names, only for products with no stored link, among the items no link claimed.
    for p in ordered:
        if links.get(p.id):
            continue
        hits = [i for i in names.get(norm_name(p.name), []) if i.id not in claimed]
        if len(hits) == 1 and len(product_names[norm_name(p.name)]) == 1:
            pairs.append(Pair(p.id, hits[0].id, "name")); claimed.add(hits[0].id)
        elif hits:
            ambiguous.append((p.id, tuple(sorted(i.id for i in hits))))
    paired = {x.product_id for x in pairs}
    skip = paired | {pid for pid, _ in ambiguous} | set(broken)
    return Matches(tuple(pairs), tuple(ambiguous), tuple(broken), tuple(sorted(p.id for p in products if p.id not in skip)),
                   tuple(sorted(i.id for i in items if i.id not in claimed)))


class NotExact(MapError):
    """A write could not name exactly one till item. `candidates` are items to offer by SKU; nothing is guessed."""

    def __init__(self, reply, candidates=()):
        super().__init__(reply)
        self.candidates = tuple(candidates)


def resolve_exact(query, items):
    """The one till item an owner phrase names, for a WRITE: an exact SKU (any visibility), else an exact name among visible items.
    Raises NotExact otherwise, listing at most five items by SKU."""
    q = norm_name(query)
    by_sku = [i for i in items if i.sku and i.sku.casefold() == q]
    if len(by_sku) == 1:
        return by_sku[0]
    hits = by_sku or [i for i in items if norm_name(i.name) == q and not i.hidden]
    if len(hits) == 1:
        return hits[0]
    if hits:
        raise NotExact("More than one item in the till is called that. Which one? Send its SKU: "
                       + ", ".join(i.sku or i.id for i in hits[:5]), hits[:5])
    raise NotExact("I can't find an item with exactly that name in the till. I only change an exact match.",
                   suggest(query, items))


def _forms(word):
    """The word and its plausible singular/plural forms (suggestions only; never used for exact matching)."""
    forms = {word}
    if len(word) > 3 and word.endswith("ies"):
        forms.add(word[:-3] + "y")
    if len(word) > 3 and word.endswith("es"):
        forms.add(word[:-2])
    if len(word) > 2 and word.endswith("s"):
        forms.add(word[:-1])
    if word.endswith("y"):
        forms.add(word[:-1] + "ies")
    forms.update((word + "s", word + "es"))
    return forms


def suggest(query, items, limit=5):
    """Read-only 'Did you mean' help: visible items whose name holds every word of the query, in its singular or plural form.
    Never used to pick a write target."""
    words = [_forms(w) for w in norm_name(query).split()]
    if not words or limit <= 0:
        return ()
    return tuple(sorted((i for i in items if not i.hidden and all(any(f in norm_name(i.name) for f in fs) for fs in words)),
                        key=lambda i: i.name)[:limit])
