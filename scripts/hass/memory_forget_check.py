#!/usr/bin/env python3
"""Check forgotten owner memory and count active cost facts on a private copy."""

import argparse
from collections import Counter
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import tempfile


STORE = "conversation.sqlite3"
CHECK = "memory_forget_check"


class CheckError(Exception):
    """A fixed, non-private finding suitable for stdout."""


def _temp_candidates():
    candidates = [path for var in ("TMPDIR", "TEMP", "TMP") if (path := os.getenv(var))]
    return candidates + ["/tmp", "/var/tmp", "/usr/tmp", os.getcwd()]


def _temp_parent(state):
    source = os.path.realpath(state)
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.commonpath((source, parent)) != source
                and os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)):
            return parent
    raise CheckError("temp-unavailable")


def _mode(path):
    try:
        return path.lstat().st_mode
    except FileNotFoundError:
        return None


def _read_snapshot(state):
    store = state / STORE
    try:
        if not stat.S_ISDIR(state.lstat().st_mode):
            raise CheckError("unsafe-state")
        mode = _mode(store)
        if mode is None:
            return None
        if not stat.S_ISREG(mode):
            raise CheckError("unsafe-state")
    except (OSError, ValueError):
        raise CheckError("unsafe-state") from None

    # Input is an operator-supplied, stable copy. Opening only the scratch copy
    # lets SQLite recover there without creating or updating input sidecars.
    input_files = [store]
    not_sqlite = f"not-sqlite {STORE}"
    try:
        for suffix in ("-wal", "-journal"):
            sidecar = state / (STORE + suffix)
            mode = _mode(sidecar)
            if mode is not None:
                if not stat.S_ISREG(mode):
                    raise CheckError(not_sqlite)
                input_files.append(sidecar)
        parent = _temp_parent(state)
        with tempfile.TemporaryDirectory(dir=parent) as scratch:
            for path in input_files:
                shutil.copyfile(path, Path(scratch) / path.name)
            with closing(sqlite3.connect(Path(scratch) / STORE)) as db:
                db.execute("PRAGMA query_only=ON")
                if not db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone():
                    return None
                # Only the blankness predicate is read, never the value text.
                return db.execute("SELECT id, key, value = '', superseded_at IS NULL, "
                                  "forgotten_at IS NULL FROM memory").fetchall()
    except (OSError, sqlite3.Error):
        raise CheckError(not_sqlite) from None


def _report(rows):
    keys = set()
    active = Counter()
    last_forgotten = {}
    for row_id, key, _, not_superseded, not_forgotten in rows:
        if not isinstance(row_id, int) or not isinstance(key, str):
            raise CheckError(f"not-sqlite {STORE}")
        keys.add(key)
        if not_forgotten:
            if not_superseded:  # Both predicates hold, matching hass.memory.ACTIVE.
                active[key] += 1
        else:
            last_forgotten[key] = max(row_id, last_forgotten.get(key, row_id))

    unblanked = sum(not blank and key in last_forgotten and row_id <= last_forgotten[key]
                    for row_id, key, blank, _, _ in rows)
    multiple = sum(count > 1 for count in active.values())
    print(f"rows {len(rows)}")
    print(f"keys {len(keys)}")
    print(f"active {sum(active.values())}")
    print(f"forgotten-keys {len(last_forgotten)}")
    print(f"cost-keys-active {sum(count for key, count in active.items() if key.startswith('cost.'))}")
    return [f"{reason} {count}" for reason, count in (("unblanked", unblanked), ("multiple-active", multiple))
            if count]


def main(argv=None):
    parser = argparse.ArgumentParser(prog=CHECK, description=__doc__, allow_abbrev=False)
    parser.add_argument("--state", required=True, type=Path, metavar="DIR", help="input state directory")
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        parser.error("unrecognized arguments")  # Do not echo a private path in a usage error.

    findings = []
    try:
        rows = _read_snapshot(args.state)
        if rows is None:
            print("memory absent")
        else:
            findings = _report(rows)
    except CheckError as exc:
        findings = [str(exc)]
    for finding in findings:
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} {CHECK}")
    return int(bool(findings))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())
