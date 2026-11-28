#!/usr/bin/env python3
"""Check the offline intake parser and display against fixed selling-price answers."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.skills import item_intake


CASES = [
    '$9.57', '9.5', '9 dollars', '9 dollars and 57 cents', 'nine dollars',
    '57 cents', '4 or 5 bucks', 'about 4', '120 cents', '$1234567',
    '4 each', '$4 a jar', '',
]
MUST_NONE = (6, 7, 8, 9, 12)
EXPECTED = (
    "case 0 money='9.57' shown='$9.57'",
    "case 1 money='9.50' shown='$9.50'",
    "case 2 money='9.00' shown='$9.00'",
    "case 3 money='9.57' shown='$9.57'",
    "case 4 money='9.00' shown='$9.00'",
    "case 5 money='0.57' shown='$0.57'",
    "case 6 money=None shown=''",
    "case 7 money=None shown=''",
    "case 8 money=None shown=''",
    "case 9 money=None shown=''",
    "case 10 money='4.00' shown='$4.00'",
    "case 11 money='4.00' shown='$4.00'",
    "case 12 money=None shown=''",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    argv = sys.argv[1:] if argv is None else argv
    parser.parse_args(argv)
    if argv:  # argparse can consume a bare end-of-options marker.
        parser.error('no arguments are accepted')

    failed = False
    for i, text in enumerate(CASES):
        try:
            money = item_intake._parse_money(text)
            shown = item_intake.money_text(money)
        except Exception:
            print('FAIL check-error')
            failed = True
            break

        line = f'case {i} money={money!r} shown={shown!r}'
        print(line)
        if i in MUST_NONE and money is not None:
            print(f'FAIL unsure-amount-read {i}')
            failed = True
        if line != EXPECTED[i]:
            print(f'FAIL money-changed {i}')
            failed = True

    print('FAIL npp_intake_money_words' if failed else 'PASS npp_intake_money_words')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
