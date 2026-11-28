#!/usr/bin/env python3
"""Replay listing closure on synthetic rows and check for cross-listing writes."""

import argparse
from contextlib import closing, nullcontext
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.npp import job
from hass.skills import openreq


# Close state, request live, second segment open, second version approved.
CASES = (
    ("cancelled", True, True, False),
    ("expired", False, True, False),
    ("approved", True, True, True),
    ("cancelled", True, False, False),
    ("publish_failed", True, True, False),
)
QUESTIONS = "duplicate:expired,item:answered,near_maker:expired,selling_price:expired"
SUPERSEDED = "1:superseded,2:superseded,3:superseded,4:superseded"
EXPECTED = (
    "case 0 job=cancelled closed=yes open_segments=0 outcomes=card,cancelled,card,card "
    f"questions={QUESTIONS} versions={SUPERSEDED} request=closed",
    "case 1 job=expired closed=yes open_segments=0 outcomes=card,expired,card,card "
    f"questions={QUESTIONS} versions={SUPERSEDED} request=open",
    "case 2 job=approved closed=yes open_segments=0 outcomes=card,approved,card,card "
    f"questions={QUESTIONS} versions=1:superseded,2:approved,3:superseded,4:superseded request=closed",
    "case 3 job=cancelled closed=yes open_segments=0 outcomes=card,card,card,card "
    f"questions={QUESTIONS} versions={SUPERSEDED} request=closed",
    "case 4 job=publish_failed closed=yes open_segments=0 outcomes=card,publish_failed,card,card "
    f"questions={QUESTIONS} versions={SUPERSEDED} request=closed",
)

PHOTO = "a" * 64
LISTING, OTHER = "a1b2", "c3d4"
OWNER, OTHER_OWNER = "chat-owner", "chat-2"


def T(minutes):
    return datetime(2026, 11, 21, 14, tzinfo=timezone.utc) + timedelta(minutes=minutes)


class FixtureOutbox:
    def __init__(self, db):
        self.db = db
        db.execute("CREATE TABLE outbox(id INTEGER PRIMARY KEY, chat TEXT, text TEXT, "
                   "attachments TEXT, reply_to TEXT, ids_ok INTEGER)")

    def add(self, chat, text, attachments=(), reply_to=None, *, long_ok=False, ids_ok=False):
        return self.db.execute(
            "INSERT INTO outbox(chat,text,attachments,reply_to,ids_ok) VALUES (?,?,?,?,?)",
            (chat, text, json.dumps(list(attachments)), reply_to, int(ids_ok)),
        ).lastrowid


class FixtureConversation:
    def __init__(self, db, media_root, now):
        self.db = db
        self.settings = {"mediaRoot": media_root}
        self.requests = openreq.OpenRequests(db)
        self.outbox = FixtureOutbox(db)
        self._owner_chats = {OWNER}
        self.now = now
        self.problems = []

    def _now(self):
        return self.now

    def _problem(self, level, code):
        self.problems.append(code)

    _tx = staticmethod(nullcontext)

    @staticmethod
    def _code(hexdigest):
        return hexdigest[:4]

    @staticmethod
    def _live_reasons(draft):
        return []


def seed(conv, request_live, segment_open, version_approved):
    db = conv.db

    def put(owner, provider_id, at):
        return conv.requests.put(owner, provider_id, at, skill="npp", texts=["fig jam"],
                                 slots={"intake": {}}, turns=8, attachments=[PHOTO])

    request_id = put(OWNER, "p-req", T(0))
    other_id = put(OTHER_OWNER, "p-req-2", T(0) if request_live else conv._now())
    if not request_live:
        # Keep the expired row linked at the fixture ID so only expiry, not an
        # ID mismatch, prevents Jobs.request from returning it.
        db.execute("UPDATE open_requests SET request_id=999 WHERE request_id=?", (request_id,))
        request_id = 999
    db.executemany(
        "INSERT INTO npp_jobs(job_id,chat,sender,photo_sha,open_request_id,state,created_at,current_version) "
        "VALUES (?,?,?,?,?,'card_out',?,?)",
        [(LISTING, OWNER, "sender-1", PHOTO, request_id, T(0).isoformat(), 2),
         (OTHER, OTHER_OWNER, "sender-2", PHOTO, other_id, T(0).isoformat(), 1)],
    )
    db.executemany(
        "INSERT INTO npp_segments(segment_id,job_id,started_by,accepted_at,deadline_at,ended_at,outcome) "
        "VALUES (?,?,'p-seg',?,?,?,?)",
        [(n, jid, T(0).isoformat(), T(30).isoformat(), T(end).isoformat() if end is not None else None,
          "card" if end is not None else None)
         for n, jid, end in ((1, LISTING, 1), (2, LISTING, None if segment_open else 2),
                             (3, LISTING, 1), (4, LISTING, 1), (5, OTHER, None), (6, OTHER, 1))],
    )
    db.executemany(
        "INSERT INTO npp_versions(job_id,n,segment_id,listing_json,listing_sha,patch_json,state) "
        "VALUES (?,?,?,'{}',?,'{}',?)",
        [(jid, n, segment, "0" * 64, state)
         for jid, n, segment, state in ((LISTING, 1, 1, "superseded"),
                                        (LISTING, 2, 2, "approved" if version_approved else "delivered"),
                                        (LISTING, 3, 3, "building"), (LISTING, 4, 4, "queued"),
                                        (OTHER, 1, 6, "delivered"))],
    )
    db.executemany(
        "INSERT INTO npp_questions(job_id,qid,asked_outbox_id,asked_at,state) VALUES (?,?,1,?,?)",
        [(jid, qid, T(1).isoformat(), state)
         for jid, qid, state in ((LISTING, "selling_price", "open"), (LISTING, "item", "answered"),
                                 (LISTING, "duplicate", "expired"), (LISTING, "near_maker", "open"),
                                 (OTHER, "item", "open"))],
    )
    return request_id


def other_rows(db):
    queries = (
        ("SELECT * FROM npp_segments WHERE job_id=? ORDER BY segment_id", OTHER),
        ("SELECT * FROM npp_versions WHERE job_id=? ORDER BY n", OTHER),
        ("SELECT * FROM npp_questions WHERE job_id=? ORDER BY rowid", OTHER),
        ("SELECT state FROM npp_jobs WHERE job_id=?", OTHER),
        ("SELECT state FROM open_requests WHERE owner=? ORDER BY request_id", OTHER_OWNER),
    )
    return tuple(tuple(db.execute(sql, (key,))) for sql, key in queries)


def case_line(db, index, request_id):
    listing = db.execute("SELECT state,closed_at FROM npp_jobs WHERE job_id=?", (LISTING,)).fetchone()
    segments = db.execute("SELECT ended_at,outcome FROM npp_segments WHERE job_id=? ORDER BY segment_id",
                          (LISTING,)).fetchall()
    questions = db.execute("SELECT qid,state FROM npp_questions WHERE job_id=? ORDER BY qid", (LISTING,))
    versions = db.execute("SELECT n,state FROM npp_versions WHERE job_id=? ORDER BY n", (LISTING,))
    request = db.execute("SELECT state FROM open_requests WHERE request_id=?", (request_id,)).fetchone()
    closed = "yes" if listing["closed_at"] is not None else "no"
    open_segments = sum(row["ended_at"] is None for row in segments)
    outcomes = ",".join(row["outcome"] or "-" for row in segments) or "-"
    return (f"case {index} job={listing['state']} closed={closed} open_segments={open_segments} outcomes={outcomes} "
            f"questions={','.join(f'{qid}:{state}' for qid, state in questions)} "
            f"versions={','.join(f'{n}:{state}' for n, state in versions)} "
            f"request={request['state'] if request is not None else 'gone'}")


def run_case(index, state, request_live, segment_open, version_approved):
    now = T(10) if request_live else T(200)
    with TemporaryDirectory() as media_root, closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        conv = FixtureConversation(db, media_root, now)
        jobs = job.Jobs(conv, None, npp.assets())
        with jobs.executor:
            request_id = seed(conv, request_live, segment_open, version_approved)
            listing = db.execute("SELECT * FROM npp_jobs WHERE job_id=?", (LISTING,)).fetchone()
            before = other_rows(db)
            jobs.close(listing, state, now)
            return case_line(db, index, request_id), before != other_rows(db)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    parser.parse_args(args)
    if args:  # argparse accepts a bare '--' even though this command takes no arguments.
        parser.error("no arguments accepted")

    failed = False
    try:
        for index, case in enumerate(CASES):
            line, other_touched = run_case(index, *case)
            print(line)
            if other_touched:
                print(f"FAIL other-job-touched {index}")
                failed = True
            if line != EXPECTED[index]:
                print(f"FAIL close-changed {index}")
                failed = True
    except Exception:
        print("FAIL check-error")
        failed = True
    print(f"{'FAIL' if failed else 'PASS'} npp_job_close_rows")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
