#!/usr/bin/env python3
"""Check photo consent filtering and private price basis on fixed NPP fixtures."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.skills import intake_simple


CASES = [
    {'photo_details': {'name': 'Wildflower Honey', 'brand': 'Cedar Row Apiary', 'size': '12 oz'}},
    {'photo_details': {'name': 'Wildflower Honey', 'brand': 'Cedar Row Apiary', 'size': '12 oz'},
     'photo_confirmed': False},
    {'photo_details': {'name': 'Wildflower Honey', 'brand': 'Cedar Row Apiary', 'size': '12 oz'},
     'photo_confirmed': True},
    {'photo_details': {'name': 'Wildflower Honey', 'brand': 'Cedar Row Apiary', 'size': '12 oz',
                       'printed_claims': ['raw', 'local']},
     'photo_claim_answers': {'0': False}},
    {'photo_details': {'name': 'Wildflower Honey', 'brand': 'Cedar Row Apiary', 'size': '12 oz',
                       'printed_claims': ['raw', 'local']},
     'photo_claim_answers': {'0': True, '1': False}},
    {'photo_details': {'features': ['glass jar', 'cedar lid'], 'count': 3}},
    {'price_unit': 'basket', 'sold_by': 'bag'},
    {'sold_by': 'bundle'},
    {'sold_by': 'pound'},
    {},
]

EXPECTED = (
    "case 0 sources=['Wildflower Honey', 'Cedar Row Apiary', '12 oz'] basis=None",
    "case 1 sources=[] basis=None",
    "case 2 sources=['Wildflower Honey', 'Cedar Row Apiary', '12 oz'] basis=None",
    "case 3 sources=['Wildflower Honey', 'Cedar Row Apiary', '12 oz', 'local'] basis=None",
    "case 4 sources=['Wildflower Honey', 'Cedar Row Apiary', '12 oz', 'raw'] basis=None",
    "case 5 sources=['glass jar', 'cedar lid'] basis=None",
    "case 6 sources=[] basis='basket'",
    "case 7 sources=[] basis='bundle'",
    "case 8 sources=[] basis=None",
    "case 9 sources=[] basis=None",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    parser.parse_args(args)
    if args:  # argparse accepts a bare end-of-options marker even without positionals.
        parser.error('no arguments accepted')

    failed = False
    for i, got in enumerate(CASES):
        try:
            src = intake_simple.public_sources({'intake': got})
            basis = intake_simple._private_price_basis(got)
        except Exception:
            print('FAIL check-error')
            failed = True
            break

        line = f'case {i} sources={src!r} basis={basis!r}'
        print(line)
        claims = got.get('photo_details', {}).get('printed_claims', [])
        answers = got.get('photo_claim_answers', {})
        if (got.get('photo_confirmed') is False and src) or any(
            answers.get(str(k)) is False and claim in src for k, claim in enumerate(claims)
        ):
            print(f'FAIL refused-text-public {i}')
            failed = True
        if line != EXPECTED[i]:
            print(f'FAIL sources-changed {i}')
            failed = True

    print(f'{"FAIL" if failed else "PASS"} npp_photo_details_consent')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
