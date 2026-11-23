#!/usr/bin/env python3
"""Compare two saved Clover caches offline; report only aggregate counts."""

import argparse
from contextlib import closing
from datetime import datetime
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.clover.cache import COLUMNS, IDENTITY_KEYS


FIELDS = (
    "name", "sku", "code", "price_cents", "price_type", "unit_name",
    "category_ids", "categories", "hidden", "available",
)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse may echo an unrecognized token, including a private path.
        super().error("invalid arguments; see --help")


def _temp_candidates():
    return [*(os.environ[key] for key in ("TMPDIR", "TEMP", "TMP") if os.environ.get(key)),
            "/tmp", "/var/tmp", "/usr/tmp", os.getcwd()]


def _temp_parent(paths):
    inputs = [os.path.realpath(path.parent) for path in paths]
    for path in _temp_candidates():
        parent = os.path.realpath(path)
        if (os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)
                and all(os.path.commonpath((folder, parent)) != folder for folder in inputs)):
            return parent
    return None


class _InputError(Exception):
    """A reason label safe to print, without the original exception or path."""


def _snapshot_sources(path):
    try:
        regular = stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        regular = False
    if not regular:
        raise _InputError("unsafe-input")

    sources = [path]
    for suffix in ("-wal", "-journal"):
        sidecar = path.with_name(path.name + suffix)
        try:
            mode = sidecar.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError:
            raise _InputError("not-sqlite") from None
        if not stat.S_ISREG(mode):
            raise _InputError("not-sqlite")
        sources.append(sidecar)
    return sources


def _read_snapshot(sources, folder):
    """Let SQLite recover/open sidecars only in this disposable private copy."""
    folder.mkdir()
    for source in sources:
        shutil.copyfile(source, folder / source.name)
    with closing(sqlite3.connect(folder / sources[0].name)) as db:
        db.execute("PRAGMA query_only=ON")
        db.row_factory = sqlite3.Row
        items = {row["id"]: row for row in db.execute(f"SELECT {', '.join(COLUMNS)} FROM items")}
        meta = dict(db.execute("SELECT key, value FROM meta"))
    return items, meta


def _as_of(meta):
    try:
        time = datetime.fromisoformat(meta.get("asOf"))
    except (TypeError, ValueError):
        return None
    return time if time.utcoffset() is not None else None


def _report(before, after, findings):
    old, old_meta = before
    new, new_meta = after
    if any(old_meta.get(key) != new_meta.get(key) for key in IDENTITY_KEYS):
        findings.append("different-till")
    start, end = _as_of(old_meta), _as_of(new_meta)
    if start is not None and end is not None and end < start:
        findings.append("reversed")

    added, removed = len(new.keys() - old.keys()), len(old.keys() - new.keys())
    changed: dict[str, int] = dict.fromkeys(FIELDS, 0)
    changed_items = stock_changed = 0
    for item_id in old.keys() & new.keys():
        left, right = old[item_id], new[item_id]
        differences = [field for field in FIELDS if left[field] != right[field]]
        for field in differences:
            changed[field] += 1
        changed_items += bool(differences)
        stock_changed += left["stock"] != right["stock"] or left["stock_modified"] != right["stock_modified"]

    print(f"before-items {len(old)}")
    print(f"after-items {len(new)}")
    print(f"added {added}")
    print(f"removed {removed}")
    for field, count in changed.items():
        print(f"changed {field} {count}")
    print(f"stock-changed {stock_changed}")
    if total := added + removed + changed_items:
        findings.append(f"till-changed {total}")


def _compare(paths, findings):
    sources = {}
    for which, path in paths.items():
        try:
            sources[which] = _snapshot_sources(path)
        except _InputError as error:
            findings.append(f"{error} {which}")
    if findings:
        return

    try:
        parent = _temp_parent(paths.values())
        if parent is None:
            findings.append("temp-unavailable")
            return
        caches = {}
        with tempfile.TemporaryDirectory(dir=parent) as temp:
            for which, files in sources.items():
                try:
                    caches[which] = _read_snapshot(files, Path(temp) / which)
                except (OSError, sqlite3.Error):
                    findings.append(f"not-sqlite {which}")
    except OSError:
        findings.append("temp-unavailable")
        return
    if not findings:
        _report(caches["before"], caches["after"], findings)


def main(argv=None):
    parser = _Parser(prog="clover_cache_diff", description=__doc__, allow_abbrev=False)
    for which in ("before", "after"):
        parser.add_argument(f"--{which}", type=Path, metavar="FILE", required=True)
    args = parser.parse_args(argv)
    findings = []
    _compare(vars(args), findings)
    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} clover_cache_diff")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
