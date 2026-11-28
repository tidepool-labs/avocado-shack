#!/usr/bin/env python3
"""Check the release owner matcher offline against synthetic contact details."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import publish_live


FORBIDDEN = ['+1 000 111 2222', 'iMessage;-;owner@fixture-shop.com', '']
CASES = [
    'call 000-111-2222 any time',
    '(000) 111 2222',
    '+1.000.111.2222',
    '0001112222',
    'write OWNER@Fixture-Shop.com',
    'iMessage;-;owner@fixture-shop.com',
    '000-111-2223',
    'the shop at fixture-shop.com',
    '000 111',
    'order 10001112222 shipped',
]
MUST_FIND = (0, 1, 2, 3, 4, 5, 9)
EXPECTED = (
    'case 0 owner=yes',
    'case 1 owner=yes',
    'case 2 owner=yes',
    'case 3 owner=yes',
    'case 4 owner=yes',
    'case 5 owner=yes',
    'case 6 owner=no',
    'case 7 owner=no',
    'case 8 owner=no',
    'case 9 owner=yes',
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    argv = sys.argv[1:] if argv is None else argv
    parser.parse_args(argv)
    if argv:  # argparse accepts a lone end-of-options marker; this CLI takes nothing.
        parser.error('no arguments accepted')

    failed = False
    for index, text in enumerate(CASES):
        try:
            needles = publish_live.owner_needles(FORBIDDEN)
            found = publish_live.owner_found(text.encode('latin1'), needles)
        except Exception:
            print('FAIL check-error')
            failed = True
            break

        line = f'case {index} owner={"yes" if found else "no"}'
        print(line)
        if not found and index in MUST_FIND:
            print(f'FAIL owner-missed {index}')
            failed = True
        if line != EXPECTED[index]:
            print(f'FAIL owner-changed {index}')
            failed = True

    print(f'{"FAIL" if failed else "PASS"} npp_release_owner_match')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
