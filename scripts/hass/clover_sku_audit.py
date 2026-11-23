#!/usr/bin/env python3
"""Report Clover SKU counts and conflicts from an offline cache copy."""

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.clover.sku import is_hass_sku


class AuditError(Exception):
    """A fixed, non-sensitive failure reason."""


class AuditParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse can echo unrecognized arguments, including private paths.
        super().error("invalid arguments; see --help")


def _temp_candidates():
    return (
        *(os.environ[key] for key in ("TMPDIR", "TEMP", "TMP") if os.environ.get(key)),
        "/tmp", "/var/tmp", "/usr/tmp", os.getcwd(),
    )


def _temp_parent(state):
    # The Clover directory is already inside this excluded tree.
    source = os.path.realpath(state)
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.commonpath((source, parent)) != source
                and os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)):
            return parent
    raise AuditError("temp-unavailable")


def _mode(path, reason):
    try:
        return path.lstat().st_mode
    except FileNotFoundError:
        return None
    except OSError:
        raise AuditError(reason) from None


def _snapshot_rows(state):
    """Copy a stable input store and sidecars before opening SQLite."""
    clover = state / "clover"
    store = clover / "cache.sqlite3"
    not_sqlite = f"not-sqlite {store.name}"
    if not stat.S_ISDIR(_mode(state, "unsafe-state") or 0):
        raise AuditError("unsafe-state")
    mode = _mode(clover, "unsafe-state")
    if mode is None:
        return None
    if not stat.S_ISDIR(mode):
        raise AuditError("unsafe-state")
    mode = _mode(store, "unsafe-state")
    if mode is None:
        return None
    if not stat.S_ISREG(mode):
        raise AuditError("unsafe-state")

    sources = [store]
    for suffix in ("-wal", "-journal"):
        sidecar = store.with_name(store.name + suffix)
        mode = _mode(sidecar, not_sqlite)
        if mode is not None:
            if not stat.S_ISREG(mode):
                raise AuditError(not_sqlite)
            sources.append(sidecar)

    try:
        temporary = tempfile.TemporaryDirectory(dir=_temp_parent(state))
    except OSError:
        raise AuditError("temp-unavailable") from None
    with temporary as directory:
        copy = Path(directory) / store.name
        try:
            for source in sources:
                shutil.copyfile(source, copy.with_name(source.name))
            with closing(sqlite3.connect(copy)) as db:
                db.execute("PRAGMA query_only=ON")
                rows = db.execute("SELECT id, sku, code, hidden FROM items").fetchall()
            if any(value is not None and not isinstance(value, str)
                   for _, sku, code, _ in rows for value in (sku, code)):
                raise sqlite3.DataError
            return rows
        except (OSError, sqlite3.Error):
            raise AuditError(not_sqlite) from None


def _report(rows):
    barcodes = defaultdict(set)
    for item_id, _, code, _ in rows:
        if code:
            barcodes[code.casefold()].add(item_id)

    skus = Counter()
    hass_count = hidden_count = barcode_count = malformed_count = 0
    for item_id, sku, _, hidden in rows:
        if not sku:
            continue
        key = sku.casefold()
        skus[key] += 1
        hidden_count += bool(hidden)
        valid = is_hass_sku(sku)
        hass_count += valid
        malformed_count += key.startswith("as-") and not valid
        owners = barcodes.get(key)
        barcode_count += bool(owners and (len(owners) > 1 or item_id not in owners))

    print(f"items {len(rows)}")
    print(f"with-sku {sum(skus.values())}")
    print(f"hass-sku {hass_count}")
    print(f"hidden-with-sku {hidden_count}")
    findings = (
        ("duplicate-sku", sum(count > 1 for count in skus.values())),
        ("sku-is-barcode", barcode_count),
        ("as-malformed", malformed_count),
    )
    for reason, count in findings:
        if count:
            print(f"FAIL {reason} {count}")
    return any(count for _, count in findings)


def main(argv=None):
    parser = AuditParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path, metavar="DIR",
                        help="directory containing the offline Clover cache")
    args = parser.parse_args(argv)
    try:
        rows = _snapshot_rows(args.state)
    except AuditError as exc:
        print(f"FAIL {exc}")
        failed = True
    else:
        if rows is None:
            print("cache absent")
            failed = False
        else:
            failed = _report(rows)
    print("FAIL clover_sku_audit" if failed else "PASS clover_sku_audit")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
