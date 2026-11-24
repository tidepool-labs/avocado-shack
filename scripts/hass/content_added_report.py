#!/usr/bin/env python3
"""Report counts of catalog additions and public-field coverage from a copy."""

import argparse
from collections import Counter
from datetime import date
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model


PHOTO_IMAGE = re.compile(r"assets/products/photo-[0-9a-f]{16}\.(jpg|png)")
COVERAGE = (
    "price-each", "price-per-lb", "price-plain", "supplier", "image-alt", "photo-image",
    "note added-no-price", "note added-no-alt", "note hidden-dated",
)
FINDINGS = ("bad-selling-price", "bad-added-on", "added-in-future")


class ReportParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse diagnostics can echo rejected values and unrecognized arguments.
        super().error("invalid arguments; see --help")


def has_text(value):
    return isinstance(value, str) and bool(value.strip())


def finish(*findings):
    for finding in findings:
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} content_added_report")
    return int(bool(findings))


def report(products, since, today):
    counts = Counter()
    days = Counter()
    for product in products:
        if not isinstance(product, dict):
            counts["note malformed"] += 1
            continue
        status = product.get("status")
        if status in ("hidden", "held") and "addedOn" in product:
            counts["note hidden-dated"] += 1
            continue

        price = product.get("sellingPrice")
        valid_price = isinstance(price, str) and content_model.valid_selling_price(price)
        if "sellingPrice" in product and not valid_price:
            counts["bad-selling-price"] += 1
        added = content_model.iso_day(product.get("addedOn"))
        if "addedOn" in product:
            if added is None:
                counts["bad-added-on"] += 1
            elif added > today:
                counts["added-in-future"] += 1
        if status != "active":
            continue

        counts["active"] += 1
        alt = has_text(product.get("imageAlt"))
        if added is not None:
            days[added] += 1
            counts["note added-no-price"] += "sellingPrice" not in product
            counts["note added-no-alt"] += not alt
        if valid_price:
            if price.endswith(" each"):
                counts["price-each"] += 1
            elif price.endswith(" per lb"):
                counts["price-per-lb"] += 1
            else:
                counts["price-plain"] += 1
        counts["supplier"] += has_text(product.get("supplier"))
        counts["image-alt"] += alt
        image = product.get("image")
        if isinstance(image, str) and PHOTO_IMAGE.fullmatch(image):
            counts["photo-image"] += 1

    print(f"active {counts['active']}")
    print(f"added-dated {sum(days.values())}")
    for day, count in sorted(days.items()):
        if since is None or day >= since:
            print(f"added-day {day} {count}")
    for label in COVERAGE:
        print(f"{label} {counts[label]}")
    if counts["note malformed"]:
        print(f"note malformed {counts['note malformed']}")
    return finish(*(f"{reason} {counts[reason]}" for reason in FINDINGS if counts[reason]))


def main(argv=None):
    parser = ReportParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", required=True, type=Path, metavar="DIR", help="catalog copy (read only)")
    parser.add_argument("--since", type=date.fromisoformat, metavar="YYYY-MM-DD", help="first day to show")
    parser.add_argument("--today", type=date.fromisoformat, metavar="YYYY-MM-DD", help="override the shop's Pacific day")
    args = parser.parse_args(argv)
    if args.content.is_symlink() or not args.content.is_dir():
        return finish("unsafe-input")
    try:
        products = content_model.load_content(args.content).products
    except (ValueError, OSError):  # ContentError, decoding failures and unreadable copies
        return finish("content-invalid")
    if not isinstance(products, list):
        return finish("content-invalid")
    return report(products, args.since, args.today or content_model.shop_today())


if __name__ == "__main__":
    sys.exit(main())
