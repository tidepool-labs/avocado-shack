#!/usr/bin/env python3
"""Check catalog name bindings offline and report counts, never names."""

import argparse
import json
from pathlib import Path
import stat
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import claims, label_reader
from hass.npp import copy, missing, research


PRODUCTS = ROOT / 'hass/content/products.json'
MAKERS = ROOT / 'hass/content/makers.json'
INPUT_CAP = 2_000_000
TAG = 'maker_name_binding_check'


class InputError(Exception):
    """An input finding containing only a fixed reason and input label."""


def _reject_constant(_value):
    raise ValueError('not a JSON value')


def _load(path, label):
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise InputError(f'input-unsafe {label}')
        if info.st_size > INPUT_CAP:
            raise InputError(f'input-too-large {label}')
        with path.open('rb') as source:
            raw = source.read(INPUT_CAP + 1)
        if len(raw) > INPUT_CAP:
            raise InputError(f'input-too-large {label}')
        document = json.loads(raw.decode('utf-8'), parse_constant=_reject_constant)
        if isinstance(document, dict):
            return document.get(label)
    except (OSError, ValueError, RecursionError):
        raise InputError(f'input-unreadable {label}') from None
    raise InputError(f'input-unreadable {label}')


def _strings(row, required, optional=()):
    return (isinstance(row, dict)
            and all(isinstance(row.get(key), str) for key in required)
            and all(key not in row or isinstance(row[key], str) for key in optional))


def _inputs():
    products = _load(PRODUCTS, 'products')
    if not isinstance(products, list) or not all(
        _strings(row, ('id', 'name', 'status', 'brand')) for row in products
    ):
        raise InputError('input-unreadable products')
    makers = _load(MAKERS, 'makers')
    # JSON object keys are strings; values() preserves their file order.
    if not isinstance(makers, dict) or not all(
        _strings(row, ('name', 'place'), ('story', 'url')) for row in makers.values()
    ):
        raise InputError('input-unreadable makers')
    return products, makers


def _findings(makers, brands, active):
    checks = {
        'identity': lambda v: label_reader.identity_text('brand', v) == v,
        'plain': copy.plain,
        'idfield': research._identity_field,
        'owner': lambda v: missing._owner_maker(['made by ' + v], 'jam') == v,
    }
    for kind, values in (('maker', makers), ('brand', brands)):
        failed = dict.fromkeys(checks, 0)
        for value in values:
            for name, check in checks.items():
                if not check(value):
                    failed[name] += 1
        for name, count in failed.items():
            if count:
                yield f'name-binding {kind} {name} {count}'
    failed_names = sum(not copy.plain(row['name']) for row in active)
    if failed_names:
        yield f'product-name-plain {failed_names}'


def main(argv=None):
    argparse.ArgumentParser(prog=TAG, description=__doc__, add_help=False).parse_args(argv)
    try:
        products, makers = _inputs()
    except InputError as error:
        print(f'FAIL {error}')
        print(f'FAIL {TAG}')
        return 1

    active = [row for row in products if row['status'] == 'active']
    maker_names = [row['name'] for row in makers.values()]
    brands = sorted({row['brand'] for row in active if row['brand'] != claims.PLACEHOLDER})
    print(f'makers {len(maker_names)}')
    print(f'brands {len(brands)}')
    findings = []
    try:
        findings.extend(_findings(maker_names, brands, active))
    except Exception:
        # Check exceptions may contain catalog text; never report their details.
        findings.append('check-error')
    for finding in findings:
        print(f'FAIL {finding}')
    print(f'{"FAIL" if findings else "PASS"} {TAG}')
    return int(bool(findings))


if __name__ == '__main__':
    sys.exit(main())
