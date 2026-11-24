#!/usr/bin/env python3
"""Replay the NPP duplicate rule against spelling variants and report counts only."""

import argparse
import json
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass.npp import missing

PRODUCTS = ROOT / "hass/content/products.json"
MAKERS = ROOT / "hass/content/makers.json"
INPUT_CAP = 2_000_000
KINDS = ("exact", "upper", "double-space", "plural", "the", "no-apostrophe")


class InputError(ValueError):
    """A fixed diagnostic that never contains input content or paths."""


def _reject_constant(_token):
    raise ValueError("non-JSON constant")


def _load(path, name, valid):
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise InputError(f"input-unsafe {name}")
        if metadata.st_size > INPUT_CAP:
            raise InputError(f"input-too-large {name}")
        with path.open("rb") as source:
            raw = source.read(INPUT_CAP + 1)
        if len(raw) > INPUT_CAP:
            raise InputError(f"input-too-large {name}")
        document = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
        if not isinstance(document, dict) or name not in document:
            raise InputError(f"input-unreadable {name}")
        records = document[name]
        if not valid(records):
            raise InputError(f"input-unreadable {name}")
        return records
    except InputError:
        raise
    except (OSError, ValueError, RecursionError):
        raise InputError(f"input-unreadable {name}") from None


def _has_strings(record, fields):
    return isinstance(record, dict) and all(isinstance(record.get(key), str) for key in fields)


def _valid_products(records):
    return isinstance(records, list) and all(
        _has_strings(record, ("id", "name", "status")) for record in records
    )


def _valid_makers(records):
    # JSON object keys are always strings.
    return isinstance(records, dict) and all(
        _has_strings(record, ("name", "place"))
        and all(key not in record or isinstance(record[key], str) for key in ("story", "url"))
        for record in records.values()
    )


def _variants(name):
    yield "exact", name
    yield "upper", name.upper()
    if " " in name:
        yield "double-space", name.replace(" ", "  ", 1)
    yield "plural", name[:-1] if name.endswith("s") else name + "s"
    yield "the", "the " + name
    without_apostrophes = name.replace("'", "").replace("’", "")
    if without_apostrophes != name:
        yield "no-apostrophe", without_apostrophes


def _finish(findings):
    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} npp_duplicate_variants")
    return 1 if findings else 0


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    try:
        products = _load(PRODUCTS, "products", _valid_products)
        makers = _load(MAKERS, "makers", _valid_makers)
    except InputError as error:
        return _finish([str(error)])

    tried = dict.fromkeys(KINDS, 0)
    caught = dict.fromkeys(KINDS, 0)
    for product in products:
        if product["status"] != "active":
            continue
        for kind, variant in _variants(product["name"]):
            tried[kind] += 1
            try:
                hit = "catalog" in missing._duplicates(variant, products, makers, None)
            except Exception:
                return _finish(["check-error"])
            if hit:
                caught[kind] += 1

    findings = []
    for kind in KINDS:
        print(f"tried {kind} {tried[kind]}")
        print(f"caught {kind} {caught[kind]}")
        if tried[kind] != caught[kind]:
            findings.append(f"variant-missed {kind} {tried[kind] - caught[kind]}")
    return _finish(findings)


if __name__ == "__main__":
    sys.exit(main())
