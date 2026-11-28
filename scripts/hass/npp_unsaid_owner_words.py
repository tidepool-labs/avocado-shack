#!/usr/bin/env python3
"""Check the NPP owner-words policy offline with synthetic draft records."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import live_policy


def _product(brand, *, before=None, **fields):
    return {
        'ops': [{'op': 'product.add'}],
        'records': [{'collection': 'products', 'before': before,
                     'after': {'brand': brand, **fields}}],
    }


CASES = [
    (_product('Harbor Lane Farm'), 'add the harbor lane farm honey'),
    (_product('Harbor Lane Farm'), 'add this honey'),
    (_product('Harbor Lane Farm'), 'it is not from harbor lane farm'),
    (_product('Harbor Lane Farm'), 'harbor lane farm maybe'),
    (_product('Harbor Lane Farm'), 'is it harbor lane farm?'),
    (_product('Harbor Lane Farm'), 'can you add harbor lane farm honey?'),
    (_product('Producer not identified', displayBrand='From the market'), 'add the honey'),
    (_product('Harbor Lane Farm', displayBrand='Cedar Row'), 'add the harbor lane farm honey'),
    ({'ops': [{'op': 'product.add'}, {'op': 'maker.add'}],
      'records': [{'collection': 'makers', 'before': None,
                   'after': {'name': 'Cedar Row Apiary', 'place': 'Fillmore, CA'}}]},
     'new honey from cedar row apiary'),
    (_product('Harbor Lane Farm', before={'brand': 'Old'}), 'add this honey'),
]

MUST_ASK = (1, 2, 3, 4, 7, 8)
EXPECTED = (
    'case 0 unsaid=[]',
    "case 1 unsaid=['Harbor Lane Farm']",
    "case 2 unsaid=['Harbor Lane Farm']",
    "case 3 unsaid=['Harbor Lane Farm']",
    "case 4 unsaid=['Harbor Lane Farm']",
    'case 5 unsaid=[]',
    'case 6 unsaid=[]',
    "case 7 unsaid=['Cedar Row']",
    "case 8 unsaid=['Fillmore']",
    'case 9 unsaid=[]',
)


def main(argv=None):
    # Even the conventional --help flag is outside this no-argument interface.
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    for i, (draft, owner_text) in enumerate(CASES):
        try:
            found = live_policy.unsaid(draft, owner_text)
        except Exception:
            print('FAIL check-error')
            failed = True
            break
        line = f'case {i} unsaid={found!r}'
        print(line)
        if i in MUST_ASK and found == []:
            print(f'FAIL unsaid-missed {i}')
            failed = True
        if line != EXPECTED[i]:
            print(f'FAIL unsaid-changed {i}')
            failed = True
    print('FAIL npp_unsaid_owner_words' if failed else 'PASS npp_unsaid_owner_words')
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
