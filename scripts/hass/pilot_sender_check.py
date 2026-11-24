#!/usr/bin/env python3
"""Check which chats sent messages in a pilot window using a read-only store."""

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import re
import sqlite3


TABLES = ("messages", "message_chats")


def instant(value):
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.utcoffset() is not None:
            return parsed
    return None


def report(findings, *, failed=False):
    for reason in findings:
        print(f"FAIL {reason}")
    failed = failed or bool(findings)
    print(f"{'FAIL' if failed else 'PASS'} pilot_sender_check")
    return int(failed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversation", required=True, type=Path, help="SQLite conversation store")
    parser.add_argument("--from", dest="start", required=True, help="inclusive ISO-8601 instant with offset")
    parser.add_argument("--to", required=True, help="exclusive ISO-8601 instant with offset")
    parser.add_argument("--allow", required=True, action="append", help="allowed chat digest (12 lowercase hex)")
    parser.add_argument("--expect-chat", action="append", default=[], metavar="DIGEST",
                        help="require activity from one allowed chat digest (12 lowercase hex)")
    args = parser.parse_args(argv)

    findings = []
    allowed = set(args.allow)
    expected = args.expect_chat[0] if args.expect_chat else None
    if any(not re.fullmatch(r"[0-9a-f]{12}", digest) for digest in args.allow + args.expect_chat):
        findings.append("bad-digest")
    elif len(args.expect_chat) > 1:
        findings.append("multiple-expected-chats")
    elif expected is not None and expected not in allowed:
        findings.append("expected-chat-not-allowed")
    start, end = instant(args.start), instant(args.to)
    if start is None or end is None:
        findings.append("bad-time")
        return report(findings)
    if start >= end:
        findings.append("empty-window")
    if findings:
        return report(findings)

    counts = Counter()
    unattributed = 0
    try:
        uri = args.conversation.absolute().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("BEGIN")  # Check the schema and rows in one read snapshot.
            tables = {name for (name,) in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (?, ?)", TABLES
            )}
            if missing := [f"missing-table {table}" for table in TABLES if table not in tables]:
                return report(missing)
            for received_at, chat in db.execute("""
                SELECT m.received_at, c.chat
                FROM messages AS m LEFT JOIN message_chats AS c ON m.provider_id = c.provider_id
            """):
                received = instant(received_at)
                if received is None:
                    # A bad timestamp cannot safely be classified as outside the window.
                    findings.append("bad-time")
                elif start <= received < end:
                    if chat is None:
                        unattributed += 1
                    elif isinstance(chat, str):
                        counts[sha256(chat.encode("utf-8")).hexdigest()[:12]] += 1
                    else:
                        raise ValueError("invalid chat type")
    except (OSError, ValueError, sqlite3.Error):
        # There is no generic store-error reason in the output contract. Do not
        # invent one, expose an exception, or print potentially partial totals.
        return report(findings, failed=True)

    if unattributed:
        findings.append(f"unattributed {unattributed}")
    for digest, count in sorted(counts.items()):
        verdict = "allowed" if digest in allowed else "other"
        print(f"chat {digest} messages {count} {verdict}")
        if verdict == "other":
            findings.append(f"other-chat {digest}")
    if expected is not None and expected not in counts:
        findings.append("missing-expected-chat")
    return report(findings)


if __name__ == "__main__":
    raise SystemExit(main())
