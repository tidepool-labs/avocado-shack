#!/usr/bin/env python3
"""Check that new product records fail the house shape check for a bad picture path, shelf, maker, field set or text.

Offline and read only: it calls hass.house_style.check_product on fixed in-memory records and compares the
answers with the pinned ones.
"""

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import house_style  # noqa: E402

NAME = "npp_product_record_shape"
MISSING = "<missing>"

BASE = {
    "id": "photo-product-012",
    "name": "Wildflower Honey",
    "brand": "Cedar Row Apiary",
    "category": "pantry",
    "image": "assets/products/photo-product-012.webp",
    "description": "Wildflower honey from Cedar Row Apiary.",
    "producerKey": "cedar-row",
    "displayBrand": "Cedar Row Apiary",
    "status": "active",
}
MAKERS = {"cedar-row": {"name": "Cedar Row Apiary"}}

CASES = [
    [],
    [("image", "../../private/photo.webp")],
    [("category", "candy")],
    [("producerKey", "ghost")],
    [("displayBrand", "Best in Town")],
    [("brand", "Producer not identified"), ("displayBrand", "From the market"), ("producerKey", None)],
    [("brand", "Producer not identified"), ("displayBrand", "From the market")],
    [("id", "p-12")],
    [("secret", "x")],
    [("description", "<missing>")],
    [("name", "Honey\u200b")],
    [("image", "assets/products/photo-0123456789abcdef.jpg")],
    [("producerKey", ["cedar-row"])],
]
# Records that must never pass the shape check.
MUST_FAIL = (1, 2, 3, 8, 9, 10, 12)
# Pinned answers measured at c8cdcc95; cases 4, 6 and 7 pass on soft checks only (an observation for the owner).
EXPECTED = [
    "case 0 pass=yes score=100 hard=[]",
    "case 1 pass=no score=88 hard=['picture path']",
    "case 2 pass=no score=81 hard=['shelf is one of the nine']",
    "case 3 pass=no score=81 hard=['maker link']",
    "case 4 pass=yes score=88 hard=[]",
    "case 5 pass=yes score=100 hard=[]",
    "case 6 pass=yes score=94 hard=[]",
    "case 7 pass=yes score=94 hard=[]",
    "case 8 pass=no score=81 hard=['fields']",
    "case 9 pass=no score=81 hard=['fields']",
    "case 10 pass=no score=94 hard=['name and brand text']",
    "case 11 pass=yes score=100 hard=[]",
    "case 12 pass=no score=81 hard=['maker link']",
]


def build(overrides):
    rec = dict(BASE)
    for field, value in overrides:
        if value == MISSING:
            rec.pop(field, None)
        else:
            rec[field] = value
    return rec


def run():
    """Return (informational and finding lines, ok)."""
    lines = []
    ok = True
    for i, overrides in enumerate(CASES):
        try:
            got = house_style.check_product(build(overrides), MAKERS)
            line = f"case {i} pass={'yes' if got['pass'] else 'no'} score={got['score']} hard={got['hard_failures']!r}"
            passed = bool(got["pass"])
        except Exception:  # noqa: BLE001 - reported as a named finding, never the exception text
            lines.append("FAIL check-error")
            return lines, False
        lines.append(line)
        if passed and i in MUST_FAIL:
            lines.append(f"FAIL bad-record-passed {i}")
            ok = False
        if line != EXPECTED[i]:
            lines.append(f"FAIL record-changed {i}")
            ok = False
    return lines, ok


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    lines, ok = run()
    for line in lines:
        print(line)
    print(f"PASS {NAME}" if ok else f"FAIL {NAME}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
