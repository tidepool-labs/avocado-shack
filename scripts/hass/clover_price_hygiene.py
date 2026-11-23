#!/usr/bin/env python3
"""Count Clover price hygiene findings from an offline state copy."""

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
from hass.clover import mapper


class ReportError(Exception):
    """A fixed diagnostic safe to print without input values."""


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's detailed errors can echo an unrecognized path argument.
        super().error("invalid arguments (use --help)")


def _temp_candidates():
    return tuple(value for key in ("TMPDIR", "TEMP", "TMP") if (value := os.getenv(key))) + (
        "/tmp", "/var/tmp", "/usr/tmp", os.getcwd(),
    )


def _temp_parent(*input_dirs):
    inputs = [os.path.realpath(path) for path in input_dirs]
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)
                and all(os.path.commonpath((parent, root)) != root for root in inputs)):
            return parent
    raise ReportError("temp-unavailable")


def _mode(path):
    try:
        return path.lstat().st_mode
    except FileNotFoundError:
        return None


def _snapshot_rows(state):
    clover = state / "clover"
    store = clover / "cache.sqlite3"
    try:
        if not stat.S_ISDIR(_mode(state) or 0):
            raise ReportError("unsafe-state")
        mode = _mode(clover)
        if mode is None:
            return None
        if not stat.S_ISDIR(mode):
            raise ReportError("unsafe-state")
        mode = _mode(store)
        if mode is None:
            return None
        if not stat.S_ISREG(mode):
            raise ReportError("unsafe-state")
    except (OSError, ValueError):
        raise ReportError("unsafe-state") from None

    not_sqlite = f"not-sqlite {store.name}"
    try:
        sources = [store]
        for suffix in ("-wal", "-journal"):
            sidecar = store.with_name(store.name + suffix)
            mode = _mode(sidecar)
            if mode is not None:
                if not stat.S_ISREG(mode):
                    raise ReportError(not_sqlite)
                sources.append(sidecar)

        try:
            temporary = tempfile.TemporaryDirectory(dir=_temp_parent(state, clover))
        except OSError:
            raise ReportError("temp-unavailable") from None
        with temporary as directory:
            snapshot = Path(directory)
            for source in sources:
                shutil.copyfile(source, snapshot / source.name)
            with closing(sqlite3.connect(snapshot / store.name)) as db:
                db.execute("PRAGMA query_only=ON")
                return db.execute("SELECT price_cents, price_type, unit_name, hidden FROM items").fetchall()
    except (OSError, sqlite3.Error):
        raise ReportError(not_sqlite) from None


def _report(rows):
    if rows is None:
        print("cache absent")
        return []

    types = Counter()
    hidden = non_lb = over_guard = missing_price = missing_unit = unknown_type = 0
    for price, price_type, unit_name, is_hidden in rows:
        hidden += bool(is_hidden)
        numeric_price = isinstance(price, (int, float))
        over_guard += numeric_price and price > mapper.MAX_PRICE_CENTS
        if price_type in mapper.PRICE_TYPES:
            types[price_type] += 1
        else:
            unknown_type += 1
        if price_type == "FIXED":
            missing_price += price is None or (numeric_price and price <= 0)
        elif price_type == "PER_UNIT":
            unit = unit_name.strip().casefold() if isinstance(unit_name, str) else ""
            missing_unit += not unit
            non_lb += bool(unit) and unit not in ("lb", "lbs", "pound", "pounds")

    print(f"items {len(rows)}")
    print(f"hidden {hidden}")
    for price_type in mapper.PRICE_TYPES:
        if types[price_type]:
            print(f"price-type {price_type} {types[price_type]}")
    print(f"note per-unit-not-lb {non_lb}")
    print(f"note over-typo-guard {over_guard}")
    return [f"{reason} {count}" for reason, count in (
        ("fixed-no-price", missing_price),
        ("per-unit-no-unit", missing_unit),
        ("unknown-price-type", unknown_type),
    ) if count]


def main(argv=None):
    parser = PrivateArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--state", required=True, type=Path, metavar="DIR", help="offline state copy")
    args = parser.parse_args(argv)
    try:
        findings = _report(_snapshot_rows(args.state))
    except ReportError as error:
        findings = [str(error)]
    for finding in findings:
        print(f"FAIL {finding}")
    print("FAIL clover_price_hygiene" if findings else "PASS clover_price_hygiene")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
