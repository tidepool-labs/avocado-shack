#!/usr/bin/env python3
"""Check the public-name claim omission fixtures without changing any listing."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import newitem


CASES = [
    ('Organic Wildflower Honey', 'honey', 'organic'),
    ('Raw local honey', 'honey', 'local'),
    ('Wildflower Honey', 'honey', ''),
    ('Organic', 'honey', 'organic'),
    ('Orgánic Apricot Jam', 'jam', 'org'),
    ('Certified organic olive oil', 'oil', 'certified'),
    ('Non-GMO corn tortillas', 'tortillas', 'gmo'),
    ('Detox green tea', 'tea', 'detox'),
    ('Free-range eggs', 'eggs', 'range'),
    ('Honey', 'honey', ''),
    (None, 'honey', ''),
]
EXPECTED = [
    "case 0 name='Wildflower Honey'",
    "case 1 name='Honey'",
    "case 2 name='Wildflower Honey'",
    "case 3 name='Honey'",
    "case 4 name='Apricot Jam'",
    "case 5 name='Olive oil'",
    "case 6 name='Corn tortillas'",
    "case 7 name='Green tea'",
    "case 8 name='Eggs'",
    "case 9 name='Honey'",
    "case 10 name=None",
]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    failed = False
    for i, (name, kind, word) in enumerate(CASES):
        try:
            got = newitem.without_claims(name, kind)
        except Exception:
            print('FAIL check-error')
            failed = True
            break

        line = f'case {i} name={got!r}'
        print(line)
        if word and word in (got or '').casefold():
            print(f'FAIL claim-left-in-name {i}')
            failed = True
        if line != EXPECTED[i]:
            print(f'FAIL name-changed {i}')
            failed = True

    print('FAIL npp_name_claim_strip' if failed else 'PASS npp_name_claim_strip')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
