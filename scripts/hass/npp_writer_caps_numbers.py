#!/usr/bin/env python3
"""Check the writer's capitalised-word and number grounding on offline fixtures."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import newitem


ALLOWED = "wildflower honey from Cedar Row Apiary in Fillmore, 12 oz jar"
CASES = [
    "Wildflower honey from Cedar Row Apiary.",
    "Wildflower honey from Cedar Row Apiary in Fillmore.",
    "Wildflower honey from Cedar Row Apiary in Ojai.",
    "A 12 oz jar of wildflower honey.",
    "A 16 oz jar of wildflower honey.",
    "Wildflower honey, a Gold Medal winner.",
    "Honey made since 1998.",
    "Spoon it onto toast. Pairs with Brie.",
    "Wildflower honey.",
]
MUST_FLAG = (2, 4, 5, 6, 7)
EXPECTED = (
    "case 0 ungrounded=[]",
    "case 1 ungrounded=[]",
    "case 2 ungrounded=['Ojai']",
    "case 3 ungrounded=[]",
    "case 4 ungrounded=['16']",
    "case 5 ungrounded=['Gold', 'Medal']",
    "case 6 ungrounded=['1998']",
    "case 7 ungrounded=['Brie']",
    "case 8 ungrounded=[]",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    failed = False
    for i, text in enumerate(CASES):
        try:
            got = newitem.grounded_text(text, ALLOWED)
        except Exception:
            print("FAIL check-error")
            failed = True
            break

        line = f"case {i} ungrounded={got!r}"
        print(line)
        if i in MUST_FLAG and not got:
            print(f"FAIL ungrounded-name-passed {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL grounded-changed {i}")
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_writer_caps_numbers")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
