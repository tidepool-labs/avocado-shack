#!/usr/bin/env python3
"""Check NPP's posted item links against the checked-in website sources offline."""

import argparse
import json
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import npp, publish_live
from hass.npp import reply

PRODUCTS = ROOT / "hass/content/products.json"
SHOP = ROOT / "storefront-mockup/shop.js"
PRODUCTS_CAP = 2_000_000
SHOP_CAP = 1_000_000
GOLDEN_PREFIX = "hass-gallery-style/golden/"
GOLDEN_STEM = re.compile(r"photo-product-[0-9]{1,6}")
SHOP_LINK = 'href="?item=${esc(encodeURIComponent(p.id))}#market"'


class InputError(Exception):
    """Carries only a fixed diagnostic, never input content or a path."""


def read_input(path, name, cap):
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise InputError(f"input-unsafe {name}")
        if info.st_size > cap:
            raise InputError(f"input-too-large {name}")
        with path.open("rb") as source:
            data = source.read(cap + 1)
        if len(data) > cap:
            raise InputError(f"input-too-large {name}")
        return data.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise InputError(f"input-unreadable {name}") from None


def reject_constant(_value):
    raise ValueError("not a JSON constant")


def read_products():
    text = read_input(PRODUCTS, "products", PRODUCTS_CAP)
    try:
        document = json.loads(text, parse_constant=reject_constant)
    except (ValueError, RecursionError):
        raise InputError("input-unreadable products") from None
    records = document.get("products") if isinstance(document, dict) else None
    if not isinstance(records, list) or any(
        not isinstance(row, dict)
        or not all(isinstance(row.get(key), str) for key in ("id", "name", "status"))
        for row in records
    ):
        raise InputError("input-unreadable products")
    return records


def item_link(product_id):
    return f"{publish_live.URL}/?item={product_id}#market"


def posted_matches(replies, product_id):
    try:
        return item_link(product_id) in reply.posted(replies, product_id, reply.SITE)
    except (ValueError, LookupError, TypeError, AttributeError):
        # A refused ID or an unrenderable template cannot produce a matching link.
        return False


def golden_findings(files, names):
    for name in names:
        stem = name[len(GOLDEN_PREFIX):-len(".json")]
        if not GOLDEN_STEM.fullmatch(stem):
            yield "stem-invalid"
            continue
        try:
            document = json.loads(files[name], parse_constant=reject_constant)
        except (ValueError, TypeError, RecursionError):
            yield "assets-unreadable"
            continue
        card = document.get("card") if isinstance(document, dict) else None
        if not isinstance(card, dict) or card.get("link_to_this") != item_link(stem):
            yield f"golden-link {stem}"


def findings():
    try:
        records = read_products()
        shop = read_input(SHOP, "shop", SHOP_CAP)
    except InputError as error:
        yield str(error)
        return

    try:
        _, files, replies = npp.assets()
    except Exception:
        yield "assets-unreadable"
        return

    active = [row["id"] for row in records if row["status"] == "active"]
    names = sorted(name for name in files if name.startswith(GOLDEN_PREFIX) and name.endswith(".json"))
    print(f"products {len(active)}")
    print(f"records {len(records)}")
    print(f"goldens {len(names)}")

    if reply.SITE != publish_live.URL:
        yield "site-differs"
    mismatches = sum(not posted_matches(replies, product_id) for product_id in active)
    if mismatches:
        yield f"posted-link-mismatch {mismatches}"
    refused = sum(not reply.PRODUCT_ID.fullmatch(row["id"]) for row in records)
    if refused:
        yield f"id-refused {refused}"
    yield from golden_findings(files, names)
    if SHOP_LINK not in shop:
        yield "js-link-missing"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)
    failed = False
    for reason in findings():
        print(f"FAIL {reason}")
        failed = True
    print(f"{'FAIL' if failed else 'PASS'} npp_posted_link_parity")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
