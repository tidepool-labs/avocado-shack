#!/usr/bin/env python3
"""Check offline which fixture sentences the maker-page filter admits."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import maker_site


CASES = [
    ("Bluebird Pantry cooks small batches of jam in a shared kitchen.", "Bluebird Pantry", "Fillmore"),
    ("We cook small batches of jam in a shared kitchen each week.", "Bluebird Pantry", "Fillmore"),
    ("Bluebird Pantry cooks small batches of organic jam each week.", "Bluebird Pantry", "Fillmore"),
    ("Bluebird Pantry cooks the finest jam you will ever taste here.", "Bluebird Pantry", "Fillmore"),
    ("Bluebird Pantry cooks small batches of jam for Whole Foods Market.", "Bluebird Pantry", "Fillmore"),
    ("Bluebird Pantry cooks small batches of jam that soothes colds.", "Bluebird Pantry", "Fillmore"),
    ("Bluebird Pantry cooks small batches of jam in a shared kitchen!", "Bluebird Pantry", "Fillmore"),
    ("Bluebird Pantry cooks jam in batches of 12 jars every week.", "Bluebird Pantry", "Fillmore"),
    ("Bluebird Pantry cooks small batches of jam, sold at the market.", "Bluebird Pantry", "Fillmore"),
    ("Bluebird Pantry cooks small batches of j\u0430m in a shared kitchen.", "Bluebird Pantry", "Fillmore"),
    ("Bluebird Pantry cooks small batches of the best jam each week.", "Bluebird Pantry", "Fillmore"),
    ("Bluebird Pantry cooks small batches of jam in Fillmore each week.", "Bluebird Pantry", "Fillmore"),
    ("Short.", "Bluebird Pantry", "Fillmore"),
    ("Visit https://bluebird.example for the jam we cook each week.", "Bluebird Pantry", "Fillmore"),
]

MUST_DROP = (2, 3, 4, 5, 6, 7, 9, 10, 12, 13)
EXPECTED = (
    "case 0 kept=yes",
    "case 1 kept=yes",
    "case 2 kept=no",
    "case 3 kept=no",
    "case 4 kept=no",
    "case 5 kept=no",
    "case 6 kept=no",
    "case 7 kept=no",
    "case 8 kept=yes",
    "case 9 kept=no",
    "case 10 kept=no",
    "case 11 kept=yes",
    "case 12 kept=no",
    "case 13 kept=no",
)


def main(argv=None):
    # Even --help is outside this no-argument command's interface.
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)

    failed = False
    for i, (sentence, name, town) in enumerate(CASES):
        try:
            got = maker_site.source_ok(sentence, name, town)
        except Exception:
            print("FAIL check-error")
            failed = True
            break

        kept = got is not None
        line = f"case {i} kept={'yes' if kept else 'no'}"
        print(line)
        if kept and i in MUST_DROP:
            print(f"FAIL unsafe-sentence-kept {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL sentence-changed {i}")
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_maker_page_sentence")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
