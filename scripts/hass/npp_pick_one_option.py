#!/usr/bin/env python3
"""Check that fixture option lists yield one clear pick or no pick, offline."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.skills import openreq


def _options():
    return {
        "ids": ["p-honey-1", "p-honey-2", "p-jam-1"],
        "names": ["Wildflower Honey", "Orange Blossom Honey", "Apricot Jam"],
    }


CASES = [
    ("2", _options()),
    ("the second one", _options()),
    ("the jam one", _options()),
    ("orange blossom", _options()),
    ("honey", _options()),
    ("4", _options()),
    ("0", _options()),
    ("the tenth one please", _options()),
    ("the one", _options()),
    ("wildflower jam", _options()),
    ("1", {"ids": ["p-1", "p-2"], "names": ["Honey"]}),
    ("1", {"ids": [], "names": []}),
]
MUST_NONE = (4, 5, 6, 7, 8, 9, 10, 11)
EXPECTED = (
    "case 0 pick='p-honey-2'",
    "case 1 pick='p-honey-2'",
    "case 2 pick='p-jam-1'",
    "case 3 pick='p-honey-2'",
    "case 4 pick=None",
    "case 5 pick=None",
    "case 6 pick=None",
    "case 7 pick=None",
    "case 8 pick=None",
    "case 9 pick=None",
    "case 10 pick=None",
    "case 11 pick=None",
)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    for i, (text, ask) in enumerate(CASES):
        try:
            got = openreq.pick_candidate(text, ask)
        except Exception:
            print("FAIL check-error")
            failed = True
            break

        line = f"case {i} pick={got!r}"
        print(line)
        if i in MUST_NONE and got is not None:
            print(f"FAIL unclear-pick-chosen {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL pick-changed {i}")
            failed = True

    if failed:
        print("FAIL npp_pick_one_option")
        return 1
    print("PASS npp_pick_one_option")
    return 0


if __name__ == "__main__":
    sys.exit(main())
