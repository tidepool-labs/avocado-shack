#!/usr/bin/env python3
"""Report aggregate bundle states from an offline Hass state copy."""

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.clover.bundle import STATES


REPORT = "clover_bundle_report"
STORE = "bundles.sqlite3"
IN_FLIGHT = ("till-intent", "till-applied", "link-written", "site-intent", "site-live")


class ReportError(Exception):
    """A fixed finding safe to print without disclosing the input."""


def _mode(path):
    try:
        return path.lstat().st_mode
    except FileNotFoundError:
        return None


def _temp_candidates():
    return [value for key in ("TMPDIR", "TEMP", "TMP") if (value := os.getenv(key))] + [
        "/tmp", "/var/tmp", "/usr/tmp", os.getcwd(),
    ]


def _snapshot_rows(state):
    clover = state / "clover"
    store = clover / STORE
    try:
        if not stat.S_ISDIR(_mode(state) or 0):
            raise ReportError("unsafe-state")
        clover_mode = _mode(clover)
        if clover_mode is None:
            return None
        if not stat.S_ISDIR(clover_mode):
            raise ReportError("unsafe-state")
        store_mode = _mode(store)
        if store_mode is None:
            return None
        if not stat.S_ISREG(store_mode):
            raise ReportError("unsafe-state")
    except (OSError, ValueError):
        raise ReportError("unsafe-state") from None

    not_sqlite = f"not-sqlite {STORE}"
    files = [store]
    try:
        for suffix in ("-wal", "-journal"):
            sidecar = store.with_name(STORE + suffix)
            mode = _mode(sidecar)
            if mode is not None:
                if not stat.S_ISREG(mode):
                    raise ReportError(not_sqlite)
                files.append(sidecar)
    except OSError:
        raise ReportError(not_sqlite) from None

    # The state directory encloses all inputs. Never let tempfile probe it,
    # even via an alias, or touch the source's shared-memory file.
    source = os.path.realpath(state)
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)
                and os.path.commonpath((source, parent)) != source):
            break
    else:
        raise ReportError("temp-unavailable")

    try:
        temporary = tempfile.TemporaryDirectory(dir=parent)
    except OSError:
        raise ReportError("temp-unavailable") from None
    try:
        with temporary as directory:
            for path in files:
                shutil.copyfile(path, Path(directory) / path.name)
            with closing(sqlite3.connect(Path(directory) / STORE)) as db:
                db.execute("PRAGMA query_only=ON")
                db.text_factory = bytes
                return [raw for (raw,) in db.execute("SELECT row FROM bundles")]
    except (OSError, sqlite3.Error):
        raise ReportError(not_sqlite) from None


def _reject_constant(_value):
    raise ValueError("non-JSON constant")


def _report(rows, now):
    counts = Counter()
    bad = unknown = expired = undos = 0
    for raw in rows:
        try:
            row = json.loads(raw, parse_constant=_reject_constant)
        except (TypeError, ValueError, RecursionError):
            bad += 1
            continue
        if not isinstance(row, dict):
            bad += 1
            continue
        undos += isinstance(row.get("undo_of"), str)
        state = row.get("state")
        if not isinstance(state, str):
            bad += 1
        elif state not in STATES:
            unknown += 1
        else:
            counts[state] += 1
            expires = row.get("expires")
            if state == "proposed" and type(expires) in (int, float) and expires <= now:
                expired += 1

    print(f"bundles {len(rows)}")
    for state in STATES:
        if counts[state]:
            print(f"state {state} {counts[state]}")
    print(f"proposed-expired {expired}")
    print(f"undo-bundles {undos}")
    return [f"{reason} {count}" for reason, count in (
        ("bad-row", bad), ("unknown-state", unknown),
        ("till-uncertain", counts["till-uncertain"]), ("partial", counts["partial"]),
        ("split", counts["split"]), ("in-flight", sum(counts[state] for state in IN_FLIGHT)),
    ) if count]


def _parse_now(value):
    try:
        instant = datetime.fromisoformat(value)
        if instant.utcoffset() is not None:
            return instant.timestamp()
    except (ValueError, OverflowError, OSError):
        pass
    raise argparse.ArgumentTypeError("expected a timezone-aware ISO-8601 time")


def main(argv=None):
    parser = argparse.ArgumentParser(prog=f"{REPORT}.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--state", required=True, type=Path, help="offline state directory")
    parser.add_argument("--now", type=_parse_now, help="timezone-aware ISO-8601 time (default: current UTC)")
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        parser.error("unrecognized arguments")  # Do not echo input values.
    now = args.now if args.now is not None else datetime.now(timezone.utc).timestamp()

    findings = []
    try:
        rows = _snapshot_rows(args.state)
        if rows is None:
            print("bundles absent")
        else:
            findings = _report(rows, now)
    except ReportError as error:
        findings = [str(error)]
    for finding in findings:
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} {REPORT}")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
