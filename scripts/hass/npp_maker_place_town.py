#!/usr/bin/env python3
"""Offline drift guard: a maker's place reads as a town only as 'Town, State'.

Runs itemstd.classify_place over fixed made-up places and pins each answer.
A region, a street address or a contact read as a town would put an invented
origin on a listing. Reads nothing but the repo's own functions; changes nothing.
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import itemstd  # noqa: E402

CASES = ['Fillmore, CA', 'Fillmore', 'Central Coast', 'Central Coast, CA', "California's Central Coast",
         'near Ojai, CA', 'Ventura County, CA', '', None, '123 Main St, CA', 'San Luis Obispo, California',
         'Fillmore, CA, USA', 'Ana@cedarrow, CA', 'Napa Valley, CA']

# Cases that must never be answered 'town': regions, a street address, a contact, a blank.
MUST_NOT_TOWN = (2, 3, 4, 5, 6, 9, 12, 13)

EXPECTED = (
    "case 0 place='town'",
    "case 1 place='other'",
    "case 2 place='region'",
    "case 3 place='region'",
    "case 4 place='region'",
    "case 5 place='region'",
    "case 6 place='region'",
    "case 7 place='blank'",
    "case 8 place='blank'",
    "case 9 place='other'",
    "case 10 place='town'",
    "case 11 place='other'",
    "case 12 place='other'",
    "case 13 place='region'",
)

NAME = "npp_maker_place_town"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    failed = False
    for i, place in enumerate(CASES):
        try:
            got = itemstd.classify_place(place)
        except Exception:
            print("FAIL check-error")
            failed = True
            break
        line = f"case {i} place={got!r}"
        print(line)
        if i in MUST_NOT_TOWN and got == "town":
            print(f"FAIL region-read-as-town {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL place-changed {i}")
            failed = True
    if failed:
        print(f"FAIL {NAME}")
        return 1
    print(f"PASS {NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
