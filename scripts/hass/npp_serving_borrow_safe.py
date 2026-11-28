#!/usr/bin/env python3
"""Check the catalog serving-sentence borrow rule against offline fixtures."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import newitem


CASES = [
    'Spoon it onto warm toast.',
    'Spoon it onto warm toast',
    'Try it.',
    'Spoon it onto toast from Harbor Lane.',
    'Use 2 spoons in tea.',
    'Stir it into organic yogurt.',
    'Keep it in a cool dry place.',
    'Spread it on bread; it heals sore throats.',
    'Great with cheese and crackers.',
    'Drizzle it over fresh fruit.',
]
MUST_REFUSE = (1, 2, 3, 4, 5, 7)
EXPECTED = (
    'case 0 borrow=yes',
    'case 1 borrow=no',
    'case 2 borrow=no',
    'case 3 borrow=no',
    'case 4 borrow=no',
    'case 5 borrow=no',
    'case 6 borrow=yes',
    'case 7 borrow=no',
    'case 8 borrow=yes',
    'case 9 borrow=yes',
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    failed = False
    for i, sentence in enumerate(CASES):
        try:
            ok = newitem._serving_ok(sentence, '')
        except Exception:
            print('FAIL check-error')
            failed = True
            break
        line = f"case {i} borrow={'yes' if ok else 'no'}"
        print(line)
        if ok and i in MUST_REFUSE:
            print(f'FAIL unsafe-serving-borrowed {i}')
            failed = True
        if line != EXPECTED[i]:
            print(f'FAIL borrow-changed {i}')
            failed = True

    print('FAIL npp_serving_borrow_safe' if failed else 'PASS npp_serving_borrow_safe')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
