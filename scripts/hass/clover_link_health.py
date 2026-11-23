#!/usr/bin/env python3
"""Check saved website–till links from offline copies, reporting counts only."""

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
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.clover import cache, mapper, reports


class Finding(Exception):
    """A fixed, public report reason (never an exception from an input reader)."""


def _mode(path):
    try:
        return path.lstat().st_mode
    except FileNotFoundError:
        return None


def _read_links(state):
    try:
        if not stat.S_ISDIR(_mode(state) or 0):
            raise Finding("unsafe-state")
        folder = state / "clover"
        if not cache._private_dir(folder, create=False):
            return {}
        path = folder / "links.json"
        try:
            st = path.lstat()
        except FileNotFoundError:
            return {}
        # Same admission checks as reports.read_inputs, with a separate content input.
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise Finding("unsafe-state")
        links = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(links, dict):
            raise Finding("unsafe-state")
        return links
    except (cache.CacheUnsafe, OSError, ValueError, RecursionError):
        raise Finding("unsafe-state") from None


def _read_products(path):
    try:
        document = json.loads(reports._read_regular(path))
        if isinstance(document, dict) and isinstance(document.get("products"), list):
            return document["products"]
    except (cache.CacheUnsafe, OSError, ValueError, RecursionError):
        pass
    raise Finding("unreadable products")


def _temp_candidates():
    return [value for key in ("TMPDIR", "TEMP", "TMP") if (value := os.environ.get(key))] + [
        "/tmp", "/var/tmp", "/usr/tmp", os.getcwd(),
    ]


def _temp_parent(input_dirs):
    roots = [os.path.realpath(path) for path in input_dirs]
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)
                and all(os.path.commonpath((parent, root)) != root for root in roots)):
            return parent
    raise Finding("temp-unavailable")


def _snapshot(store, *input_dirs):
    not_sqlite = f"not-sqlite {store.name}"
    try:
        mode = _mode(store)
    except OSError:
        raise Finding("unsafe-state") from None
    if mode is None:
        raise Finding("cache-absent")
    if not stat.S_ISREG(mode):
        raise Finding("unsafe-state")

    sources = [store]
    try:
        for suffix in ("-wal", "-journal"):
            sidecar = store.with_name(store.name + suffix)
            mode = _mode(sidecar)
            if mode is not None:
                if not stat.S_ISREG(mode):
                    raise Finding(not_sqlite)
                sources.append(sidecar)
    except OSError:
        raise Finding(not_sqlite) from None

    try:
        temporary = tempfile.TemporaryDirectory(dir=_temp_parent(input_dirs))
    except OSError:
        raise Finding("temp-unavailable") from None
    try:
        with temporary as directory:
            copy = Path(directory) / store.name
            for source in sources:
                shutil.copyfile(source, copy.with_name(source.name))
            with closing(sqlite3.connect(copy)) as db:
                db.execute("PRAGMA query_only=ON")
                return db.execute("SELECT id, name, sku, hidden FROM items").fetchall()
    except (OSError, sqlite3.Error):
        raise Finding(not_sqlite) from None


def _findings(counts):
    failed = False
    for reason, count in counts.items():
        if count:
            print(f"FAIL {reason} {count}")
            failed = True
    return failed


def _check(state, content):
    links = _read_links(state)
    records = _read_products(content / "products.json")
    if not links:
        print("links absent")
        return False

    print(f"links {len(links)}")
    products = {}
    for row in records:
        if isinstance(row, dict) and row.get("status") == "active" and isinstance(row.get("id"), str):
            name = row.get("name")
            products[row["id"]] = SimpleNamespace(id=row["id"], name=name if isinstance(name, str) else "")
    well_formed = {pid: link for pid, link in links.items()
                   if isinstance(link, dict) and isinstance(link.get("cloverId"), str)}
    active = {pid: link for pid, link in well_formed.items() if pid in products}
    failed = _findings({"malformed": len(links) - len(well_formed), "inactive-site": len(well_formed) - len(active)})

    rows = _snapshot(cache.path_for(state), state, content)
    items = [SimpleNamespace(id=item_id, name=name, sku=sku) for item_id, name, sku, _ in rows]
    hidden_ids = {item_id for item_id, _, _, hidden in rows if hidden == 1}
    matches = mapper.match(products.values(), items, active)
    resolved = [pair for pair in matches.pairs if pair.how in ("link", "sku")]
    by_sku = sum(pair.how == "sku" for pair in resolved)
    print(f"by-id {len(resolved) - by_sku}")
    print(f"by-sku {by_sku}")
    uses = Counter(link["cloverId"] for link in active.values())
    resolution_failed = _findings({
        "stale-id": by_sku,
        "broken": len(matches.broken_links),
        "shared": sum(count for count in uses.values() if count > 1),
        "hidden-target": sum(pair.item_id in hidden_ids for pair in resolved),
    })
    return failed or resolution_failed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path, help="state copy directory")
    parser.add_argument("--content", required=True, type=Path, help="directory containing products.json")
    args = parser.parse_args(argv)
    try:
        failed = _check(args.state, args.content)
    except Finding as error:
        print(f"FAIL {error}")
        failed = True
    print("FAIL clover_link_health" if failed else "PASS clover_link_health")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
