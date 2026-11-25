"""HCI-07: decide the one exact till change for a count sentence such as "30 of the blue mugs". Planning only; nothing is sent.

`plan` takes values that were already read (the parsed sentence, the website products, the private link table, the till items and
categories, the Clover settings) and returns exactly one of:

  Change  the draft a single `yes` would apply, the link to write with it (or None) and the website stock word that goes with the count;
  Ask     a question for Mike, named by a plain `kind`. Nothing is guessed: an unclear sentence, product or till item is a question.

It reads no file, makes no network call and asks no model. The drafts come from the existing builders in `hass.clover.drafts`, so every
count and price check, the stale-check values and the undo journal are the ones the rest of the till code already trusts.

A builder's own plain-words refusal (a bad count, "already shows 30", "received how many", a link whose till item is gone, a unit that does
not fit the item) is not turned into a question: `drafts.DraftRefused` passes through unchanged, and its message is the reply to Mike.

Ask kinds: which-product, price, count-conflict, price-mismatch, not-live, hidden. The G questions Q1-Q3 (reports/roadmaps/G-QUESTIONS-ROADMAP.md)
are open, so each one asks Mike by default. `Policy.count_conflict` is the only switch: `set` or `add` answers Q1; the plan never changes a
price (Q3 "separate") and never invents a till item for a product that is not live on the website (Q2 "wait").
"""
from dataclasses import dataclass, field
from decimal import Decimal

from hass.clover import drafts
from hass.clover.links import holders, reserved
from hass.clover.mapper import MapError, norm_name, parse_selling_price, parse_site_product

MODES = ("count", "set", "add")
KINDS = ("which-product", "price", "count-conflict", "price-mismatch", "not-live", "hidden")


@dataclass(frozen=True)
class Policy:
    """`count_conflict`: what plain "there are 30" means when the till already counts a different number above 0 (Q1).
    Any value other than "set" or "add" asks."""
    count_conflict: str = "ask"


@dataclass(frozen=True)
class Ask:
    """One question for Mike. `names` are product or till item names to offer. The repr carries no price or count."""
    kind: str
    names: tuple = ()


@dataclass(frozen=True)
class Change:
    """The one exact till change. `draft` is the builder's Draft (it holds every price and count, so it stays out of the repr).
    `link` is {"product_id", "sku"} when this change creates or links the till item, else None. `site_word` is the website stock word
    (yes, limited or no) the new count calls for, or None when the product already shows it; for an existing item the same word is
    already in `draft.site_ops`."""
    draft: drafts.Draft = field(repr=False)
    product_id: str
    link: "dict | None" = field(default=None, repr=False)
    site_word: "str | None" = field(default=None, repr=False)

    def __repr__(self):
        return f"Change(kind={self.draft.kind!r}, product_id={self.product_id!r}, linked={self.link is not None})"


# ---------------------------------------------------------------------------------------------------------- the website product
def _forms(name):
    """The one fixed plural fold: the name itself, and the name without a final "es" or "s"."""
    out = {name}
    for tail in ("es", "s"):
        if name.endswith(tail) and len(name) > len(tail):
            out.add(name[:-len(tail)])
    return out


def _hits(query, products):
    exact = [p for p in products if norm_name(p["name"]) == query]
    if exact:
        return exact   # an exact name is never outvoted by a plural fold ("Mug" and "Mugs" can both exist)
    wanted = _forms(query)
    return [p for p in products if _forms(norm_name(p["name"])) & wanted]


def _names(products):
    return tuple(sorted(p["name"] for p in products))


def find_product(query, site_products):
    """The one ACTIVE website product record a phrase names, or an Ask. Whole names only: exact norm_name, else the plural fold.
    Zero or several matches -> Ask("which-product", names); a name only a not-active (hidden or held) product has -> Ask("not-live")."""
    q = norm_name(query)
    active, other = [], []
    for record in site_products:
        try:
            site = parse_site_product(record)
        except MapError:
            continue
        (active if site.status == "active" else other).append(record)
    if not q:
        return Ask("which-product")
    found = _hits(q, active)
    if len(found) == 1:
        return found[0]
    if found:
        return Ask("which-product", _names(found))
    waiting = _hits(q, other)
    return Ask("not-live", _names(waiting)) if waiting else Ask("which-product")


# ---------------------------------------------------------------------------------------------------------- the till item
def _label(item):
    return f"{item.name} (SKU {item.sku})" if item.sku else item.name


def _linked_item(product_id, links, items):
    """The till item this product's own link holds, or None. Resolved against EVERY product's link, in the order mapper.match uses, so an
    item another product's link already holds is never this product's (a second link to it is a broken claim, not a second owner)."""
    item_id = holders(items, links).get(product_id)
    return next((i for i in items if i.id == item_id), None)


def _till_unit(item):
    return item.unit_name.casefold() if item.price_type == "PER_UNIT" and item.unit_name else None


def _check_unit(intent, till_unit, name):
    said = intent.unit.casefold() if isinstance(intent.unit, str) and intent.unit else None
    if said != till_unit:
        raise drafts.DraftRefused(
            f"{name} is counted {'in ' + till_unit if till_unit else 'by the item'}, so I cannot take that count "
            f"{'in ' + said if said else 'with no unit'}. Say it like {'12 ' + till_unit + ' of ' if till_unit else '12 of '}{name}.")


def _site_price(record):
    """(cents, unit) of the website sellingPrice, None when the website has none, or False when it has one Hass cannot read."""
    text = record.get("sellingPrice")
    if text is None or text == "":
        return None
    try:
        return parse_selling_price(text)
    except MapError:
        return False


def _plan_existing(intent, record, site, item, link, config, policy):
    _check_unit(intent, _till_unit(item), item.name)
    price = _site_price(record)
    if price is False:
        return Ask("price", (site.name,))
    if price is not None and price != (item.price_cents, _till_unit(item)):
        return Ask("price-mismatch", (item.name,))   # never a price change here; the price has its own one-yes change (Q3)
    mode = intent.mode
    if mode == "count":
        have, want = item.stock, drafts._qty(intent.quantity, item, config)
        if have is not None and have > 0 and have != want:
            if policy.count_conflict not in ("set", "add"):
                return Ask("count-conflict", (item.name,))
            mode = policy.count_conflict
    if mode == "add":
        draft = drafts.build_received(item, intent.quantity, config, site_product=site)
    else:
        draft = drafts.build_set_stock(item, intent.quantity, config, site_product=site)
    return Change(draft, site.id, link, drafts._site_op(site, Decimal(draft.after["stock"]), config))


def _plan_new(intent, record, site, items, categories, config):
    price = _site_price(record)
    if not price:
        return Ask("price", (site.name,))
    _check_unit(intent, price[1], site.name)   # the website's own price basis: "each" or "per lb"
    category = record.get("category") if isinstance(record.get("category"), str) else None
    draft = drafts.build_create_counted(site.name, record["sellingPrice"], category, intent.quantity, items, config, categories=categories)
    link = {"product_id": site.id, "sku": draft.after["sku"]}
    return Change(draft, site.id, link, drafts._site_op(site, Decimal(draft.after["stock"]), config))


# ---------------------------------------------------------------------------------------------------------- the plan
def plan(intent, site_products, links, items, categories, config, *, policy=Policy()):
    """`intent` has (mode, quantity, unit, query) like qty_words.CountIntent. `site_products` are hass/content product records (dicts),
    `links` the private {product_id: {"cloverId", "sku"}} table, `items` the till's CloverItem list, `categories` [(clover_id, name)],
    `config` the CloverConfig. Returns one Change or one Ask; raises drafts.DraftRefused with a plain reply when a builder refuses."""
    if intent.mode not in MODES:
        raise ValueError("mode")
    record = find_product(intent.query, site_products)
    if isinstance(record, Ask):
        return record
    site = parse_site_product(record)
    link = links.get(site.id)
    if isinstance(link, dict) and link:
        item = _linked_item(site.id, links, items)
        if item is None:
            raise drafts.DraftRefused(f"The link for {site.name} points at an item the till no longer has, or one that another product's link "
                                      "already holds, so I do not know which one to count. Nothing was changed. Fix the link first.")
        return _plan_existing(intent, record, site, item, None, config, policy)
    taken = reserved(items, links)   # till items another product's link already holds are never offered or linked again
    same = sorted((i for i in items if norm_name(i.name) == norm_name(site.name) and i.id not in taken), key=lambda i: (_label(i), i.id))
    if len(same) > 1:
        return Ask("which-product", tuple(_label(i) for i in same))
    if same:
        item = same[0]
        if item.hidden:
            return Ask("hidden", (item.name,))
        return _plan_existing(intent, record, site, item, {"product_id": site.id, "sku": item.sku}, config, policy)
    return _plan_new(intent, record, site, items, categories, config)
