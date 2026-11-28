#!/usr/bin/env python3
"""Check the catalog's public HTTPS link rules against offline fixtures."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model


CASES = [
    "https://cedarrow.com/honey",
    "https://shop.cedar-row.co.uk/",
    "http://cedarrow.com/",
    "https://127.1/",
    "https://2130706433/",
    "https://0x7f.0.0.1/",
    "https://[::1]/",
    "https://cedarrow.com:8443/",
    "https://user:pw@cedarrow.com/",
    "https://printer.local/",
    "https://cedarrow\\evil.com/",
    "https://cedarrow/",
    "https://caf\xe9.com/",
    "https://cedar row.com/",
    7,
]
MUST_REFUSE = tuple(range(2, 15))
EXPECTED = (
    "case 0 problems=0 why=None",
    "case 1 problems=0 why=None",
    "case 2 problems=1 why=None",
    "case 3 problems=1 why='IP address'",
    "case 4 problems=1 why='IP address'",
    "case 5 problems=1 why='IP address'",
    "case 6 problems=1 why='IP address'",
    "case 7 problems=1 why='port'",
    "case 8 problems=1 why='user or password'",
    "case 9 problems=1 why='private name'",
    "case 10 problems=1 why='backslash'",
    "case 11 problems=1 why='host has no dot'",
    "case 12 problems=1 why='host characters'",
    "case 13 problems=1 why='host characters'",
    "case 14 problems=1 why=None",
)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='npp_public_link_check.py',
                                     description=__doc__, add_help=False)
    parser.parse_args(argv)

    failed = False
    for i, value in enumerate(CASES):
        problems = []
        try:
            content_model._https(problems, 'url', value)
            why = (content_model._not_public(value)
                   if isinstance(value, str) and value.startswith('https://') else None)
        except Exception:
            print('FAIL check-error')
            failed = True
            break

        line = f'case {i} problems={len(problems)} why={why!r}'
        print(line)
        if i in MUST_REFUSE and not problems:
            print(f'FAIL private-link-allowed {i}')
            failed = True
        if line != EXPECTED[i]:
            print(f'FAIL link-changed {i}')
            failed = True

    print('FAIL npp_public_link_check' if failed else 'PASS npp_public_link_check')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
