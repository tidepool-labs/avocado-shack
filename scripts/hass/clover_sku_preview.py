#!/usr/bin/env python3
"""Preview Clover SKUs for unlinked active products from offline copies."""

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

from hass.clover import cache, mapper, sku


class Finding(Exception):
    """A report reason that does not contain private input data."""


class PreviewParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse can echo unexpected arguments, including input paths.
        super().error("invalid arguments; see --help")


def _non_json_number(_value):
    raise ValueError


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_non_json_number)


def _read_links(state):
    folder = state / "clover"
    try:
        for directory in (state, folder):
            if not stat.S_ISDIR(directory.lstat().st_mode):
                raise ValueError
        path = folder / "links.json"
        try:
            info = path.lstat()
        except FileNotFoundError:
            return {}
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError
        links = _json(path)
        if not isinstance(links, dict):
            raise ValueError
        return links
    except (OSError, ValueError, RecursionError):
        raise Finding("unsafe-state") from None


def _read_products(content):
    path = content / "products.json"
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError
        document = _json(path)
        products = document.get("products") if isinstance(document, dict) else None
        if not isinstance(products, list):
            raise ValueError
        active = []
        for product in products:
            if not isinstance(product, dict):
                raise ValueError
            if product.get("status") == "active":
                pid = product.get("id")
                # The one catalog field reported verbatim must be a single ID token.
                if (not isinstance(pid, str) or not pid or not pid.isascii()
                        or not all(c.isalnum() or c in "-_" for c in pid)):
                    raise ValueError
                active.append(product)
        return active
    except (OSError, ValueError, RecursionError):
        raise Finding("unreadable products") from None


def _temp_candidates():
    return [value for key in ("TMPDIR", "TEMP", "TMP") if (value := os.environ.get(key))] + [
        "/tmp", "/var/tmp", "/usr/tmp", os.getcwd(),
    ]


def _temp_parent(input_dirs):
    inputs = [os.path.realpath(path) for path in input_dirs]
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)
                and all(os.path.commonpath((parent, path)) != path for path in inputs)):
            return parent
    raise Finding("temp-unavailable")


def _snapshot_items(store, input_dirs):
    reason = f"not-sqlite {store.name}"
    try:
        if not stat.S_ISREG(store.lstat().st_mode):
            raise Finding(reason)
        sources = [store]
        for suffix in ("-wal", "-journal"):
            sidecar = store.with_name(store.name + suffix)
            try:
                info = sidecar.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(info.st_mode):
                raise Finding(reason)
            sources.append(sidecar)
    except (OSError, ValueError):
        raise Finding(reason) from None

    try:
        temporary = tempfile.TemporaryDirectory(dir=_temp_parent(input_dirs))
    except (OSError, ValueError):
        raise Finding("temp-unavailable") from None
    try:
        with temporary as dirname:
            folder = Path(dirname)
            for source in sources:
                shutil.copyfile(source, folder / source.name)
            with closing(sqlite3.connect(folder / store.name)) as db:
                db.execute("PRAGMA query_only=ON")
                rows = db.execute("SELECT * FROM items")
                # cache._item expects positional values in COLUMNS order.
                found = {column[0]: i for i, column in enumerate(rows.description)}
                positions = [found[name] for name in cache.COLUMNS]
                items = [cache._item(tuple(row[i] for i in positions)) for row in rows]
                if any(not isinstance(field, str) for item in items
                       for field in (item.id, item.name, item.sku, item.code)):
                    raise ValueError
                return items
    except (sqlite3.Error, OSError, KeyError, ValueError, ArithmeticError, TypeError, RecursionError):
        raise Finding(reason) from None


def _report(products, links, items):
    proposed = Counter()
    unlinked = failures = 0
    for product in products:
        pid = product["id"]
        if pid in links:
            continue
        unlinked += 1
        name, category = product.get("name"), product.get("category")
        if category not in mapper.CATEGORIES:
            print(f"note category-unsupported {pid}")
            continue
        try:
            candidate = sku.generate_sku(name if isinstance(name, str) else "", category, items)
        except sku.DuplicateItem:
            print(f"note till-twin {pid}")
        except sku.SkuExhausted:
            print(f"FAIL sku-exhausted {pid}")
            failures += 1
        except mapper.MapError:
            print(f"note name-refused {pid}")
        else:
            print(f"sku {pid} {candidate}")
            proposed[candidate] += 1
    print(f"unlinked {unlinked}")
    print(f"previewed {sum(proposed.values())}")
    print(f"note same-preview-sku {sum(count >= 2 for count in proposed.values())}")
    return bool(failures)


def main(argv=None):
    parser = PreviewParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--state", required=True, type=Path, help="copied Hass state directory")
    parser.add_argument("--content", required=True, type=Path, help="directory with copied products.json")
    args = parser.parse_args(argv)
    folder = args.state / "clover"
    try:
        links = _read_links(args.state)
        products = _read_products(args.content)
        items = _snapshot_items(folder / cache.FILENAME, (args.state, folder, args.content))
        failed = _report(products, links, items)
    except Finding as finding:
        print(f"FAIL {finding}")
        failed = True
    print(f"{'FAIL' if failed else 'PASS'} clover_sku_preview")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
