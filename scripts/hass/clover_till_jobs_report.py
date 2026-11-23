#!/usr/bin/env python3
"""Report counts and queue age from an offline conversation-store copy."""

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.clover.approvals import MAX_JOBS


STORE = "conversation.sqlite3"
REPORT = "clover_till_jobs_report"


class Finding(Exception):
    """A fixed diagnostic safe to print without underlying error details."""


def _temp_candidates():
    return [value for key in ("TMPDIR", "TEMP", "TMP")
            if (value := os.environ.get(key))] + ["/tmp", "/var/tmp", "/usr/tmp", os.getcwd()]


def _temp_parent(state):
    # tempfile's default search can probe TMPDIR by creating a file there.
    input_dir = os.path.realpath(state)
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.commonpath((input_dir, parent)) != input_dir
                and os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)):
            return parent
    raise Finding("temp-unavailable")


def _snapshot_rows(state):
    """Copy only the store and recovery sidecars; SQLite never opens the input."""
    store = state / STORE
    not_sqlite = f"not-sqlite {STORE}"
    try:
        if not stat.S_ISDIR(state.lstat().st_mode):
            raise Finding("unsafe-state")
        try:
            mode = store.lstat().st_mode
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(mode):
            raise Finding("unsafe-state")
    except (OSError, ValueError):
        raise Finding("unsafe-state") from None

    files = [store]
    try:
        for suffix in ("-wal", "-journal"):
            sidecar = store.with_name(STORE + suffix)
            try:
                mode = sidecar.lstat().st_mode
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(mode):
                raise Finding(not_sqlite)
            files.append(sidecar)
    except OSError:
        raise Finding(not_sqlite) from None

    try:
        with tempfile.TemporaryDirectory(dir=_temp_parent(state)) as scratch:
            copy = Path(scratch) / STORE
            try:
                for source in files:
                    shutil.copyfile(source, copy.with_name(source.name))
                with closing(sqlite3.connect(copy)) as db:
                    db.execute("PRAGMA query_only=ON")
                    if not db.execute("SELECT 1 FROM sqlite_master "
                                      "WHERE type='table' AND name='till_jobs'").fetchone():
                        return None
                    return db.execute("SELECT received_at, done, allowed FROM till_jobs").fetchall()
            except (OSError, sqlite3.Error):
                raise Finding(not_sqlite) from None
    except OSError:
        raise Finding("temp-unavailable") from None


def _aware_time(value):
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            pass
        else:
            if parsed.utcoffset() is not None:
                return parsed
    return None


def _now_arg(value):
    parsed = _aware_time(value)
    if parsed is None:
        raise argparse.ArgumentTypeError("expected a timezone-aware ISO-8601 time")
    return parsed


def _report(rows, now):
    if rows is None:
        print("till jobs absent")
        return []

    pending = done = not_allowed = bad_time = 0
    oldest_age = None
    pending_bad_time = False
    for received_at, is_done, allowed in rows:
        received = _aware_time(received_at)
        bad_time += received is None
        done += is_done == 1
        if is_done == 0:
            pending += 1
            not_allowed += allowed == 0
            if received is None:
                pending_bad_time = True
            else:
                age = now - received
                if oldest_age is None or age > oldest_age:
                    oldest_age = age

    print(f"jobs {len(rows)}")
    print(f"done {done}")
    print(f"pending {pending}")
    print(f"pending-not-allowed {not_allowed}")
    print(f"capacity {pending}/{MAX_JOBS}")
    if oldest_age is not None and not pending_bad_time:
        print(f"oldest-pending-minutes {oldest_age // timedelta(minutes=1)}")

    findings = []
    if pending:
        findings.append(f"pending {pending}")
    if pending >= MAX_JOBS:
        findings.append("queue-full")
    if bad_time:
        findings.append(f"bad-time {bad_time}")
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path, help="offline state directory")
    parser.add_argument("--now", type=_now_arg, help="timezone-aware ISO-8601 time (default: current UTC)")
    args = parser.parse_args(argv)
    now = args.now if args.now is not None else datetime.now(timezone.utc)
    try:
        findings = _report(_snapshot_rows(args.state), now)
    except Finding as exc:
        findings = [str(exc)]
    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} {REPORT}")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
