#!/usr/bin/env python3
"""Check the retry predicate used for '?' on an open NPP listing, offline."""

import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp
from hass.npp import job


CASES = (
    (None, ['render-failed'], None),
    (None, ['question'], None),
    (1, ['card'], 'queued'),
    (1, ['card'], 'delivered'),
    (1, ['render-failed', 'question'], None),
    (1, ['question', 'render-failed'], 'superseded'),
    (None, [], None),
    (1, ['card', None], 'queued'),
    (None, ['retake'], None),
    (1, ['card'], 'building'),
)
EXPECTED = (True, False, True, False, False, True, False, True, False, False)
STAMP = '2000-01-01T00:00:00+00:00'


def seed_case(db, i, current_version, outcomes, version_state):
    job_id = f'job{i:04d}'
    db.execute(
        "INSERT INTO npp_jobs (job_id, chat, sender, photo_sha, open_request_id, state, "
        "created_at, current_version) VALUES (?, ?, 'fixture-sender', ?, 1, 'editing', ?, ?)",
        (job_id, f'fixture-chat-{i}', 'a' * 64, STAMP, current_version),
    )
    segment_id = None
    for n, outcome in enumerate(outcomes):
        segment_id = db.execute(
            "INSERT INTO npp_segments (job_id, started_by, accepted_at, deadline_at, "
            "ended_at, outcome) VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, f'fixture-turn-{i}-{n}', STAMP, STAMP,
             None if outcome is None else STAMP, outcome),
        ).lastrowid
    if version_state is not None:
        db.execute(
            "INSERT INTO npp_versions (job_id, n, segment_id, listing_json, listing_sha, "
            "patch_json, state) VALUES (?, ?, ?, '{}', ?, '{}', ?)",
            (job_id, current_version, segment_id, 'a' * 64, version_state),
        )
    return job_id


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    try:
        with TemporaryDirectory() as media_root, closing(sqlite3.connect(':memory:')) as db:
            db.row_factory = sqlite3.Row
            conv = SimpleNamespace(db=db, settings={'mediaRoot': media_root})
            jobs = job.Jobs(conv, None, hass.npp.assets())
            for i, (current_version, outcomes, version_state) in enumerate(CASES):
                try:
                    job_id = seed_case(db, i, current_version, outcomes, version_state)
                    row = jobs.one('SELECT * FROM npp_jobs WHERE job_id=?', job_id)
                    retry = jobs.needs_retry(row)
                except Exception:
                    print('FAIL check-error')
                    failed = True
                    continue

                print(f"case {i} retry={'yes' if retry else 'no'}")
                if retry and version_state == 'delivered':
                    print(f'FAIL retry-on-delivered {i}')
                    failed = True
                if not retry and outcomes and outcomes[-1] == 'render-failed':
                    print(f'FAIL no-retry-after-render-failed {i}')
                    failed = True
                if retry != EXPECTED[i]:
                    print(f'FAIL retry-changed {i}')
                    failed = True
    except Exception:
        print('FAIL check-error')
        failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_retry_question_mark")
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
