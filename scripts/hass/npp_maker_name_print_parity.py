#!/usr/bin/env python3
"""Check offline whether S4 maker identities can bind into an S5 story."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp
from hass.npp import copy, research


NAMES = ('Miners Orchards', 'Smith & Sons', 'Miners Orchards Inc.', 'Ben & Jerry Farm')
TOWNS = ('Watsonville', 'St. Helena', 'Mt. Shasta')


def main(argv=None):
    # Even --help is an argument to this no-arguments diagnostic.
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    try:
        writer = copy.Writer(hass.npp.assets())
    except Exception:
        print('FAIL check-error')
        print('FAIL npp_maker_name_print_parity')
        return 1

    failed = False
    for label, key, prefix, values in (
        ('name', 'maker_name', 'Honey made by ', NAMES),
        ('town', 'town', 'Honey from a farm based in ', TOWNS),
    ):
        for i, value in enumerate(values):
            try:
                s4 = research._identity_field(value)
                ctx = copy.Context('food', 'pantry', 'raw', 'Honey',
                                   owner_words=prefix + value,
                                   maker_name=value if key == 'maker_name' else '',
                                   town=value if key == 'town' else '')
                s5 = key in writer.bindings(ctx, 'story')
            except Exception:
                print('FAIL check-error')
                failed = True
                continue

            print(f'{label} {i} s4={"yes" if s4 else "no"} s5={"yes" if s5 else "no"}')
            if s4 and not s5:
                print(f'FAIL s5-cannot-print {label} {i}')
                failed = True

    print(f'{"FAIL" if failed else "PASS"} npp_maker_name_print_parity')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
