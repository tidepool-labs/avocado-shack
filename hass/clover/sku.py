"""HASS-CLOVER-1: the SKU scheme. Deterministic, readable, unique against Clover, and stable once issued.

Form: `AS-<CAT>-<NAME>-<NN>`, for example `AS-PAN-SUNSHINE-OLIVE-OIL-01`.
  AS     Avocado Shack: marks a SKU Hass made, so Hass never touches one a person typed.
  CAT    three letters from the site category word (pantry -> PAN); `GEN` when the category is not one of the site's nine.
  NAME   up to 18 characters of the name: accents dropped, capitals, words joined with `-`, small joining words (the, a, of ...) left out,
         cut at a word boundary.
  NN     01 to 99: the first number not already used by any SKU or barcode in the till.
Never longer than 28 characters. The same name, category and till contents always give the same SKU. A SKU is issued once and never
re-made: renaming an item or changing its category leaves its SKU alone. Before a create is sent the caller re-checks the one SKU
against the live till (`CloverClient.find_by_sku`); a clash there means a new draft with the next number, never a silent overwrite.
"""
import re
import unicodedata

from hass.clover.mapper import CATEGORIES, MapError, norm_name

GENERAL = "GEN"
CATEGORY_CODES = dict(zip(CATEGORIES, ("FRU", "VEG", "DAI", "EGG", "MEA", "PAN", "DRK", "BRD", "FLW"))) | {"general": GENERAL}
PREFIX = "AS"
SLUG_MAX = 18
SKU_RE = re.compile(r"AS-[A-Z]{3}-[A-Z0-9]+(?:-[A-Z0-9]+)*-(?:0[1-9]|[1-9][0-9])")
SKU_MAX = 28
SMALL_WORDS = frozenset({"THE", "A", "AN", "OF", "AND", "WITH", "FOR", "IN", "ON"})


class DuplicateItem(MapError):
    """The till already has an item with exactly this name. `item` is it; no SKU is made."""

    def __init__(self, item):
        super().__init__("that item is already in the till")
        self.item = item


class SkuExhausted(MapError):
    pass


def slug(name, max_len=SLUG_MAX):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").upper().replace("'", "")  # Linn's -> LINNS
    words = re.sub(r"[^A-Z0-9]+", " ", ascii_name).split()
    kept = [w for w in words if w not in SMALL_WORDS] or words
    if not kept:
        raise MapError("I need letters or numbers in the name to make a SKU.")
    out = ""
    for w in kept:
        nxt = f"{out}-{w}" if out else w
        if len(nxt) > max_len:
            return out or w[:max_len]
        out = nxt
    return out


def base(name, category):
    return f"{PREFIX}-{CATEGORY_CODES.get(category, GENERAL)}-{slug(name)}"


def is_hass_sku(text):
    return isinstance(text, str) and len(text) <= SKU_MAX and SKU_RE.fullmatch(text) is not None


def used_values(items):
    """Every SKU and barcode in the till, case-folded. Hidden items count: their SKUs are still taken."""
    return {v.casefold() for i in items for v in (i.sku, i.code) if v}


def generate_sku(name, category, items):
    """The SKU for a new item `name` in `category`, given every till item. Raises DuplicateItem when the till already has the name."""
    key = norm_name(name)
    items = sorted(items, key=lambda i: i.id)  # one pass: an iterator must still reserve every SKU and barcode below
    twin = next((i for i in items if norm_name(i.name) == key and not i.hidden), None)
    if twin is not None:
        raise DuplicateItem(twin)
    stem, taken = base(name, category), used_values(items)
    for n in range(1, 100):
        sku = f"{stem}-{n:02d}"
        if sku.casefold() not in taken:
            return sku
    raise SkuExhausted("All 99 numbers for that name are used. Give the item a more specific name.")
