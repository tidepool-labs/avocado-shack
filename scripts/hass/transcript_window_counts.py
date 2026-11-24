#!/usr/bin/env python3
"""Count events in a stable transcript snapshot over a half-open time window."""

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime
from hashlib import sha256
import os
from pathlib import Path
import re
import sqlite3
import stat


NAME = "transcript.sqlite3"
LABEL = re.compile(r"[a-z][a-z0-9_-]{0,31}")


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error can echo an unexpected argument verbatim.
        super().error("invalid arguments; see --help")


def aware_time(value):
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            return parsed
    return None


def safe_label(value):
    return value if isinstance(value, str) and LABEL.fullmatch(value) else "other"


def report(path, since, until, *, require_complete=False):
    groups = {name: Counter() for name in ("direction", "kind", "disposition", "chat")}
    events = draft_codes = unparsed = 0
    # The offline input must not be changing: unix-none takes no file locks.
    # Keep the WAL index in memory so no shared sidecar is created or modified.
    uri = path.absolute().as_uri() + "?mode=ro&vfs=unix-none"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.execute("PRAGMA locking_mode=EXCLUSIVE")
        for utc, direction, kind, disposition, chat, has_draft in db.execute(
            "SELECT utc, direction, kind, disposition, chat, draft_code IS NOT NULL FROM events"
        ):
            timestamp = aware_time(utc)
            if timestamp is None:
                unparsed += 1
            elif since <= timestamp < until:
                if not isinstance(chat, str):
                    raise ValueError("chat is not text")
                events += 1
                draft_codes += has_draft
                groups["direction"][safe_label(direction)] += 1
                groups["kind"][safe_label(kind)] += 1
                groups["disposition"][safe_label(disposition)] += 1
                groups["chat"][sha256(chat.encode("utf-8")).hexdigest()[:12]] += 1

    if require_complete and unparsed:
        # An unassignable row could belong to this window; suppress partial totals.
        return unparsed

    print(f"events {events}")
    for name, counts in groups.items():
        for value, count in sorted(counts.items()):
            print(f"{name} {value} {count}")
    print(f"draft-codes {draft_codes}")
    print(f"unparsed {unparsed}")
    return 0


def inspect_store(path):
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return f"unsafe-db {NAME}"
    except (FileNotFoundError, NotADirectoryError):
        return f"missing-db {NAME}"
    except (OSError, ValueError):
        return f"not-sqlite {NAME}"

    return None


def main(argv=None):
    parser = PrivateArgumentParser(prog="transcript_window_counts.py", description=__doc__,
                                    allow_abbrev=False)
    parser.add_argument("--state", required=True, type=Path, help="snapshot directory")
    parser.add_argument("--since", required=True, help="inclusive ISO time with offset")
    parser.add_argument("--until", required=True, help="exclusive ISO time with offset")
    parser.add_argument("--require-complete", action="store_true",
                        help="fail without a breakdown if any snapshot timestamp is unassignable")
    args = parser.parse_args(argv)
    since, until = aware_time(args.since), aware_time(args.until)
    findings = []
    if since is None or until is None or since >= until:
        findings.append("bad-window")
    path = args.state / NAME
    store_finding = inspect_store(path)
    if store_finding:
        findings.append(store_finding)
    elif not findings:
        try:
            incomplete = report(path, since, until, require_complete=args.require_complete)
            if incomplete:
                findings.append(f"incomplete-window unparsed {incomplete}")
        except (sqlite3.Error, OSError, ValueError):
            findings.append(f"not-sqlite {NAME}")
    for finding in findings:
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} transcript_window_counts")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
