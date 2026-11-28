#!/usr/bin/env python3
"""Check the heading and wording of Hass's private intake summary offline."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.skills import item_intake

HEAD = 'Kept private, not on the website:'
CASES = [
    {},
    {'qty': 12, 'qty_unit': 'jar', 'sold_by': 'item', 'price': '9.50', 'cost': '4.25'},
    {'qty': 1, 'qty_unit': 'loaf'},
    {'qty': 2.5, 'qty_unit': 'lb', 'sold_by': 'pound', 'price': '6.00'},
    {'origin': 'Fillmore hills.', 'claims': 'raw'},
    {'best_by': '2027-01-15', 'received': 'not-a-day'},
    {'low_stock': 0, 'customer_note': 'Great on toast'},
    {'price': None, 'cost': None, 'qty': None},
    'not a dict',
]
MUST_MARKED = (1, 2, 3, 4, 5, 6, 7)
EXPECTED = [
    [],
    [HEAD, 'Bought: 12 \ue000jars\ue001.', 'Sold per item.',
     'Price: $9.50 for each one.', 'You paid: $4.25 for each one.'],
    [HEAD, 'Bought: 1 \ue000loaf\ue001.'],
    [HEAD, 'Bought: 2.5 \ue000lb\ue001.', 'Sold per pound.', 'Price: $6.00 per pound.'],
    [HEAD, 'Origin: \ue000Fillmore hills\ue001.', 'On the label (unverified, your word): \ue000raw\ue001.'],
    [HEAD, 'Best by: Jan 15, 2027.', "Bought or received: a day I can't read."],
    [HEAD, 'Low on stock at: 0.', 'Your sentence for customers: \ue000Great on toast\ue001.'],
    [HEAD, 'Skipped, so I left them blank: qty, price, cost.'],
    [],
]


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    for i, intake in enumerate(CASES):
        try:
            lines = item_intake.private_lines(intake)
        except Exception:
            print('FAIL check-error')
            failed = True
            break
        print(f'case {i} lines={lines!r}')
        if i in MUST_MARKED and (not lines or lines[0] != HEAD):
            print(f'FAIL unmarked-private {i}')
            failed = True
        if lines != EXPECTED[i]:
            print(f'FAIL lines-changed {i}')
            failed = True
    print(f'{"FAIL" if failed else "PASS"} npp_intake_private_lines')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
