#!/usr/bin/env python3
"""Report aggregate count readiness from offline copies of site and Clover data."""

import argparse
from collections import Counter
from contextlib import closing
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.clover import cache, mapper, reports


class Finding(Exception):
    """A fixed report reason that contains no private input values."""


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's diagnostic can echo an unrecognized path or option value.
        super().error("expected --state DIR and --content DIR (see --help)")


def _read_links(state):
    folder = state / cache.DIRNAME
    try:
        if not stat.S_ISDIR(state.lstat().st_mode):
            raise cache.CacheUnsafe("state")
        if not cache._private_dir(folder, create=False):
            return {}
        # Match reports.read_inputs without imposing its worktree-relative products path.
        path = folder / "links.json"
        try:
            st = path.lstat()
        except FileNotFoundError:
            return {}
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise cache.CacheUnsafe("links")
        links = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(links, dict):
            raise ValueError("links")
        return links
    except (cache.CacheUnsafe, OSError, ValueError, RecursionError):
        raise Finding("unsafe-state") from None


def _not_json(_token):
    raise ValueError("non-JSON constant")


def _read_products(content):
    try:
        document = json.loads(reports._read_regular(content / "products.json"), parse_constant=_not_json)
        products = document.get("products") if isinstance(document, dict) else None
        if not isinstance(products, list):
            raise ValueError("products")
    except (cache.CacheUnsafe, OSError, ValueError, RecursionError):
        raise Finding("unreadable products") from None
    return [SimpleNamespace(id=p["id"], name=p["name"]) for p in products
            if isinstance(p, dict) and p.get("status") == "active"
            and isinstance(p.get("id"), str) and isinstance(p.get("name"), str)]


def _temp_candidates():
    for key in ("TMPDIR", "TEMP", "TMP"):
        value = os.environ.get(key)
        if value:
            yield value
    yield from ("/tmp", "/var/tmp", "/usr/tmp")
    yield os.getcwd()


def _temp_parent(input_dirs):
    roots = [os.path.realpath(path) for path in input_dirs]
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)
                and all(os.path.commonpath((root, parent)) != root for root in roots)):
            return parent
    raise Finding("temp-unavailable")


def _snapshot(store, input_dirs):
    """Read a private copy (including recovery sidecars), never open the input in SQLite."""
    try:
        mode = store.lstat().st_mode
    except FileNotFoundError:
        return None
    except OSError:
        raise Finding("unsafe-state") from None
    if not stat.S_ISREG(mode):
        raise Finding("unsafe-state")

    sources = [store]
    reason = f"not-sqlite {store.name}"
    try:
        for suffix in ("-wal", "-journal"):
            sidecar = store.with_name(store.name + suffix)
            try:
                mode = sidecar.lstat().st_mode
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(mode):
                raise Finding(reason)
            sources.append(sidecar)
    except OSError:
        raise Finding(reason) from None

    parent = _temp_parent(input_dirs)
    try:
        temporary = tempfile.TemporaryDirectory(dir=parent)
    except OSError:
        raise Finding("temp-unavailable") from None
    try:
        with temporary as directory:
            root = Path(directory)
            for source in sources:
                shutil.copyfile(source, root / source.name)
            with closing(sqlite3.connect(root / store.name)) as db:
                db.execute("PRAGMA query_only=ON")
                return db.execute("SELECT id, name, sku, hidden, stock FROM items").fetchall()
    except (OSError, sqlite3.Error):
        raise Finding(reason) from None


def _report(products, rows, links):
    items = [SimpleNamespace(id=item_id, name=name, sku=sku) for item_id, name, sku, _, _ in rows]
    counts = {item_id: (hidden, stock) for item_id, _, _, hidden, stock in rows}
    pairs = mapper.match(products, items, links).pairs
    methods = Counter(pair.how for pair in pairs)
    no_count = hidden_with_count = negative = bad_count = 0
    for pair in pairs:
        hidden, stock = counts[pair.item_id]
        if stock is None:
            no_count += 1
            continue
        hidden_with_count += bool(hidden)  # Presence of a stored value, even if invalid.
        try:
            value = Decimal(stock)
        except (InvalidOperation, TypeError):
            bad_count += 1
        else:
            if not value.is_finite():
                bad_count += 1
            elif value < 0:
                negative += 1

    print(f"pairs {len(pairs)}")
    for method in ("link", "sku", "name"):
        print(f"pairs-by {method} {methods[method]}")
    print(f"no-count {no_count}")
    print(f"hidden-with-count {hidden_with_count}")
    if negative:
        print(f"FAIL negative {negative}")
    if bad_count:
        print(f"FAIL bad-count {bad_count}")
    return bool(negative or bad_count)


def main(argv=None):
    parser = PrivateParser(prog="clover_count_readiness.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--state", type=Path, metavar="DIR", required=True)
    parser.add_argument("--content", type=Path, metavar="DIR", required=True)
    args = parser.parse_args(argv)
    failed = False
    try:
        raw_links = _read_links(args.state)
        products = _read_products(args.content)
        rows = _snapshot(args.state / cache.DIRNAME / cache.FILENAME, (args.state, args.content))
        links = {pid: link for pid, link in raw_links.items()
                 if isinstance(link, dict) and isinstance(link.get("cloverId"), str)}
        if len(links) != len(raw_links):
            print(f"note malformed-links {len(raw_links) - len(links)}")
        if rows is None:
            print("cache absent")
        else:
            failed = _report(products, rows, links)
    except Finding as error:
        print(f"FAIL {error}")
        failed = True
    print(f"{'FAIL' if failed else 'PASS'} clover_count_readiness")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
