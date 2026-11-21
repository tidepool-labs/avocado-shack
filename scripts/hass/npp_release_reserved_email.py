#!/usr/bin/env python3
"""Check the release email screen against synthetic text and binary fixtures."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import publish_live


CASES = [
    ('write to ana@fixture-shop.com today', 'page.html'),
    ('you@example.com', 'page.html'),
    ('ops@mail.example.org', 'page.html'),
    ('qa@shop.test', 'page.html'),
    ('MIKE@EXAMPLE.COM', 'page.html'),
    ('ab@fixture-shop.com', 'photo.jpg'),
    ('abc@fixture-shop.com', 'photo.jpg'),
    ('abc@fixture-shop.xyz', 'photo.jpg'),
    ('abc@fixture-shop.xyz', 'notes.txt'),
    ('x\x00y abc@fixture-shop.com', 'notes.txt'),
]
MUST_HIT = (0, 6, 8, 9)
EXPECTED = (
    "case 0 hits=['ana@fixture-shop.com'] binary=no",
    'case 1 hits=[] binary=no',
    'case 2 hits=[] binary=no',
    'case 3 hits=[] binary=no',
    'case 4 hits=[] binary=no',
    'case 5 hits=[] binary=yes',
    "case 6 hits=['abc@fixture-shop.com'] binary=yes",
    'case 7 hits=[] binary=yes',
    "case 8 hits=['abc@fixture-shop.xyz'] binary=no",
    "case 9 hits=['abc@fixture-shop.com'] binary=yes",
)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    for i, (text, path) in enumerate(CASES):
        try:
            hits = sorted(publish_live.pattern_hits('email', publish_live.PATTERNS['email'], text, path))
            binary = 'yes' if publish_live.is_binary(text, path) else 'no'
        except Exception:
            print('FAIL check-error')
            failed = True
            break

        line = f'case {i} hits={hits!r} binary={binary}'
        print(line)
        if i in MUST_HIT and not hits:
            print(f'FAIL real-address-dropped {i}')
            failed = True
        if line != EXPECTED[i]:
            print(f'FAIL hits-changed {i}')
            failed = True

    if failed:
        print('FAIL npp_release_reserved_email')
        return 1
    print('PASS npp_release_reserved_email')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
