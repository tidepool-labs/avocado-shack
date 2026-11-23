#!/usr/bin/env python3
"""Compare inbound coverage in stable offline SQLite snapshots, as counts only."""

import argparse
from collections import Counter
from contextlib import closing, contextmanager
from datetime import datetime
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile


NAME = "transcript_inbound_parity"


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error text can echo raw arguments, including paths.
        super().error("invalid arguments; see --help")


def parse_time(value):
    try:
        stamp = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return stamp if stamp.tzinfo is not None else None


def _temp_candidates():
    for name in ("TMPDIR", "TEMP", "TMP"):
        if value := os.environ.get(name):
            yield value
    yield from ("/tmp", "/var/tmp", "/usr/tmp")
    yield os.getcwd()


def _private_temp_parent(input_roots):
    # Do not probe by writing: even a transient file could modify an input directory.
    for candidate in _temp_candidates():
        path = os.path.realpath(candidate)
        if os.path.isdir(path) and os.access(path, os.W_OK | os.X_OK) and not any(
                os.path.commonpath((path, root)) == root for root in input_roots):
            return path
    return None


@contextmanager
def _open_snapshot(path, temp_parent):
    # Offline inputs must already be stable. Never copy the source shared-memory sidecar.
    files = [path]
    for suffix in ("-wal", "-journal"):
        sidecar = path.with_name(path.name + suffix)
        try:
            mode = sidecar.lstat().st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(mode):
            raise OSError("unsafe SQLite sidecar")
        files.append(sidecar)

    with tempfile.TemporaryDirectory(dir=temp_parent) as scratch:
        for source in files:
            shutil.copyfile(source, Path(scratch) / source.name)
        with closing(sqlite3.connect(Path(scratch) / path.name)) as db:
            db.execute("PRAGMA query_only=ON")
            yield db


def read_window(path, query, selection, since, until, temp_parent):
    try:
        mode = os.lstat(path).st_mode
    except (FileNotFoundError, NotADirectoryError):
        return "missing-db", None, 0
    except OSError:
        return "not-sqlite", None, 0
    if not stat.S_ISREG(mode):
        return "unsafe-db", None, 0

    counts = Counter()
    unparsed = 0
    try:
        with _open_snapshot(path, temp_parent) as db:
            for provider_id, category, raw_time in db.execute(query):
                stamp = parse_time(raw_time)
                if stamp is None:
                    unparsed += 1
                elif category == selection and since <= stamp < until:
                    counts[provider_id] += 1
    except (OSError, sqlite3.Error):
        return "not-sqlite", None, 0
    return None, counts, unparsed


def main(argv=None):
    parser = PrivateArgumentParser(prog=f"{NAME}.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--state", required=True, type=Path, metavar="DIR")
    parser.add_argument("--since", required=True, metavar="ISO", help="inclusive, with timezone")
    parser.add_argument("--until", required=True, metavar="ISO", help="exclusive, with timezone")
    args = parser.parse_args(argv)
    since, until = parse_time(args.since), parse_time(args.until)
    if since is None or until is None or since >= until:
        print("FAIL bad-window")
        print(f"FAIL {NAME}")
        return 1

    stores = (
        (args.state / "inbox.sqlite3", "SELECT provider_id, state, received_at FROM inbound", "done"),
        (args.state / "transcript.sqlite3", "SELECT provider_id, direction, utc FROM events", "in"),
    )
    input_roots = {os.path.realpath(args.state),
                   *(os.path.realpath(path.parent) for path, _, _ in stores)}
    temp_parent = _private_temp_parent(input_roots)
    if temp_parent is None:
        print("FAIL temp-unavailable")
        print(f"FAIL {NAME}")
        return 1

    findings = []
    windows = []
    unparsed = 0
    for path, query, selection in stores:
        error, counts, invalid = read_window(path, query, selection, since, until, temp_parent)
        if error is not None:
            findings.append(f"{error} {path.name}")
        windows.append(counts)
        unparsed += invalid

    if not findings:
        expected, found = windows
        matched = sum((expected & found).values())
        missing = sum((expected - found).values())
        transcript_only = sum(count for key, count in found.items() if key not in expected)
        surplus = sum(count for key, count in (found - expected).items() if key in expected)
        print(f"inbound-done {sum(expected.values())}")
        print(f"matched {matched}")
        print(f"note transcript-only {transcript_only}")
        print(f"unparsed {unparsed}")
        if missing:
            findings.append(f"inbound-not-in-transcript {missing}")
        if surplus:
            findings.append(f"transcript-surplus {surplus}")

    for finding in findings:
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} {NAME}")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
