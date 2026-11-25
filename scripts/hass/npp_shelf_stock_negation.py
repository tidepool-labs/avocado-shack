#!/usr/bin/env python3
"""Check a new item's shelf and availability are read from Mike's words only when not negated.

Offline drift guard: runs the pure repo readers over a few fixed texts, prints what each one read, and fails
when a negated phrase sets a shelf or an availability word, or when any pinned answer changes.
Run as `python3 -B scripts/hass/npp_shelf_stock_negation.py` (no arguments).
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import claims, newitem  # noqa: E402,F401 - claims is the negator gate both readers go through

NAME = "npp_shelf_stock_negation"

CASES = ['put it on the pantry shelf', 'not on the pantry shelf', 'dairy section please', 'shelf: bread', 'sold out',
         'not sold out', 'only a few left', 'it is never limited', 'plenty of jars', '', 'no pantry shelf for this one',
         "it isn't sold out yet"]

# Cases whose words are negated or absent: they must not read as shelf 'pantry' or availability 'no'/'limited'.
MUST_NONE = (1, 5, 7, 10, 11)

# Pinned answers measured offline (case 3, "shelf: bread", reads as no shelf: an observation, not a finding).
EXPECTED = [
    "case 0 shelf='pantry' availability=None",
    "case 1 shelf=None availability=None",
    "case 2 shelf='dairy' availability=None",
    "case 3 shelf=None availability=None",
    "case 4 shelf=None availability='no'",
    "case 5 shelf=None availability=None",
    "case 6 shelf=None availability='limited'",
    "case 7 shelf=None availability=None",
    "case 8 shelf=None availability=None",
    "case 9 shelf=None availability=None",
    "case 10 shelf=None availability=None",
    "case 11 shelf=None availability=None",
]


def main(argv=None):
    argparse.ArgumentParser(prog="npp_shelf_stock_negation.py", description="Check shelf and availability are read only when not negated.").parse_args(argv)
    failed = False
    for i, text in enumerate(CASES):
        try:
            shelf = newitem.stated_shelf(text)
            avail = newitem._availability_evidence(newitem._fold(text))
        except Exception:  # noqa: BLE001 - any repo failure is the named finding, without its text
            print("FAIL check-error")
            failed = True
            break
        line = f"case {i} shelf={shelf!r} availability={avail!r}"
        print(line)
        if i in MUST_NONE and (shelf == "pantry" or avail in ("no", "limited")):
            print(f"FAIL negated-word-read {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL evidence-changed {i}")
            failed = True
    print(f"FAIL {NAME}" if failed else f"PASS {NAME}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
