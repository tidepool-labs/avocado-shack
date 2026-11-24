#!/usr/bin/env python3
"""Report catalog availability and restock counts from an offline content copy."""

import argparse
from collections import Counter
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import content_model, sitegen  # noqa: E402


class ReportParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse diagnostics can echo arbitrary arguments, including input paths.
        super().error("invalid arguments; see --help")


def finish(*findings):
    for finding in findings:
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} content_availability_report")
    return int(bool(findings))


def main(argv=None):
    parser = ReportParser(prog="content_availability_report.py", description=__doc__)
    parser.add_argument("--content", required=True, type=Path, metavar="DIR")
    parser.add_argument("--today", type=date.fromisoformat, metavar="YYYY-MM-DD",
                        help="report date (default: the shop's Pacific day)")
    args = parser.parse_args(argv)
    today = args.today if args.today is not None else content_model.shop_today()

    try:
        safe = not args.content.is_symlink() and args.content.is_dir()
    except OSError:
        safe = False
    if not safe:
        return finish("unsafe-input")
    try:
        content = content_model.load_content(args.content)
    except (OSError, ValueError):  # Includes ContentError and decode errors.
        return finish("content-invalid")
    if not isinstance(content.products, list):
        return finish("content-invalid")

    checked = content_model.checked_on(content.store)
    if checked is None:
        print("checked-on none")
    else:
        age = (today - checked).days
        print(f"checked-on {age} days")
        if age > sitegen.STALE_AFTER_DAYS:
            print("note selection-stale")

    counts = Counter()
    states = Counter()
    for product in content.products:
        if not isinstance(product, dict):
            counts["note malformed"] += 1
            continue

        if "available" in product and product["available"] not in content_model.AVAILABILITY:
            counts["bad-available"] += 1
        has_restock = "restock_on" in product
        restock = content_model.iso_day(product.get("restock_on"))
        if has_restock and restock is None:
            counts["bad-restock-day"] += 1

        status = product.get("status")
        if status != "active":
            if has_restock and status in ("hidden", "held"):
                counts["note restock-inactive"] += 1
            continue

        counts["active"] += 1
        state = sitegen.availability_state(product, content.store, today)
        label = sitegen.availability_label(product, content.store, today)
        if state is not None:
            states[state] += 1
        if label is None:
            counts["no-word"] += 1
        elif label.startswith("Last confirmed"):
            counts["last-confirmed"] += 1

        if has_restock:
            counts["restock-set"] += 1
            if state != "no":
                counts["note restock-not-sold-out"] += 1
            elif restock is not None and restock < today:
                counts["note restock-passed"] += 1

    print(f"active {counts['active']}")
    for word in content_model.AVAILABILITY:
        print(f"state {word} {states[word]}")
    for key in ("last-confirmed", "no-word", "restock-set", "note restock-passed",
                "note restock-not-sold-out", "note restock-inactive"):
        print(f"{key} {counts[key]}")
    if counts["note malformed"]:
        print(f"note malformed {counts['note malformed']}")

    return finish(*(f"{key} {counts[key]}" for key in ("bad-available", "bad-restock-day") if counts[key]))


if __name__ == "__main__":
    sys.exit(main())
