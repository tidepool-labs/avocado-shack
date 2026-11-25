#!/usr/bin/env python3
"""Check two products on one photo are not drafted as one listing until named.

Offline drift guard: it calls item_add.several_products on fixed made-up
cases and compares the answers with the pinned ones. No model, network or file.
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.skills import item_add  # noqa: E402


CASES = [
    ("Lemon Curd", "add lemon curd"),
    ("Lemon Curd", "add lemon curd and plum jam"),
    ("Salt and vinegar chips", "add salt and vinegar chips"),
    ("Lemon Curd", ["add lemon curd and plum jam", "The lemon curd only, please"]),
    ("Lemon Curd", ["add lemon curd and plum jam", "lemon curd and plum jam, both"]),
    ("Lemon Curd", "add lemon curd, plum jam"),
    ("Wildflower Honey", "add wildflower honey, Juniper Ridge, Oregon"),
    ("Lemon Curd", "add the lemon curd and the plum jam"),
    ("Jam & Jelly", "add it"),
    ("Lemon Curd", ""),
    ("Lemon Curd", "add plum jam and lemon curd"),
]

# Cases where Mike has not named the one product, so Hass must ask first.
MUST_ASK = (1, 4, 5, 7, 8, 10)

EXPECTED = (
    "case 0 several=no",
    "case 1 several=yes",
    "case 2 several=no",
    "case 3 several=no",
    "case 4 several=yes",
    "case 5 several=yes",
    "case 6 several=no",
    "case 7 several=yes",
    "case 8 several=yes",
    "case 9 several=no",
    "case 10 several=yes",
)

NAME = "npp_two_products_photo"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    failed = False
    for index, (name, message) in enumerate(CASES):
        try:
            got = item_add.several_products(name, message)
        except Exception:
            print("FAIL check-error")
            failed = True
            break
        line = f"case {index} several={'yes' if got else 'no'}"
        print(line)
        if index in MUST_ASK and not got:
            print(f"FAIL two-products-one-listing {index}")
            failed = True
        if line != EXPECTED[index]:
            print(f"FAIL several-changed {index}")
            failed = True
    print(f"{'FAIL' if failed else 'PASS'} {NAME}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
