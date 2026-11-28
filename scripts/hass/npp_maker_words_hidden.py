#!/usr/bin/env python3
"""Check visible maker matching and maker relations using offline fixtures."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import newitem


MAKERS = {
    "cedar-row": {"name": "Cedar Row Apiary"},
    "old-mill": {"name": "Old Mill Bakery", "hidden": True},
    "harbor": {"name": "Harbor Lane Farm"},
    "harbor-lane-farm-west": {"name": "Harbor Lane Farm West"},
}
HIDDEN = {"old-mill"}
CASES = [
    "new honey from Cedar Row Apiary",
    "bread from Old Mill Bakery",
    "old-mill sourdough",
    "jam by Harbor Lane Farm West in Ventura, CA",
    "jam by Harbor Lane Farm",
    "made by Juniper Ridge in Ojai, CA.",
    "out of Bluebird & Co",
    "from the market",
    "",
]
EXPECTED = (
    "case 0 maker='cedar-row' relations=[('Cedar Row Apiary', None)]",
    "case 1 maker=None relations=[('Old Mill Bakery', None)]",
    "case 2 maker=None relations=[]",
    "case 3 maker='harbor-lane-farm-west' relations=[('Harbor Lane Farm West', 'Ventura, CA')]",
    "case 4 maker='harbor' relations=[('Harbor Lane Farm', None)]",
    "case 5 maker=None relations=[('Juniper Ridge', 'Ojai, CA')]",
    "case 6 maker=None relations=[('Bluebird & Co', None)]",
    "case 7 maker=None relations=[]",
    "case 8 maker=None relations=[]",
)


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    for i, text in enumerate(CASES):
        try:
            found = newitem.find_maker(text, MAKERS)
            rel = newitem.maker_relations(text)
        except Exception:
            print("FAIL check-error")
            failed = True
            break

        line = f"case {i} maker={found!r} relations={rel!r}"
        print(line)
        if found in HIDDEN:
            print(f"FAIL hidden-maker-found {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL maker-changed {i}")
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_maker_words_hidden")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
