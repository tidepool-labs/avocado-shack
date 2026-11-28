#!/usr/bin/env python3
"""Replay the NPP field validator over the checked-in catalog; report counts only."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import npp
from hass.npp import copy, validate

PRODUCTS = ROOT / 'hass/content/products.json'
PRODUCTS_CAP = 2_000_000
FIELDS = ('name', 'description', 'imageAlt')
REQUIRED = ('id', 'name', 'status', 'category')
REASON = re.compile(r'[a-z][a-z-]{0,40}')
TOOL = 'npp_field_check_replay'


def _reject_json_constant(_token):
    raise ValueError('not a JSON number')


def _load_products():
    try:
        info = PRODUCTS.lstat()
        if not stat.S_ISREG(info.st_mode):
            return [], 0, 'input-unsafe products'
        if info.st_size > PRODUCTS_CAP:
            return [], 0, 'input-too-large products'
        with PRODUCTS.open('rb') as source:
            raw = source.read(PRODUCTS_CAP + 1)
        if len(raw) > PRODUCTS_CAP:
            return [], 0, 'input-too-large products'
        document = json.loads(raw.decode('utf-8'), parse_constant=_reject_json_constant)
    except (OSError, ValueError, RecursionError):
        return [], 0, 'input-unreadable products'

    rows = document.get('products') if isinstance(document, dict) else None
    if not isinstance(rows, list) or any(
        not isinstance(row, dict)
        or any(not isinstance(row.get(key), str) for key in REQUIRED)
        or ((row['status'] == 'active' or 'description' in row)
            and not isinstance(row.get('description'), str))
        or not isinstance(row.get('imageAlt', ''), str)
        for row in rows
    ):
        return [], 0, 'input-unreadable products'
    active = [row for row in rows if row['status'] == 'active']
    return active, len(rows) - len(active), None


def _findings(products, writer):
    counts = {field: Counter() for field in FIELDS}
    errors = {}  # Report each generic finding once, in first-seen order.
    descriptions = tuple(row['description'] for row in products)
    for i, row in enumerate(products):
        ctx = copy.Context(kind='food', category=row['category'], variant='', item=row['name'],
                           other_descriptions=descriptions[:i] + descriptions[i + 1:])
        for field in FIELDS:
            value = (row.get('imageAlt') or row['name']) if field == 'imageAlt' else row[field]
            try:
                reason = validate.field_problem(writer, field, value, (), ctx)
            except Exception:
                errors['check-error'] = None
                continue
            if reason is None:
                continue
            if not isinstance(reason, str) or REASON.fullmatch(reason) is None:
                errors['reason-invalid'] = None
                continue
            counts[field][reason] += 1

    yield from errors
    for field in FIELDS:
        for reason, count in sorted(counts[field].items()):
            yield f'field-refused {field} {reason} {count}'


def _report(findings):
    failed = False
    for finding in findings:
        print(f'FAIL {finding}')
        failed = True
    print(f'{"FAIL" if failed else "PASS"} {TOOL}')
    return int(failed)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    products, excluded, problem = _load_products()
    if problem is not None:
        return _report((problem,))
    try:
        writer = copy.Writer(npp.assets())
    except Exception:
        return _report(('assets-unreadable',))

    print('excluded', excluded)
    print('products', len(products))
    print('checked', len(products) * len(FIELDS))
    return _report(_findings(products, writer))


if __name__ == '__main__':
    sys.exit(main())
