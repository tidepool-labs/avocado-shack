#!/usr/bin/env python3
"""Check payload nullness in an offline inbox snapshot; report counts only."""

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

STORE = "inbox.sqlite3"
STATES = ("pending", "done", "history")


class Finding(Exception):
    """A fixed diagnostic that never includes input values or paths."""


def _temp_candidates():
    configured = (os.environ.get(key) for key in ("TMPDIR", "TEMP", "TMP"))
    return [*(value for value in configured if value), "/tmp", "/var/tmp", "/usr/tmp", os.getcwd()]


def _temp_parent(state):
    source = os.path.realpath(state)
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.commonpath((source, parent)) != source
                and os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)):
            return parent
    raise Finding("temp-unavailable")


def _snapshot_counts(state):
    """Return (total, state counts, invalid payload counts), or None if absent."""
    store = state / STORE
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

    not_sqlite = f"not-sqlite {STORE}"
    try:
        files = [store]
        for suffix in ("-wal", "-journal"):
            sidecar = store.with_name(STORE + suffix)
            try:
                mode = sidecar.lstat().st_mode
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(mode):
                raise Finding(not_sqlite)
            files.append(sidecar)

        with tempfile.TemporaryDirectory(dir=_temp_parent(state)) as scratch:
            for source in files:
                shutil.copyfile(source, Path(scratch) / source.name)
            with closing(sqlite3.connect(Path(scratch) / STORE)) as db:
                db.execute("PRAGMA query_only=ON")
                total = 0
                counts, invalid = Counter(), Counter()
                for row_state, is_null in db.execute("SELECT state, payload IS NULL FROM inbound"):
                    total += 1
                    if row_state in STATES:
                        counts[row_state] += 1
                        if bool(is_null) == (row_state == "pending"):
                            invalid[row_state] += 1
                return total, counts, invalid
    except (sqlite3.Error, OSError):
        raise Finding(not_sqlite) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path, help="directory containing a quiescent inbox copy")
    args = parser.parse_args(argv)
    findings = []
    try:
        report = _snapshot_counts(args.state)
    except Finding as error:
        findings.append(str(error))
    else:
        if report is None:
            print("inbox absent")
        else:
            total, counts, invalid = report
            print(f"inbound {total}")
            for state in STATES:
                if counts[state]:
                    print(f"state {state} {counts[state]}")
            for state in ("done", "history", "pending"):
                if invalid[state]:
                    reason = "pending-empty" if state == "pending" else f"payload-kept {state}"
                    findings.append(f"{reason} {invalid[state]}")

    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} inbox_payload_check")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
