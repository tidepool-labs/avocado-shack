#!/usr/bin/env python3
"""Check candidate names against Hass's duplicate sources and held catalog products."""

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

from hass.claims import fold
from hass.label_reader import identity_text
from hass.npp.missing import _duplicates


class InputError(ValueError):
    """A fixed, non-sensitive failure reason."""


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's diagnostic can echo an unrecognized argument verbatim.
        super().error("invalid arguments (see --help)")


def _leaf_mode(path):
    """Return the leaf's mode without dereferencing it, or None if absent."""
    try:
        return path.lstat().st_mode
    except FileNotFoundError:
        return None


def _open_text(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("expected a regular file")
    return path.open(encoding="utf-8")


def _read_names(path):
    try:
        with _open_text(path) as source:
            # Keep internal control characters for Hass's identity check.
            names = [line.removesuffix("\n") for line in source
                     if line.strip() and not line.lstrip().startswith("#")]
    except (OSError, ValueError):
        raise InputError("bad-names") from None
    if not names:
        raise InputError("bad-names")
    return names


def _reject_constant(_value):
    raise ValueError("invalid JSON constant")


def _read_content(directory):
    try:
        with _open_text(directory / "products.json") as source:
            products = json.load(source, parse_constant=_reject_constant)["products"]
        with _open_text(directory / "makers.json") as source:
            makers = json.load(source, parse_constant=_reject_constant)["makers"]
        if (isinstance(products, list) and isinstance(makers, dict)
                and all(isinstance(record, dict) and isinstance(record.get("name"), str)
                        for record in (*products, *makers.values()))):
            return products, makers
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        pass
    raise InputError("unreadable content")


def _temp_candidates():
    return [value for key in ("TMPDIR", "TEMP", "TMP")
            if (value := os.environ.get(key))] + ["/tmp", "/var/tmp", "/usr/tmp", os.getcwd()]


def _temp_parent(input_dirs):
    inputs = [os.path.realpath(directory) for directory in input_dirs]
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)
                and all(os.path.commonpath((parent, directory)) != directory for directory in inputs)):
            return parent
    raise InputError("temp-unavailable")


def _snapshot_clover(store, input_dirs):
    try:
        mode = _leaf_mode(store)
    except OSError:
        raise InputError("unsafe-state") from None
    if mode is None:
        return None
    if not stat.S_ISREG(mode):
        raise InputError("unsafe-state")

    reason = f"not-sqlite {store.name}"
    try:
        files = [store]
        for suffix in ("-wal", "-journal"):
            sidecar = store.with_name(store.name + suffix)
            mode = _leaf_mode(sidecar)
            if mode is not None:
                if not stat.S_ISREG(mode):
                    raise InputError(reason)
                files.append(sidecar)

        # Recovery and any new SQLite metadata belong to the copy, not the input.
        with tempfile.TemporaryDirectory(dir=_temp_parent(input_dirs)) as scratch:
            for path in files:
                shutil.copyfile(path, Path(scratch) / path.name)
            with closing(sqlite3.connect(Path(scratch) / store.name)) as db:
                db.execute("PRAGMA query_only=ON")
                items = tuple(SimpleNamespace(name=name) for (name,) in db.execute("SELECT name FROM items"))
        return SimpleNamespace(items=items)
    except (OSError, sqlite3.Error):
        raise InputError(reason) from None


def _read_clover(state, input_dirs):
    clover = state / "clover"
    try:
        if not stat.S_ISDIR(state.lstat().st_mode):
            raise InputError("unsafe-state")
        mode = _leaf_mode(clover)
        if mode is None:
            return None
        if not stat.S_ISDIR(mode):
            raise InputError("unsafe-state")
    except OSError:
        raise InputError("unsafe-state") from None
    return _snapshot_clover(clover / "cache.sqlite3", (*input_dirs, state))


def _report(names, products, makers, clover):
    active = Counter(fold(p["name"]) for p in products if p.get("status") != "held")
    held = {fold(p["name"]) for p in products if p.get("status") == "held"}
    failed = False
    for i, line in enumerate(names, 1):
        item = identity_text("name", line, title=True)
        if item is None:
            print(f"candidate {i} refused")
            print(f"FAIL identity-refused {i}")
            failed = True
            continue
        duplicates = _duplicates(item, products, makers, clover)
        held_match = fold(item) in held
        sources = duplicates + (("held",) if held_match else ())
        print(f"candidate {i} {','.join(sources) or 'none'}")
        if duplicates:
            print(f"FAIL duplicate {i}")
        if held_match:
            print(f"FAIL held-match {i}")
        failed |= bool(sources)
    print(f"catalog-twins {sum(count > 1 for count in active.values())}")
    return failed


def main(argv=None):
    parser = PrivateParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", required=True, type=Path, help="directory with products.json and makers.json")
    parser.add_argument("--names", required=True, type=Path, help="UTF-8 file with one name per line")
    parser.add_argument("--state", type=Path, help="optional directory with a cached Clover snapshot")
    args = parser.parse_args(argv)
    try:
        names = _read_names(args.names)
        products, makers = _read_content(args.content)
        clover = None if args.state is None else _read_clover(args.state, (args.content, args.names.parent))
        failed = _report(names, products, makers, clover)
    except InputError as error:
        print(f"FAIL {error}")
        failed = True
    print("FAIL npp_duplicate_precheck" if failed else "PASS npp_duplicate_precheck")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
