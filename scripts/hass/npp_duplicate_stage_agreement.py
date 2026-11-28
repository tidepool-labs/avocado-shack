#!/usr/bin/env python3
"""Compare NPP and editor duplicate decisions on the checked-in catalog."""

import argparse
from collections import Counter
import json
from pathlib import Path
import stat
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass.npp import missing
from hass.ops import catalog


PRODUCTS = ROOT / "hass/content/products.json"
MAKERS = ROOT / "hass/content/makers.json"
INPUT_CAP = 2_000_000
REPORT = "npp_duplicate_stage_agreement"
VARIANTS = ("exact", "upper", "double-space")
STATUSES = {"active", "held", "hidden"}


class InputFailure(Exception):
    """A fixed report reason, without paths or input text."""


def _strings(record, *fields):
    return isinstance(record, dict) and all(isinstance(record.get(key), str) for key in fields)


def _products_shape(data):
    return isinstance(data, list) and all(_strings(row, "id", "name", "status", "brand") for row in data)


def _makers_shape(data):
    return isinstance(data, dict) and all(
        isinstance(key, str) and _strings(row, "name", "place")
        and all(field not in row or isinstance(row[field], str) for field in ("story", "url"))
        for key, row in data.items()
    )


def _invalid_constant(_token):
    raise ValueError("not JSON")


def _read(path, name, valid_shape):
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise InputFailure(f"input-unsafe {name}")
        if metadata.st_size > INPUT_CAP:
            raise InputFailure(f"input-too-large {name}")
        with path.open("rb") as source:
            raw = source.read(INPUT_CAP + 1)
        if len(raw) > INPUT_CAP:
            raise InputFailure(f"input-too-large {name}")
        document = json.loads(raw.decode("utf-8"), parse_constant=_invalid_constant)
        if not isinstance(document, dict) or name not in document or not valid_shape(document[name]):
            raise ValueError("wrong shape")
        return document[name]
    except (OSError, ValueError, RecursionError):
        raise InputFailure(f"input-unreadable {name}") from None


def _variants(name):
    yield "exact", name
    yield "upper", name.upper()
    if " " in name:
        yield "double-space", name.replace(" ", "  ", 1)


def _compare(records, makers):
    agree = Counter()
    disagree = {variant: Counter() for variant in VARIANTS}
    content = SimpleNamespace(products=records)
    for record in records:
        status = record["status"]
        if status not in STATUSES:
            status = "other"
        for variant, name in _variants(record["name"]):
            s3 = "catalog" in missing._duplicates(name, records, makers, None)
            editor = catalog._twin(content, name, record["brand"]) is not None
            if s3 == editor:
                agree[variant] += 1
            else:
                disagree[variant][status, s3, editor] += 1
    return agree, disagree


def _fail(reason):
    print(f"FAIL {reason}")
    print(f"FAIL {REPORT}")
    return 1


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    try:
        records = _read(PRODUCTS, "products", _products_shape)
        makers = _read(MAKERS, "makers", _makers_shape)
    except InputFailure as error:
        return _fail(error)

    try:
        agree, disagree = _compare(records, makers)
    except Exception:
        # The real-stage error could contain product text. Report no details.
        return _fail("check-error")

    print(f"records {len(records)}")
    for variant in VARIANTS:
        print(f"agree {variant} {agree[variant]}")
    for variant in VARIANTS:
        for (status, s3, editor), count in sorted(disagree[variant].items()):
            print(f"FAIL stage-disagree {status} {variant} "
                  f"s3-{'yes' if s3 else 'no'} editor-{'yes' if editor else 'no'} {count}")
    failed = any(disagree.values())
    print(f"{'FAIL' if failed else 'PASS'} {REPORT}")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
