#!/usr/bin/env python3
"""Check S3 selling-price shapes against the website editor's product validator."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import content_model
from hass.npp import assets
from hass.npp.missing import MissingInfo, OwnerPrice

AMOUNTS = ['4.00', '04.00', '0.50', '00.50', '000000.00', '999999.99',
           '1000000.00', '4.0', '4', '.50', '0.00']
ITEM = 'Wildflower Honey'
FIXTURE_ID = 'fixture-honey'
NAME = 'npp_price_shape_parity'


def s3_keeps(missing, amount):
    """Return True/False for an observed decision, None for a check-error."""
    try:
        observed = missing.decide(owner_item=ITEM, price=OwnerPrice(amount, 'item')).price.amount
        if observed is None:
            return False
        if isinstance(observed, str) and observed == amount:
            return True
    except Exception:
        pass  # The caller reports only the fixed check-error token.
    return None


def editor_accepts(amount, unit):
    """Distinguish a price refusal from failure to validate the fixture."""
    record = {
        'id': FIXTURE_ID, 'name': ITEM, 'status': 'active', 'category': 'pantry',
        'brand': 'Fixture Farm', 'displayBrand': 'Fixture Farm',
        'description': 'A jar of honey.', 'producerKey': None,
        'image': 'assets/products/fixture.jpg', 'sellingPrice': f'{amount} {unit}',
    }
    problems = []
    try:
        result = content_model.validate_products(problems, [record], {}, None)
        if result is None:
            if not problems:
                return True
            if problems == [f'product {FIXTURE_ID}.sellingPrice: {content_model.SELLING_PRICE_ERROR}']:
                return False
    except Exception:
        pass
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.parse_args(argv)
    try:
        missing = MissingInfo(assets())
    except Exception:
        print('FAIL check-error')
        print(f'FAIL {NAME}')
        return 1

    failed = False
    for i, amount in enumerate(AMOUNTS):
        kept = s3_keeps(missing, amount)
        # Always validate the original amount in both units, even on asked rows.
        each = editor_accepts(amount, 'each')
        per_lb = editor_accepts(amount, 'per lb')
        if None in (kept, each, per_lb):
            print('FAIL check-error')
            failed = True
            continue

        print(f"price {i} s3={'kept' if kept else 'asked'} "
              f"each={'yes' if each else 'no'} per-lb={'yes' if per_lb else 'no'}")
        if kept and not (each and per_lb):
            print(f'FAIL s3-only {i}')
            failed = True
        elif not kept and (each or per_lb):
            print(f'FAIL editor-only {i}')
            failed = True
        if i == 0 and not (kept and each and per_lb):
            print('FAIL control-broken')
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} {NAME}")
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
