#!/usr/bin/env python3
"""Count Clover journal changes offline without printing private row details."""

import argparse
from collections import Counter
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

NAME = "clover_journal_report"
STATUS_WORD = re.compile(r"[a-z_]{1,20}")


class ReportError(Exception):
    """A fixed, safe reason for an unavailable report."""


class ReportParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's default diagnostics may echo arbitrary argument values.
        super().error("invalid arguments (see --help)")


def _utc_day(value):
    try:
        now = datetime.fromisoformat(value)
        if now.utcoffset() is not None:
            day = now.astimezone(timezone.utc).date()
            if day.toordinal() >= 7:
                return day
    except (ValueError, OverflowError):
        pass
    raise argparse.ArgumentTypeError("expected a timezone-aware ISO-8601 time")


def _temp_candidates():
    return [*(os.environ[key] for key in ("TMPDIR", "TEMP", "TMP") if os.environ.get(key)),
            "/tmp", "/var/tmp", "/usr/tmp", os.getcwd()]


def _temp_parent(input_dirs):
    inputs = [os.path.realpath(directory) for directory in input_dirs]
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)
                and all(os.path.commonpath((parent, source)) != source for source in inputs)):
            return parent
    raise ReportError("temp-unavailable")


def _mode(path):
    try:
        return path.lstat().st_mode
    except FileNotFoundError:
        return None


def _check_state(state, clover):
    try:
        if stat.S_ISDIR(_mode(state) or 0):
            mode = _mode(clover)
            if mode is None or stat.S_ISDIR(mode):
                return
    except OSError:
        pass
    raise ReportError("unsafe-state")


@contextmanager
def _snapshot(store, input_dirs):
    """Open only a disposable copy, with SQLite free to rebuild its own SHM."""
    try:
        mode = _mode(store)
        if mode is None:
            yield None
            return
        if not stat.S_ISREG(mode):
            raise ReportError(f"not-sqlite {store.name}")
        files = [store]
        for suffix in ("-wal", "-journal"):
            sidecar = store.with_name(store.name + suffix)
            mode = _mode(sidecar)
            if mode is not None:
                if not stat.S_ISREG(mode):
                    raise ReportError(f"not-sqlite {store.name}")
                files.append(sidecar)
        with tempfile.TemporaryDirectory(dir=_temp_parent(input_dirs)) as scratch:
            for path in files:
                shutil.copyfile(path, Path(scratch) / path.name)
            with closing(sqlite3.connect(Path(scratch) / store.name)) as db:
                db.execute("PRAGMA query_only=ON")
                yield db
    except (sqlite3.Error, OSError):
        raise ReportError(f"not-sqlite {store.name}") from None


def _report(state, today):
    clover = state / "clover"
    _check_state(state, clover)
    applied = {(today - timedelta(days=offset)).isoformat(): 0 for offset in range(6, -1, -1)}
    statuses = Counter()
    with _snapshot(clover / "journal.sqlite3", (state, clover)) as db:
        if db is None:
            print("journal absent")
            return []
        for status, day in db.execute("SELECT status, day FROM changes"):
            word = status if isinstance(status, str) and STATUS_WORD.fullmatch(status) else "other"
            statuses[word] += 1
            if word == "applied" and day in applied:
                applied[day] += 1

    print(f"changes {sum(statuses.values())}")
    for word, count in sorted(statuses.items()):
        print(f"status {word} {count}")
    for day, count in applied.items():
        print(f"applied-day {day} {count}")
    return [f"{reason} {statuses[word]}" for word, reason in
            (("intent", "intent-pending"), ("uncertain", "uncertain"), ("failed", "failed"))
            if statuses[word]]


def main(argv=None):
    parser = ReportParser(prog=f"{NAME}.py", description=__doc__)
    parser.add_argument("--state", required=True, type=Path, help="directory containing clover/")
    parser.add_argument("--now", type=_utc_day, help="timezone-aware ISO-8601 time (default: current UTC)")
    args = parser.parse_args(argv)
    try:
        findings = _report(args.state, args.now or datetime.now(timezone.utc).date())
    except ReportError as error:
        findings = [str(error)]
    for finding in findings:
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} {NAME}")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
