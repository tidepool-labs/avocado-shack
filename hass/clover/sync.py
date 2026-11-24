"""HASS-CLOVER-2: one read-only pull of the till into the private cache. The caller (`cli.py sync`) owns the token and the client.

The pull asks ONLY: GET /items (expand itemStock,categories,tags; paged) and GET /item_stocks (paged): the client's allow-list refuses
every other path before a request exists, so no sales, orders, customers, payments or employees endpoint can be called. Each item
keeps, by whitelist: id, name, SKU, barcode code, price in cents, price type and unit, category ids and names, hidden, available, the
stock count (from /item_stocks where the merchant counts the item; else from the expanded itemStock; else none) and modified times.
Nothing else from a response is kept (no cost, no tax, no employee or order reference).
"""
import json
import re
from decimal import Decimal, InvalidOperation

from hass.clover import mapper

MAX_STOCK_DIGITS = 12
MAX_STOCK_SCALE = 12   # most decimal places kept; bounds the fixed-point text (<= 12 + 1 + 12 chars) before it is built


def _ids(raw, key):
    block = raw.get(key)
    els = block.get("elements") if isinstance(block, dict) else None
    if not isinstance(els, list):
        return ()
    return tuple(sorted({e["id"] for e in els if isinstance(e, dict) and isinstance(e.get("id"), str)
                         and re.fullmatch(r"[A-Za-z0-9]{1,32}", e["id"])}))


def _stock_text(value):
    """A Clover quantity as exact text ('12', '1.5'), or None for anything that is not a finite, sane number."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        return None
    try:
        q = Decimal(str(value))
        if not q.is_finite() or abs(q) >= Decimal(10) ** MAX_STOCK_DIGITS:
            return None
        if q.as_tuple().exponent < -MAX_STOCK_SCALE:   # '1E-9999999' would otherwise expand to millions of characters
            return None
        text = format(q, "f")   # exact digits, never an exponent. NOT mapper.format_quantity: it rounds to 3 places (0.0004 -> '0')
        return text.rstrip("0").rstrip(".") if "." in text else text
    except (InvalidOperation, ArithmeticError):
        return None


def stock_by_item(stock_elements):
    """{item id: (quantity text or None, modifiedTime or None)} from GET /item_stocks elements."""
    out = {}
    for el in stock_elements:
        item = el.get("item") if isinstance(el, dict) else None
        iid = item.get("id") if isinstance(item, dict) else None
        if isinstance(iid, str) and re.fullmatch(r"[A-Za-z0-9]{1,32}", iid):
            mod = el.get("modifiedTime")
            out[iid] = (_stock_text(el.get("quantity")), mod if type(mod) is int and mod >= 0 else None)
    return out


def rows(item_elements, stock_elements):
    """(cache rows, skipped): one row per usable item; a malformed element is counted, never fatal, never echoed."""
    stocks = stock_by_item(stock_elements)
    out, skipped = [], 0
    for raw in item_elements:
        try:
            item = mapper.parse_item(raw)
        except mapper.MapError:
            skipped += 1
            continue
        if item.id in stocks:
            stock, stock_modified = stocks[item.id]
        else:
            stock = None if item.stock is None else _stock_text(item.stock)
            stock_modified = item.stock_modified
        out.append({"id": item.id, "name": item.name, "sku": item.sku, "code": item.code, "price_cents": item.price_cents,
                    "price_type": item.price_type, "unit_name": item.unit_name, "category_ids": json.dumps(_ids(raw, "categories")),
                    "categories": json.dumps(list(item.categories)), "hidden": int(item.hidden), "available": int(item.available),
                    "stock": stock, "stock_modified": stock_modified, "modified_time": item.modified_time})
    return out, skipped


def pull(client):
    """Ask the till for every item and every stock record. Raises the client's CloverError on any failure (nothing is half-written)."""
    items = client.list_items()
    stocks = client.list_stocks()
    return rows(items, stocks)
