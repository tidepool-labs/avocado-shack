#!/usr/bin/env python3
"""Check release primary keys on one stable, offline SQLite copy (never a live store)."""

import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys

if __package__:
    from .install_store_schema import _open_snapshot, private_directory
else:
    from install_store_schema import _open_snapshot, private_directory


def primary_keys(db):
    keys = {}
    for (table,) in db.execute("SELECT name FROM main.sqlite_master WHERE type = 'table'"):
        quoted = table.replace('"', '""')
        # table_info lists columns in declaration order; pk is the position within the key.
        columns = sorted((row[5], row[1]) for row in db.execute(f'PRAGMA main.table_info("{quoted}")') if row[5])
        if columns:
            keys[table] = tuple(name for _, name in columns)
    return keys


def reference_keys(store, input_dirs):
    # Use the same constructors as install_store_schema, but collect PKs before closing.
    with private_directory(input_dirs, "hass-keys-") as directory:
        root = Path(directory)
        if store == "inbox":
            from hass.inbox import Inbox

            reference = Inbox(root, start_at="2026-01-01T00:00:00+00:00")
        else:
            from hass.relay import RelayStore

            reference = RelayStore(root)
        with closing(reference.db) as db:
            return primary_keys(db)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", choices=("inbox", "relay"), required=True)
    parser.add_argument("copy", type=Path, help="stable SQLite copy with any matching sidecars")
    args = parser.parse_args(argv)
    input_dirs = {Path(os.path.realpath(args.copy.parent))}
    mismatches = None
    try:
        expected = reference_keys(args.store, input_dirs)
    except Exception:
        expected = {}
    if expected:
        try:
            with _open_snapshot(args.copy, input_dirs) as db:
                actual = primary_keys(db)
            mismatches = sum(actual.get(table) != key for table, key in expected.items())
        except (OSError, ValueError, sqlite3.Error):
            pass
    # A failed read or keyless reference has no reliable mismatch count.
    print(f"store={args.store} mismatches={'unknown' if mismatches is None else mismatches}")
    return 0 if mismatches == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
