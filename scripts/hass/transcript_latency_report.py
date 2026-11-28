#!/usr/bin/env python3
"""Report inbound transcript latency for a half-open time window, offline."""

import argparse
from contextlib import closing, contextmanager
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile

NAME = "transcript_latency_report"
DB_NAME = "transcript.sqlite3"
KIND = re.compile(r"[a-z][a-z0-9_-]{0,31}")


class ReportParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse can include raw arguments (such as private paths) in errors.
        super().error("invalid arguments; see --help")


def aware_time(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.utcoffset() is not None else None


def figures(values):
    values.sort()
    n = len(values)
    if not n:
        return "none", "none", "none"
    # Compute ceil(n/2) and ceil(9*n/10) exactly, then index from zero.
    return values[(n - 1) // 2], values[(9 * n - 1) // 10], values[-1]


def report(db, since, until, *, require_latency=False):
    count = unparsed = null_latency = bad_latency = 0
    values = []
    by_kind = {}
    for utc, kind, latency in db.execute(
        "SELECT utc, kind, latency_ms FROM events WHERE direction = 'in' COLLATE BINARY"
    ):
        t = aware_time(utc)
        if t is None:
            unparsed += 1
            continue
        if not since <= t < until:
            continue
        count += 1
        label = kind if isinstance(kind, str) and KIND.fullmatch(kind) else "other"
        group = by_kind.setdefault(label, [])
        if latency is None:
            null_latency += 1
        elif type(latency) is not int or latency < 0:
            bad_latency += 1
        else:
            values.append(latency)
            group.append(latency)

    p50, p90, maximum = figures(values)
    print(f"count {count}")
    print(f"unparsed {unparsed}")
    print(f"null-latency {null_latency}")
    print(f"p50_ms {p50}")
    print(f"p90_ms {p90}")
    print(f"max_ms {maximum}")
    for label, group in sorted(by_kind.items()):
        p50, p90, maximum = figures(group)
        print(f"kind {label} p50_ms {p50} p90_ms {p90} max_ms {maximum}")
    findings = []
    if bad_latency:
        findings.append(f"bad-latency {bad_latency}")
    if require_latency and count > 0 and not values:
        findings.append("no-latency-samples")
    return findings


def _temp_candidates():
    for name in ("TMPDIR", "TEMP", "TMP"):
        value = os.environ.get(name)
        if value:
            yield value
    yield from ("/tmp", "/var/tmp", "/usr/tmp")
    yield os.getcwd()


def _private_temp_parent(input_roots):
    roots = {os.path.realpath(root) for root in input_roots}
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        # Never let tempfile probe or create anything under an input root.
        if any(os.path.commonpath((root, parent)) == root for root in roots):
            continue
        if os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK):
            return parent
    return None


@contextmanager
def _open_snapshot(path, temp_parent):
    sources = [path]
    for suffix in ("-wal", "-journal"):
        sidecar = path.with_name(path.name + suffix)
        try:
            mode = os.lstat(sidecar).st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(mode):
            raise ValueError("unsafe SQLite sidecar")
        sources.append(sidecar)

    # SQLite can rebuild shared memory and recover the database on the copy only.
    with tempfile.TemporaryDirectory(dir=temp_parent) as directory:
        snapshot = Path(directory)
        for source in sources:
            shutil.copyfile(source, snapshot / source.name)
        with closing(sqlite3.connect(snapshot / path.name)) as db:
            db.execute("PRAGMA query_only=ON")
            db.text_factory = lambda data: data.decode("utf-8", errors="surrogateescape")
            yield db


def check_store(path, since, until, state, *, require_latency=False):
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return [f"missing-db {DB_NAME}"]
    except (OSError, ValueError):
        return [f"not-sqlite {DB_NAME}"]
    if not stat.S_ISREG(mode):
        return [f"unsafe-db {DB_NAME}"]
    if since is None or until is None:
        return []
    try:
        temp_parent = _private_temp_parent((state, path.parent))
        if temp_parent is None:
            return ["temp-unavailable"]
        with _open_snapshot(path, temp_parent) as db:
            return report(db, since, until, require_latency=require_latency)
    except (OSError, ValueError, sqlite3.Error):
        return [f"not-sqlite {DB_NAME}"]


def main(argv=None):
    parser = ReportParser(prog=NAME, description=__doc__)
    parser.add_argument("--state", type=Path, required=True, help="directory containing the transcript")
    parser.add_argument("--since", required=True, help="inclusive timezone-aware ISO timestamp")
    parser.add_argument("--until", required=True, help="exclusive timezone-aware ISO timestamp")
    parser.add_argument("--require-latency", action="store_true",
                        help="fail if the window has inbound events but no measured latency")
    args = parser.parse_args(argv)

    since, until = aware_time(args.since), aware_time(args.until)
    findings = []
    if since is None or until is None or since >= until:
        findings.append("bad-window")
        since = until = None
    findings.extend(check_store(args.state / DB_NAME, since, until, args.state,
                                require_latency=args.require_latency))
    for finding in findings:
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} {NAME}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
