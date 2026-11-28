#!/usr/bin/env python3
"""Check the offline founding-year and confirmed-town sentence pins."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import maker_site


CASES = [
    ('Cedar Row Apiary was founded in 1998.', 'Cedar Row Apiary', 'Fillmore'),
    ('Cedar Row Apiary was founded in 1998 by two sisters.', 'Cedar Row Apiary', 'Fillmore'),
    ('We started Cedar Row Apiary in 2019.', 'Cedar Row Apiary', 'Fillmore'),
    ('Cedar Row Apiary has made honey since 1998.', 'Cedar Row Apiary', 'Fillmore'),
    ('Cedar Row Apiary was not founded in 1998.', 'Cedar Row Apiary', 'Fillmore'),
    ('Cedar Row Apiary is based in Fillmore.', 'Cedar Row Apiary', 'Fillmore'),
    ('Cedar Row Apiary is based in Ojai.', 'Cedar Row Apiary', 'Fillmore'),
    ('Cedar Row Apiary makes honey in Fillmore.', 'Cedar Row Apiary', 'Fillmore'),
    ('Cedar Row Apiary makes honey by hand in Fillmore.', 'Cedar Row Apiary', 'Fillmore'),
    ('Cedar Row Apiary makes honey that heals in Fillmore.', 'Cedar Row Apiary', 'Fillmore'),
    ('Cedar Row Apiary is not based in Fillmore.', 'Cedar Row Apiary', 'Fillmore'),
    ('Cedar Row Apiary is based in Fillmore.', 'Cedar Row Apiary', ''),
    ('Cedar Row Apiary was founded in 1998 to cure colds.', 'Cedar Row Apiary', 'Fillmore'),
]
MUST_NOTHING = (3, 4, 6, 9, 10, 11, 12)
EXPECTED = (
    'case 0 since=1998 based=no',
    'case 1 since=1998 based=no',
    'case 2 since=2019 based=no',
    'case 3 since=0 based=no',
    'case 4 since=0 based=no',
    'case 5 since=0 based=yes',
    'case 6 since=0 based=no',
    'case 7 since=0 based=yes',
    'case 8 since=0 based=yes',
    'case 9 since=0 based=no',
    'case 10 since=0 based=no',
    'case 11 since=0 based=no',
    'case 12 since=0 based=no',
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    parser.parse_args(args)
    if args:  # argparse normally accepts a bare -- even with no positionals.
        parser.error('no arguments are accepted')

    failed = False
    for i, (sentence, name, town) in enumerate(CASES):
        try:
            since = maker_site._since(sentence, name)
            based = maker_site._based(sentence, name, town)
        except Exception:
            print('FAIL check-error')
            failed = True
            break

        line = f"case {i} since={since} based={'yes' if based else 'no'}"
        print(line)
        if i in MUST_NOTHING and (since != 0 or based):
            print(f'FAIL unstated-fact-read {i}')
            failed = True
        if line != EXPECTED[i]:
            print(f'FAIL fact-changed {i}')
            failed = True

    print('FAIL npp_maker_founded_town' if failed else 'PASS npp_maker_founded_town')
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
