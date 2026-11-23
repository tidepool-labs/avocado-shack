#!/usr/bin/env python3
"""Count pending work in offline Hass stores before a switch or resume."""

import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import stat
import sys


# All SQL identifiers and predicates come from this fixed list, not the stores.
CHECKS = {
    "conversation": (("outbox_unsent", "outbox", "sent_at", "IS NULL"),),
    "relay": (
        ("relay_unacked", "relay", "acked_at", "IS NULL"),
        ("card_receipt_pending", "card_receipt", "state", "= 'pending'"),
    ),
    "inbox": (("inbound_pending", "inbound", "state", "= 'pending'"),),
}


def inspect_store(path, checks):
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or not info.st_size:
            yield "FAIL not-sqlite"
            return
        with closing(sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True)) as db:
            # Both relay counts must use the same SQLite snapshot.
            db.execute("BEGIN")
            for name, table, column, predicate in checks:
                if db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? COLLATE NOCASE",
                    (table,),
                ).fetchone() is None:
                    yield f"FAIL missing-table {table}"
                    continue
                if db.execute(
                    "SELECT 1 FROM pragma_table_xinfo(?) WHERE name = ? COLLATE NOCASE",
                    (table, column),
                ).fetchone() is None:
                    yield f"FAIL missing-column {table}.{column}"
                    continue
                count = db.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} {predicate}").fetchone()[0]
                yield f"{name} {count}"
                if count:
                    yield f"FAIL pending {name}"
    except (OSError, ValueError, sqlite3.Error):
        # Paths and raw SQLite diagnostics can reveal private data.
        yield "FAIL not-sqlite"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog="A clean subset reports PARTIAL PASS.")
    parser.add_argument("--complete", action="store_true",
                        help="require --conversation, --relay and --inbox for clearance")
    for store in CHECKS:
        parser.add_argument(f"--{store}", type=Path, metavar="FILE", help=f"{store} SQLite store (read only)")
    stores = vars(parser.parse_args(argv))
    complete = stores.pop("complete")
    missing = [store for store, path in stores.items() if path is None]
    failed = len(missing) == len(CHECKS)
    if failed:
        print("FAIL no-store")
    if complete and missing:
        for store in missing:
            print(f"FAIL missing-store {store}")
        failed = True
    for store, checks in CHECKS.items():
        if stores[store] is not None:
            for line in inspect_store(stores[store], checks):
                print(line)
                failed |= line.startswith("FAIL ")
    result = "FAIL" if failed else "PARTIAL PASS" if missing else "PASS"
    print(f"{result} install_pending_work")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
