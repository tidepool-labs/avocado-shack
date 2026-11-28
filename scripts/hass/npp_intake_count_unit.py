#!/usr/bin/env python3
"""Check complete stock-count, sold-by and unit answers using offline fixtures."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.skills import item_intake


CASES = [
    ('count', '3'),
    ('count', '0'),
    ('count', 'three jars'),
    ('count', 'a dozen'),
    ('count', 'about 4'),
    ('count', '2000000'),
    ('sold', 'per pound'),
    ('sold', 'by the bag'),
    ('sold', 'each'),
    ('sold', 'per 2 pounds'),
    ('sold', 'pound or bag'),
    ('unit', 'jar'),
    ('unit', 'jar2'),
    ('unit', 'dozen'),
    ('unit', 'jars of honey'),
]
MUST_NONE = (3, 4, 5, 9, 10, 12, 13, 14)
EXPECTED = (
    'case 0 count=3',
    'case 1 count=0',
    'case 2 count=3',
    'case 3 count=None',
    'case 4 count=None',
    'case 5 count=None',
    "case 6 sold='pound'",
    "case 7 sold='bag'",
    "case 8 sold='item'",
    'case 9 sold=None',
    'case 10 sold=None',
    "case 11 unit='jar'",
    'case 12 unit=None',
    'case 13 unit=None',
    'case 14 unit=None',
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    checks = {
        'count': item_intake._parse_count,
        'sold': item_intake._parse_sold_by,
        'unit': item_intake._parse_unit,
    }
    failed = False
    for index, (kind, text) in enumerate(CASES):
        try:
            got = checks[kind](text)
        except Exception:
            print('FAIL check-error')
            failed = True
            break

        line = f'case {index} {kind}={got!r}'
        print(line)
        if index in MUST_NONE and got is not None:
            print(f'FAIL number-erased {index}')
            failed = True
        if line != EXPECTED[index]:
            print(f'FAIL answer-changed {index}')
            failed = True

    if failed:
        print('FAIL npp_intake_count_unit')
        return 1
    print('PASS npp_intake_count_unit')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
