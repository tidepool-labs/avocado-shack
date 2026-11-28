#!/usr/bin/env python3
"""Check the selling-price and public-text readings of synthetic NPP captions."""

import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.npp import private_numbers


CAPTIONS = (
    "$5 each",
    "paid $3, selling $5 each",
    "$5 each, have 12",
    "$5 each and 12 in stock",
    "$5 each, we have twelve",
    "$5 each (paid $3)",
    "$5 each and $3 cost",
    "selling $5 each, got 12",
)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    for i, caption in enumerate(CAPTIONS):
        try:
            finance = private_numbers.finance(caption)
        except Exception:
            # Do not expose a parser exception that could include finance text.
            print("FAIL check-error")
            failed = True
            continue

        price = finance.selling_price
        display_price = price.replace(" ", "_") if price is not None else "none"
        print(f"case {i} price={display_price} cost={int(finance.has_cost)} count={int(finance.has_qty)}")
        if price != "5.00 each":
            print(f"FAIL price-lost {i}")
            failed = True
        if re.search(r"\d", finance.public_words):
            print(f"FAIL number-in-public {i}")
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_two_number_captions")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
