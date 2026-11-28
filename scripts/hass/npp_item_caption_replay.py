#!/usr/bin/env python3
"""Replay synthetic captions through the NPP finance and item readers offline."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.npp import job, private_numbers


CAPTIONS = (
    "it's honey",
    "it's honey, selling $4 each",
    "it's honey selling $4 each",
    "it's honey; $4 each",
    "it's honey $4 each",
    "the item is honey, $4 each",
    "product: honey, paid $2, selling $4",
    "it's honey, paid 2 selling 4",
    "selling $4 each, it's honey",
    "it is lavender honey from Etto, $9 each",
    "it's honey\nselling $4 each",
    "item: honey. $4 each",
)


def yes_no(present):
    return "yes" if present else "no"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    if args:
        parser.error("no arguments accepted")

    failed = False
    for position, caption in enumerate(CAPTIONS, 1):
        try:
            finance = private_numbers.finance(caption)
            raw_item = job.owner_item(caption) is not None
            item = job.owner_item(finance.public_words) is not None
            price = finance.selling_price is not None
        except Exception:
            # A reader exception could contain private text. Report only the class of finding.
            print("FAIL check-error")
            failed = True
            continue

        print(f"caption {position:02d} raw-item={yes_no(raw_item)} "
              f"item={yes_no(item)} price={yes_no(price)}")
        if raw_item and not item:
            print(f"FAIL item-lost {position:02d}")
            failed = True

    print("FAIL npp_item_caption_replay" if failed else "PASS npp_item_caption_replay")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
