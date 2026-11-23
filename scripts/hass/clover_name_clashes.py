#!/usr/bin/env python3
"""Report count-only Clover name clashes from an offline state copy."""

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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.clover import mapper  # noqa: E402


class Finding(Exception):
    """A report reason that carries no input values or paths."""


class ReportParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse can include the supplied tokens in a usage error.
        super().error("invalid arguments; expected --state DIR")


def _mode(path):
    try:
        return path.lstat().st_mode
    except FileNotFoundError:
        return None


def _temp_candidates():
    return [*(os.environ[key] for key in ("TMPDIR", "TEMP", "TMP") if os.environ.get(key)),
            "/tmp", "/var/tmp", "/usr/tmp", os.getcwd()]


def _temp_parent(state):
    # Clover is a real directory beneath state, so excluding state covers both.
    input_root = os.path.realpath(state)
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)
                and os.path.commonpath((input_root, parent)) != input_root):
            return parent
    raise Finding("temp-unavailable")


def _snapshot(state):
    clover = state / "clover"
    store = clover / "cache.sqlite3"
    try:
        if not stat.S_ISDIR(_mode(state) or 0):
            raise Finding("unsafe-state")
        clover_mode = _mode(clover)
        if clover_mode is None:
            return None
        if not stat.S_ISDIR(clover_mode):
            raise Finding("unsafe-state")
        store_mode = _mode(store)
        if store_mode is None:
            return None
        if not stat.S_ISREG(store_mode):
            raise Finding("unsafe-state")
    except (OSError, ValueError):
        raise Finding("unsafe-state") from None

    invalid = f"not-sqlite {store.name}"
    sources = [store]
    try:
        for suffix in ("-wal", "-journal"):
            sidecar = store.with_name(store.name + suffix)
            mode = _mode(sidecar)
            if mode is not None:
                if not stat.S_ISREG(mode):
                    raise Finding(invalid)
                sources.append(sidecar)
    except OSError:
        raise Finding(invalid) from None

    try:
        temporary = tempfile.TemporaryDirectory(dir=_temp_parent(state))
    except OSError:
        raise Finding("temp-unavailable") from None
    try:
        with temporary as directory:
            target = Path(directory)
            for source in sources:
                shutil.copyfile(source, target / source.name)
            with closing(sqlite3.connect(target / store.name)) as db:
                db.execute("PRAGMA query_only=ON")
                rows = db.execute("SELECT name, sku, hidden FROM items").fetchall()
                # SQLite's TEXT affinity still permits blobs in a copied cache.
                if any(name is not None and not isinstance(name, str) for name, _, _ in rows):
                    raise Finding(invalid)
                return rows
    except (OSError, sqlite3.Error):
        raise Finding(invalid) from None


def _report(rows):
    visible = Counter()
    hidden = Counter()
    without_sku = Counter()
    unsafe = 0
    for name, sku, is_hidden in rows:
        try:
            mapper.clean_name(name)
        except mapper.MapError:
            unsafe += 1
        key = mapper.norm_name(name)
        if is_hidden == 0:
            visible[key] += 1
            if not sku:
                without_sku[key] += 1
        else:
            hidden[key] += 1

    print(f"items {len(rows)}")
    print(f"visible {sum(visible.values())}")
    print(f"hidden-shadow {sum(hidden[key] for key in visible)}")
    print(f"note unsafe-name {unsafe}")
    clashes = [key for key, count in visible.items() if count > 1]
    unnameable = sum(without_sku[key] for key in clashes)
    if clashes:
        print(f"FAIL visible-name-clash {len(clashes)}")
    if unnameable:
        print(f"FAIL clash-without-sku {unnameable}")
    return not clashes


def main(argv=None):
    parser = ReportParser(description=__doc__, prog="clover_name_clashes.py")
    parser.add_argument("--state", required=True, type=Path, metavar="DIR")
    state = parser.parse_args(argv).state
    try:
        rows = _snapshot(state)
        if rows is None:
            print("cache absent")
            passed = True
        else:
            passed = _report(rows)
    except Finding as exc:
        print(f"FAIL {exc}")
        passed = False
    print(f"{'PASS' if passed else 'FAIL'} clover_name_clashes")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
