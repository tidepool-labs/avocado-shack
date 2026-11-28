#!/usr/bin/env python3
"""Check whether S3 and S10 item readings can bind in copy's name field."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import label_reader, npp
from hass.npp import copy, edits, private_numbers


ITEMS = (
    'wildflower honey',
    "st. john's honey",
    'honey (raw)',
    'salt & pepper',
    'jam/jelly',
    'lemon-lime soda',
    'honey, raw',
    '100% honey',
    'mom’s pickles',
    'dill pickles!',
)


def s3_name(item):
    return label_reader.identity_text('name', item, title=True)


def s10_name(grammar, item):
    words = private_numbers.finance('call it ' + item).public_words
    return dict(edits.read(grammar, words, {}).patch).get('name')


def binding_status(writer, reading):
    if not reading:
        return 'none'
    context = copy.Context('food', 'pantry', 'raw', reading, '')
    return 'bound' if 'item' in writer.bindings(context, 'name') else 'unbound'


def check_items():
    try:
        pinned = npp.assets()
        grammar = edits.Grammar(pinned[1])
        writer = copy.Writer(pinned)
    except Exception:
        # Failed setup prevents any reading from being checked. Never echo exception text.
        print('FAIL check-error')
        return False

    passed = True
    for position, item in enumerate(ITEMS, 1):
        statuses = {}
        findings = []
        for stage, read, args in (
            ('s3', s3_name, (item,)),
            ('s10', s10_name, (grammar, item)),
        ):
            try:
                status = binding_status(writer, read(*args))
            except Exception:
                findings.append('check-error')
                continue
            statuses[stage] = status
            if status == 'unbound':
                findings.append(f'{stage}-unbound {position:02d}')

        # An error has no status: don't misreport an unchecked reading as 'none'.
        if len(statuses) == 2:
            print(f"item {position:02d} s3={statuses['s3']} s10={statuses['s10']}")
        for reason in findings:
            print(f'FAIL {reason}')
            passed = False
    return passed


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    if check_items():
        print('PASS npp_item_copy_binding')
        return 0
    print('FAIL npp_item_copy_binding')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
