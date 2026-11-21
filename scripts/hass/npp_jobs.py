#!/usr/bin/env python3
"""List job metadata from a standalone copy of the Hass state database."""

import argparse
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import re
import sqlite3
from pathlib import Path


TABLES = ("npp_jobs", "npp_versions", "npp_segments", "npp_turns")
OUTCOMES = {
    "published": "posted", "cancelled": "cancelled", "expired": "expired", "retake": "retake",
    "working": "open", "asking": "open", "card_out": "open", "editing": "open",
    "approved": "open", "publish_failed": "open",
}
OPEN_STATES = tuple(state for state, outcome in OUTCOMES.items() if outcome == "open")
QUERY = f"""
WITH versions AS (
    SELECT job_id, count(delivered_at) AS delivered,
           max(julianday(queued_at)) AS queued, max(julianday(delivered_at)) AS sent
    FROM npp_versions GROUP BY job_id
), segments AS (
    SELECT job_id, max(julianday(accepted_at)) AS started, max(julianday(ended_at)) AS ended
    FROM npp_segments GROUP BY job_id
), turns AS (
    SELECT job_id, max(julianday(accepted_at)) AS accepted
    FROM npp_turns GROUP BY job_id
), jobs AS (
    SELECT j.job_id, j.state, j.current_version, coalesce(v.delivered, 0) AS delivered,
           j.created_at, j.closed_at,
           max(julianday(j.created_at), coalesce(julianday(j.closed_at), 0),
               coalesce(julianday(j.polish_started_at), 0), coalesce(v.queued, 0),
               coalesce(v.sent, 0), coalesce(s.started, 0), coalesce(s.ended, 0),
               coalesce(t.accepted, 0)) AS changed
    FROM npp_jobs AS j
    LEFT JOIN versions AS v USING (job_id)
    LEFT JOIN segments AS s USING (job_id)
    LEFT JOIN turns AS t USING (job_id)
)
SELECT job_id, state, current_version, delivered, strftime('%Y-%m-%dT%H:%MZ', changed)
FROM jobs
WHERE ? OR closed_at IS NULL OR state IN ({", ".join("?" for _ in OPEN_STATES)})
    OR changed >= julianday(?)
ORDER BY julianday(created_at), job_id
"""


def since_date(value):
    try:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            return date.fromisoformat(value)
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("expected a date in YYYY-MM-DD form")


def fail(reason):
    print(f"FAIL bad-input {reason}")
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--state-db", required=True, type=Path, metavar="FILE")
    parser.add_argument("--since", type=since_date, metavar="YYYY-MM-DD",
                        help="always include open jobs; include other jobs changed from this UTC date "
                             "(default: last 7 days)")
    parser.add_argument("--all", action="store_true", help="include every job regardless of date")
    args = parser.parse_args(argv)
    since = args.since or datetime.now(timezone.utc) - timedelta(days=7)

    try:
        supplied = args.state_db.absolute()
        path = supplied.resolve(strict=True)
        if any((parent / ".git").exists() for p in (supplied, path) for parent in p.parents):
            return fail("worktree")
        if not path.is_file():
            return fail("state-db")
        # mode=ro alone can still create a WAL shared-memory sidecar. An
        # immutable open cannot recover a journal: require a standalone copy.
        for suffix in ("-wal", "-journal"):
            sidecar = path.with_name(path.name + suffix)
            if sidecar.exists() and sidecar.stat().st_size:
                return fail("non-standalone-copy")
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
            present = {row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            for table in TABLES:
                if table not in present:
                    return fail(table)
            rows = db.execute(QUERY, (args.all, *OPEN_STATES, since.isoformat())).fetchall()
    except (OSError, RuntimeError, sqlite3.Error):
        return fail("state-db")

    lines = []
    for job, state, version, delivered, changed in rows:
        # Only the actual listing-code and state shapes are reportable.
        if (not isinstance(job, str) or not re.fullmatch(r"[0-9a-f]{4,12}", job)
                or state not in OUTCOMES or (version is not None and type(version) is not int)
                or changed is None):
            return fail("npp_jobs")
        current = "-" if version is None else str(version)
        lines.append(f"{job}\t{state}\t{current}\t{delivered}\t{changed}\t{OUTCOMES[state]}")
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
