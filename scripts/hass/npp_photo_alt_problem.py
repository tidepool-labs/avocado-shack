#!/usr/bin/env python3
"""Check the NPP photo alt-text rule against fixed offline fixtures."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.ops import photos  # noqa: E402

SHA = 'c0ffee12ab34' + '0' * 52
CASES = [
    'Jars of wildflower honey on a wooden shelf',
    'crate-shot.jpg',
    'IMG_2041',
    'photo',
    'the product photo 2',
    'c0ffee12ab34 honey',
    'ab',
    'Screenshot 2026-11-21 at 9.41',
    'https://fixture-shop.com/honey',
    'todo',
    'Honey jar with a cedar lid',
]
MUST_REFUSE = (1, 2, 3, 4, 5, 6, 7, 8, 9)
EXPECTED = (
    'case 0 refused=no',
    'case 1 refused=yes',
    'case 2 refused=yes',
    'case 3 refused=yes',
    'case 4 refused=yes',
    'case 5 refused=yes',
    'case 6 refused=yes',
    'case 7 refused=yes',
    'case 8 refused=yes',
    'case 9 refused=yes',
    'case 10 refused=no',
)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    for i, alt in enumerate(CASES):
        try:
            refused = photos._alt_problem(alt, SHA) == photos.ALT_REPLY
        except Exception:
            print('FAIL check-error')
            failed = True
            break

        line = f"case {i} refused={'yes' if refused else 'no'}"
        print(line)
        if i in MUST_REFUSE and not refused:
            print(f'FAIL bad-alt-kept {i}')
            failed = True
        if line != EXPECTED[i]:
            print(f'FAIL alt-changed {i}')
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_photo_alt_problem")
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
