#!/usr/bin/env python3
"""Check how Hass reads plain product phrases, using offline fixtures only."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import maker_site


CASES = [
    'honey and beeswax candles.',
    'jam, jelly and marmalade in small batches.',
    'honey and relieves migraines.',
    'every kind of honey.',
    'honey for 30 dollars.',
    'and honey.',
    'honey and and jam.',
    'small-batch honey.',
    'cures for colds.',
    'sourdough bread for the farmers market.',
    '',
    'honey and gravel.',
]
MUST_NONE = (2, 3, 5, 6, 8, 10, 11)
EXPECTED = (
    "case 0 things='honey and beeswax candles'",
    "case 1 things='jam, jelly and marmalade'",
    "case 2 things=None",
    "case 3 things=None",
    "case 4 things='honey'",
    "case 5 things=None",
    "case 6 things=None",
    "case 7 things='small-batch honey'",
    "case 8 things=None",
    "case 9 things='sourdough bread'",
    "case 10 things=None",
    "case 11 things=None",
)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    if argv:  # Even a lone '--' is invalid: this tool takes no arguments.
        parser.error("no arguments are accepted")

    failed = False
    for i, phrase in enumerate(CASES):
        try:
            got = maker_site._things(phrase)
        except Exception:
            print("FAIL check-error")
            failed = True
            break

        line = f"case {i} things={got!r}"
        print(line)
        if i in MUST_NONE and got is not None:
            print(f"FAIL non-product-thing-read {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL things-changed {i}")
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_maker_things_plain")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
