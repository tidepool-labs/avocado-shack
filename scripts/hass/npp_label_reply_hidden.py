#!/usr/bin/env python3
"""Check a label-read reply never names a hidden maker or a held product back to Mike.

Offline and read-only: calls the two pure reply-line helpers of hass.label_reader
on fixture makers and products, prints each answer, and reports any change.
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import label_reader  # noqa: E402

NAME = "npp_label_reply_hidden"

MAKERS = {
    "cedar-row": {"name": "Cedar Row Apiary"},
    "old-mill": {"name": "Old Mill Bakery", "hidden": True},
    "harbor": {"name": "Harbor Lane Farm"},
    "harbor-2": {"name": "Harbor Lane Farm"},
}
PRODUCTS = [
    {"id": "photo-product-001", "name": "Wildflower Honey", "brand": "Cedar Row Apiary", "status": "active"},
    {"id": "photo-product-002", "name": "Rye Loaf", "brand": "Old Mill Bakery", "status": "hidden"},
    {"id": "photo-product-003", "name": "Plum Jam", "brand": "Harbor Lane Farm", "status": "held"},
]
CASES = [
    ("maker", {"brand": "Cedar Row Apiary"}),
    ("maker", {"brand": "cedar row apiary"}),
    ("maker", {"brand": "Old Mill Bakery"}),
    ("maker", {"brand": "Harbor Lane Farm"}),
    ("maker", {"name": "Honey"}),
    ("maker", {"brand": "Juniper Ridge"}),
    ("product", {"name": "Wildflower Honey", "brand": "Cedar Row Apiary"}),
    ("product", {"name": "Rye Loaf", "brand": "Old Mill Bakery"}),
    ("product", {"name": "Plum Jam", "brand": "Harbor Lane Farm"}),
    ("product", {"name": "Wildflower Honey"}),
    ("product", {"name": "Fig Jam", "brand": "Harbor Lane Farm"}),
]
# Cases whose reply must stay silent: the hidden maker and the held product.
MUST_SILENT = (2, 8)
EXPECTED = [
    "case 0 maker=' I know the maker as \\ue000Cedar Row Apiary\\ue001.'",
    "case 1 maker=' I know the maker as \\ue000Cedar Row Apiary\\ue001.'",
    "case 2 maker=''",
    "case 3 maker=''",
    "case 4 maker=''",
    "case 5 maker=''",
    "case 6 product=' \\ue000Wildflower Honey\\ue001 is already on the website."
    " Reply with that name if you want to update it instead.'",
    "case 7 product=' \\ue000Rye Loaf\\ue001 is already saved, but hidden from the website."
    " Reply with that name if you want to update it instead.'",
    "case 8 product=''",
    "case 9 product=''",
    "case 10 product=''",
]


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    failed = False
    for index, (kind, found) in enumerate(CASES):
        try:
            if kind == "maker":
                got = label_reader._maker_line(found, MAKERS)
            else:
                got = label_reader._product_line(found, PRODUCTS)
        except Exception:
            print("FAIL check-error")
            failed = True
            break
        line = f"case {index} {kind}={got!r}"
        print(line)
        if index in MUST_SILENT and got:
            print(f"FAIL hidden-or-held-shown {index}")
            failed = True
        if line != EXPECTED[index]:
            print(f"FAIL line-changed {index}")
            failed = True
    print(f"{'FAIL' if failed else 'PASS'} {NAME}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
