#!/usr/bin/env python3
"""Preview NPP listing length warnings using the checked-in catalog and limits."""

import argparse
import json
import math
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import npp
from hass.npp import copy, validate

PRODUCTS = ROOT / 'hass/content/products.json'
MAKERS = ROOT / 'hass/content/makers.json'
INPUT_CAP = 2_000_000
FIELD_NAME = re.compile(r'[a-z][a-z_]{0,40}')


class InputFailure(Exception):
    """A fixed diagnostic safe to print without including input data."""


def string_fields(row, required, optional):
    return (isinstance(row, dict)
            and all(isinstance(row.get(key), str) for key in required)
            and all(key not in row or isinstance(row[key], str) for key in optional))


def valid_products(rows):
    return isinstance(rows, list) and all(
        string_fields(row, ('id', 'name', 'status'),
                      ('description', 'imageAlt', 'displayBrand', 'brand', 'supplier'))
        # The catalog uses null as well as omission for products with no maker.
        and (row.get('producerKey') is None or isinstance(row['producerKey'], str))
        for row in rows
    )


def valid_makers(rows):
    return isinstance(rows, dict) and all(
        isinstance(key, str) and string_fields(row, ('name', 'place'), ('story', 'url'))
        for key, row in rows.items()
    )


def reject_constant(_token):
    raise ValueError('not a JSON constant')


def read_input(path, name, valid):
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise InputFailure(f'input-unsafe {name}')
        if info.st_size > INPUT_CAP:
            raise InputFailure(f'input-too-large {name}')
        with path.open('rb') as source:
            raw = source.read(INPUT_CAP + 1)
        if len(raw) > INPUT_CAP:
            raise InputFailure(f'input-too-large {name}')
        rows = json.loads(raw.decode('utf-8'), parse_constant=reject_constant)[name]
        if not valid(rows):
            raise ValueError('invalid shape')
        return rows
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        raise InputFailure(f'input-unreadable {name}') from None


def measured(product, maker):
    supplier = product.get('supplier')
    place = maker.get('place', '')
    origin = f'From {supplier}' if supplier else f'Based in {place}' if place else validate.ORIGIN_UNKNOWN
    return {
        'name': product['name'],
        'description': product.get('description', ''),
        'brand': product.get('displayBrand') or product.get('brand') or '',
        'origin': origin,
        'image_alt': product.get('imageAlt') or product['name'],
        # S7 measures the newly written story, not the existing maker's story.
        'maker_story': '',
        'maker_name': maker.get('name', ''),
        'maker_place': place,
        'maker_url': maker.get('url', ''),
    }


def exceeds(value, chars, words):
    return len(value) > chars or len(value.split()) > words


def number(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))


def preview(limits, cards):
    print(f'products {len(cards)}')
    if not isinstance(limits, dict):
        return ['check-error']
    findings = []
    thresholds = {}
    for field, row in limits.items():
        if not isinstance(field, str) or FIELD_NAME.fullmatch(field) is None:
            findings.append('field-invalid')
            continue
        try:
            chars, words = row['chars']['p90'], row['words']['p90']
        except (KeyError, TypeError):
            findings.append('check-error')
            continue
        if not (number(chars) and number(words)):
            findings.append('check-error')
            continue
        thresholds[field] = chars, words
        count = sum(exceeds(card.get(field, ''), chars, words) for card in cards)
        print(f'warn {field} {count}')
    for field, value in (('origin', validate.ORIGIN_UNKNOWN), ('brand', 'From the market')):
        if field not in limits:
            findings.append('check-error')
        elif field in thresholds and exceeds(value, *thresholds[field]):
            findings.append(f'fixed-line-over-p90 {field}')
    return findings


def check():
    try:
        products = read_input(PRODUCTS, 'products', valid_products)
        makers = read_input(MAKERS, 'makers', valid_makers)
    except InputFailure as exc:
        return [str(exc)]
    try:
        limits = copy.Writer(npp.assets()).limits['fields']
    except Exception:
        return ['assets-unreadable']
    cards = [measured(product, makers.get(product.get('producerKey'), {}))
             for product in products if product['status'] == 'active']
    return preview(limits, cards)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    # Even '--' and '--help' are usage errors for this no-argument tool.
    args = sys.argv[1:] if argv is None else argv
    if args:
        parser.error('no arguments accepted')
    findings = check()
    for reason in findings:
        print(f'FAIL {reason}')
    print(f'{"FAIL" if findings else "PASS"} npp_p90_warning_preview')
    return int(bool(findings))


if __name__ == '__main__':
    sys.exit(main())
