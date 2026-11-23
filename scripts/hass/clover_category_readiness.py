#!/usr/bin/env python3
"""Report Clover category coverage from offline copies of the map, cache and products."""

import argparse
from collections import Counter
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import content_model
from hass.clover import mapper


class Finding(Exception):
    """A report reason that does not expose input contents or full paths."""


def _reject_constant(_value):
    raise ValueError("not a JSON constant")


def _read_json(path, reason):
    try:
        if stat.S_ISREG(path.lstat().st_mode):
            return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (OSError, ValueError, RecursionError):
        pass
    raise Finding(reason)


def _category_map(path):
    reason = "bad-category-map"
    mapping = _read_json(path, reason)
    if not isinstance(mapping, dict) or not all(
        key in content_model.CATEGORIES and isinstance(value, str) and 1 <= len(value) <= 100
        for key, value in mapping.items()
    ):
        raise Finding(reason)
    return mapping


def _product_counts(path):
    reason = "unreadable products"
    document = _read_json(path, reason)
    products = document.get("products") if isinstance(document, dict) else None
    if not isinstance(products, list):
        raise Finding(reason)
    return Counter(
        product["category"] for product in products
        if isinstance(product, dict) and product.get("status") == "active"
        and product.get("category") in content_model.CATEGORIES
    )


def _temp_candidates():
    return [value for key in ("TMPDIR", "TEMP", "TMP") if (value := os.environ.get(key))] + [
        "/tmp", "/var/tmp", "/usr/tmp", os.getcwd(),
    ]


def _temp_parent(input_dirs):
    excluded = [os.path.realpath(directory) for directory in input_dirs]
    for candidate in _temp_candidates():
        path = os.path.realpath(candidate)
        if os.path.isdir(path) and os.access(path, os.W_OK | os.X_OK) and not any(
            os.path.commonpath((path, directory)) == directory for directory in excluded
        ):
            return path
    raise Finding("temp-unavailable")


def _till_counts(store, input_dirs):
    reason = f"not-sqlite {store.name}"
    sources = [store]
    try:
        if not stat.S_ISREG(store.lstat().st_mode):
            raise Finding(reason)
        for suffix in ("-wal", "-journal"):
            sidecar = store.with_name(store.name + suffix)
            try:
                mode = sidecar.lstat().st_mode
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(mode):
                raise Finding(reason)
            sources.append(sidecar)
    except (OSError, ValueError) as error:
        raise Finding(reason) from error

    parent = _temp_parent(input_dirs)
    try:
        temporary = tempfile.TemporaryDirectory(dir=parent)
    except OSError as error:
        raise Finding("temp-unavailable") from error

    counts = Counter()
    try:
        # SQLite can recover the journal or create SHM here, never by the inputs.
        with temporary as directory:
            for source in sources:
                shutil.copyfile(source, Path(directory) / source.name)
            with closing(sqlite3.connect(Path(directory) / store.name)) as db:
                db.execute("PRAGMA query_only=ON")
                for categories, hidden in db.execute("SELECT categories, hidden FROM items"):
                    if hidden:
                        continue
                    try:
                        names = json.loads(categories)
                    except (TypeError, ValueError, RecursionError):
                        continue
                    if isinstance(names, list):
                        # Count each item at most once per normalized category.
                        counts.update({mapper.norm_name(name) for name in names if isinstance(name, str)})
    except (sqlite3.Error, OSError) as error:
        raise Finding(reason) from error
    return counts


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's default diagnostics can echo paths supplied as stray arguments.
        super().error("invalid arguments (see --help)")


def main(argv=None):
    parser = PrivateArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--category-map", required=True, type=Path, metavar="FILE")
    parser.add_argument("--cache", required=True, type=Path, metavar="FILE")
    parser.add_argument("--content", required=True, type=Path, metavar="DIR")
    args = parser.parse_args(argv)

    failed = False

    def report(reason):
        nonlocal failed
        print(f"FAIL {reason}")
        failed = True

    mapping = products = till = None
    try:
        mapping = _category_map(args.category_map)
    except Finding as error:
        report(error)
    try:
        products = _product_counts(args.content / "products.json")
    except Finding as error:
        report(error)
    try:
        till = _till_counts(args.cache, (args.category_map.parent, args.cache.parent, args.content))
    except Finding as error:
        report(error)

    if products is not None:
        for word in content_model.CATEGORIES:
            if not products[word]:
                continue
            print(f"shelf {word} products {products[word]}")
            if mapping is not None:
                mapped = word in mapping
                print(f"shelf {word} mapped {'yes' if mapped else 'no'}")
                if not mapped:
                    report(f"unmapped {word}")
                elif till is not None:
                    print(f"shelf {word} till-items {till[mapper.norm_name(mapping[word])]}")
            if word not in mapper.CATEGORIES:
                print(f"note till-engine-unsupported {word}")

    print(f"{'FAIL' if failed else 'PASS'} clover_category_readiness")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
