#!/usr/bin/env python3
"""Compare website prices, units and register visibility against a saved Clover cache."""

import argparse
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
from hass.content_model import ID_RE, SELLING_PRICE_RE


LABEL = "clover_price_parity"


class InputError(ValueError):
    """An input refusal with a fixed, printable reason."""


def _read_json(path, *, private=False):
    # Reject symlinks and special files, without blocking on a FIFO.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or (private and not _private(st)):
            raise ValueError("unsafe JSON file")
        with os.fdopen(fd, encoding="utf-8", closefd=False) as source:
            return json.load(source)
    finally:
        os.close(fd)


def _private(st):
    return st.st_uid == os.getuid() and not st.st_mode & 0o077


def _links(state, clover):
    try:
        if not stat.S_ISDIR(state.lstat().st_mode):
            raise ValueError("unsafe state directory")
        folder = clover.lstat()
        if not stat.S_ISDIR(folder.st_mode) or not _private(folder):
            raise ValueError("unsafe Clover directory")
        try:
            links = _read_json(clover / "links.json", private=True)
        except FileNotFoundError:
            return {}
        if not isinstance(links, dict) or any(
            not isinstance(link, dict) or not isinstance(link.get("cloverId"), str)
            for link in links.values()
        ):
            raise ValueError("invalid links")
        return links
    except (OSError, ValueError, RecursionError):
        raise InputError("unsafe-state") from None


def _site_prices(content, links):
    try:
        doc = _read_json(content / "products.json")
        if not isinstance(doc, dict) or not isinstance(doc.get("products"), list):
            raise ValueError("invalid products")
        prices = {}
        for row in doc["products"]:
            if not isinstance(row, dict):
                raise ValueError("invalid product")
            if row.get("status") != "active":
                continue
            pid = row.get("id")
            if not isinstance(pid, str) or not ID_RE.fullmatch(pid):
                raise ValueError("invalid product id")
            if pid not in links:
                continue
            if "sellingPrice" not in row:
                prices[pid] = None
                continue
            value = row["sellingPrice"]
            if not isinstance(value, str) or not SELLING_PRICE_RE.fullmatch(value):
                raise ValueError("invalid selling price")
            amount, _, suffix = value.partition(" ")
            prices[pid] = (int(amount.replace(".", "")), suffix == "per lb")
        return prices
    except (OSError, ValueError, RecursionError):
        raise InputError("unreadable products") from None


def _temp_candidates():
    configured = (os.environ.get(key) for key in ("TMPDIR", "TEMP", "TMP"))
    return (*filter(None, configured), "/tmp", "/var/tmp", "/usr/tmp", os.getcwd())


def _temp_parent(input_dirs):
    inputs = [os.path.realpath(path) for path in input_dirs]
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)
                and not any(os.path.commonpath((parent, root)) == root for root in inputs)):
            return parent
    raise InputError("temp-unavailable")


def _snapshot_items(store, input_dirs):
    """Open only a disposable copy; SQLite can recover WAL or journal there."""
    reason = f"not-sqlite {store.name}"
    try:
        sources = [store]
        if not stat.S_ISREG(store.lstat().st_mode):
            raise InputError(reason)
        for suffix in ("-wal", "-journal"):
            sidecar = store.with_name(store.name + suffix)
            try:
                mode = sidecar.lstat().st_mode
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(mode):
                raise InputError(reason)
            sources.append(sidecar)
    except OSError:
        raise InputError(reason) from None

    try:
        temporary = tempfile.TemporaryDirectory(dir=_temp_parent(input_dirs))
    except OSError:
        raise InputError("temp-unavailable") from None
    try:
        with temporary as folder:
            for source in sources:
                shutil.copyfile(source, Path(folder) / source.name)
            with closing(sqlite3.connect(Path(folder) / store.name)) as conn:
                conn.execute("PRAGMA query_only=ON")
                return {row[0]: row[1:] for row in conn.execute(
                    "SELECT id, price_cents, price_type, unit_name, hidden, sku FROM items"
                )}
    except (OSError, sqlite3.Error):
        raise InputError(reason) from None


def _report(prices, links, items):
    findings = []
    checked = absent = 0
    for pid, site in sorted(prices.items()):
        till = items.get(links[pid]["cloverId"])
        if till is None:
            absent += 1
            continue
        checked += 1
        cents, kind, unit, hidden, sku = till
        if site is not None:
            site_cents, per_lb = site
            if cents is None:
                findings.append(f"till-no-price {pid}")
            elif cents != site_cents:
                findings.append(f"price-differs {pid}")
            if per_lb:
                unit_ok = (kind == "PER_UNIT" and isinstance(unit, str)
                           and unit.casefold() in {"lb", "lbs", "pound"})
            else:
                unit_ok = kind == "FIXED"
            if not unit_ok:
                findings.append(f"unit-differs {pid}")
        if hidden != 0:
            findings.append(f"till-hidden {pid}")
        if not sku:
            findings.append(f"till-no-sku {pid}")
    print(f"linked {len(prices)}")
    print(f"checked {checked}")
    print(f"note no-site-price {sum(site is None for site in prices.values())}")
    print(f"note till-absent {absent}")
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path, help="copied state directory")
    parser.add_argument("--content", required=True, type=Path, help="directory containing products.json")
    args = parser.parse_args(argv)
    clover = args.state / "clover"
    try:
        links = _links(args.state, clover)
        prices = _site_prices(args.content, links)
        items = _snapshot_items(clover / "cache.sqlite3", (args.state, clover, args.content))
        findings = _report(prices, links, items)
    except InputError as exc:
        findings = [str(exc)]
    for finding in findings:
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} {LABEL}")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
