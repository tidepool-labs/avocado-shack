#!/usr/bin/env python3
"""Report the stored approval binding for one pilot change (read only)."""

import argparse
from contextlib import closing
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import re
import sqlite3
import sys


STATES = frozenset(("needs-details", "proposed", "approved", "applied", "verified",
                    "rejected", "expired", "failed", "reverted"))


def read_store(path, change_id):
    with closing(sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")  # Both projections must describe the same snapshot.
        # Conversation orders versions by row_id; replacements can be failed
        # as well as rejected. An ordinary rejection is not a replacement.
        drafts = db.execute('''
            SELECT state, draft_hash, base, created_at, proposed_at, checked_at, "commit",
                   (coalesce(replaced_by, '') <> '' OR
                    (state = 'rejected' AND reason IS 'revised')) AS replaced
              FROM drafts WHERE change_id = ? ORDER BY row_id
        ''', (change_id,)).fetchall()
        approvals = db.execute('''
            SELECT draft_hash, base, approved_at, expires_at, provider_id
              FROM approvals WHERE change_id = ? ORDER BY id
        ''', (change_id,)).fetchall()
    return drafts, approvals


def binding_reason(drafts, approvals):
    if not approvals:
        return "none"
    if len(approvals) != 1:
        return "multiple"
    approval = approvals[0]
    latest = next((row for row in reversed(drafts) if not row["replaced"]), None)
    if latest is None or latest["draft_hash"] != approval["draft_hash"]:
        return "hash-mismatch"
    if latest["base"] != approval["base"]:
        return "base-mismatch"
    values = latest["proposed_at"], approval["approved_at"], approval["expires_at"]
    if None in values:
        return "invalid-chronology"
    proposed, approved, expires = (datetime.fromisoformat(value) for value in values)
    if any(value.utcoffset() is None for value in (proposed, approved, expires)):
        return "invalid-chronology"
    if approved > expires:
        return "expired"
    if approved < proposed:
        return "before-proposal"
    return None


def short_hex(value):
    if value is None:
        return "-"
    digest = value.removeprefix("sha256:")
    if not re.fullmatch(r"[0-9a-fA-F]{12,}", digest):
        raise ValueError("invalid digest")
    return digest[:12]


def timestamp(value):
    if value is None:
        return "-"
    return datetime.fromisoformat(value).isoformat()


def report(drafts, approvals):
    lines = []
    for row in drafts:
        if row["state"] not in STATES:
            raise ValueError("invalid draft state")
        lines.append(f'draft state={row["state"]} draft_hash={short_hex(row["draft_hash"])} '
                     f'base={short_hex(row["base"])} created_at={timestamp(row["created_at"])} '
                     f'proposed_at={timestamp(row["proposed_at"])} checked_at={timestamp(row["checked_at"])} '
                     f'commit={short_hex(row["commit"])}')
    for row in approvals:
        digest = sha256(row["provider_id"].encode("utf-8")).hexdigest()[:12]
        lines.append(f'approval draft_hash={short_hex(row["draft_hash"])} base={short_hex(row["base"])} '
                     f'approved_at={timestamp(row["approved_at"])} expires_at={timestamp(row["expires_at"])} '
                     f'provider_id_digest={digest}')
    reason = binding_reason(drafts, approvals)
    lines.append(f"NOT-BOUND {reason}" if reason else "BOUND")
    return "\n".join(lines), int(reason is not None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="conversation SQLite store")
    parser.add_argument("--change-id", required=True, help="exact change ID to look up")
    args = parser.parse_args(argv)
    try:
        output, status = report(*read_store(args.db, args.change_id))
    except (OSError, sqlite3.Error, TypeError, ValueError):
        print("error: could not read pilot approval binding", file=sys.stderr)
        return 1
    print(output)
    return status


if __name__ == "__main__":
    sys.exit(main())
