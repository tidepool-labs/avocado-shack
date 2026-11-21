#!/usr/bin/env python3
"""Check owner yes/no binding against the real NPP job store using offline fixtures."""

import argparse
from contextlib import closing, nullcontext
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp
from hass.npp import job
from hass.skills import openreq


OWNER = "chat-owner"
JOB = "a1b2"
PHOTO = "a" * 64
DUPLICATE = ("duplicate", 1, OWNER)
NEAR_MAKER = ("near_maker", 1, OWNER)

# Open questions (id, asked minute or raw text, outbox chat), polarity,
# accepted minute, and whether the job's request exists and is live.
CASES = (
    ((DUPLICATE,), True, 2, True),
    ((DUPLICATE,), False, 2, True),
    ((NEAR_MAKER,), False, 2, True),
    ((NEAR_MAKER,), True, 2, True),
    ((("selling_price", 1, OWNER),), True, 2, True),
    ((DUPLICATE, NEAR_MAKER), True, 2, True),
    ((DUPLICATE,), True, None, True),
    ((("duplicate", 3, OWNER),), True, 2, True),
    ((("duplicate", 1, "chat-other"),), True, 2, True),
    ((DUPLICATE,), True, 2, False),
    ((), True, 2, True),
    ((("duplicate", "bad", OWNER),), True, 2, True),
)
EXPECTED = (
    "case 0 npp-working answers=1 job=working",
    "case 1 cancelled answers=1 job=cancelled",
    "case 2 npp-working answers=1 job=working",
    "case 3 npp-working answers=1 job=working",
    "case 4 None answers=0 job=asking",
    "case 5 None answers=0 job=asking",
    "case 6 None answers=0 job=asking",
    "case 7 None answers=0 job=asking",
    "case 8 None answers=0 job=asking",
    "case 9 None answers=0 job=asking",
    "case 10 None answers=0 job=asking",
    "case 11 None answers=0 job=asking",
)


def T(minute):
    return datetime(2026, 11, 21, 14, tzinfo=timezone.utc) + timedelta(minutes=minute)


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


def run_case(index, case, pinned):
    questions, polarity, accepted_minute, live = case
    now = T(10)
    with TemporaryDirectory() as media_root, closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        problems = []
        conv = SimpleNamespace(
            db=db, settings={"mediaRoot": media_root}, requests=openreq.OpenRequests(db),
            outbox=FixtureOutbox(db), _owner_chats={OWNER}, _now=lambda: now,
            _problem=lambda level, code: problems.append(code), _tx=nullcontext,
            _code=lambda hexdigest: hexdigest[:4], _live_reasons=lambda draft: [],
        )
        jobs = job.Jobs(conv, None, pinned)
        request_id = 999
        if live:
            request_id = conv.requests.put(
                OWNER, "p-req", T(0), skill="npp", texts=["fig jam"],
                slots={"intake": {}}, turns=8, attachments=[PHOTO],
            )
        db.execute(
            "INSERT INTO npp_jobs(job_id,chat,sender,photo_sha,open_request_id,state,created_at,current_version) "
            "VALUES (?,?,?,?,?,'asking',?,NULL)",
            (JOB, OWNER, "sender-1", PHOTO, request_id, T(0).isoformat()),
        )
        db.execute(
            "INSERT INTO npp_segments(job_id,started_by,accepted_at,deadline_at) VALUES (?,?,?,?)",
            (JOB, "p-seg", T(0).isoformat(), T(30).isoformat()),
        )
        for qid, asked, chat in questions:
            asked_at = T(asked).isoformat() if isinstance(asked, int) else asked
            db.execute(
                "INSERT INTO npp_questions(job_id,qid,asked_outbox_id,asked_at,state) VALUES (?,?,?,?,'open')",
                (JOB, qid, conv.outbox.add(chat, "question"), asked_at),
            )
        job_row = db.execute("SELECT * FROM npp_jobs WHERE job_id=?", (JOB,)).fetchone()
        msg = SimpleNamespace(provider_id=f"p-ans-{index}", received_at=T(2).isoformat(), reply_to=None, chat=OWNER)
        accepted = None if accepted_minute is None else T(accepted_minute)
        result = jobs.answer(job_row, msg, polarity, accepted, now)
        count = db.execute("SELECT COUNT(*) FROM npp_answers WHERE job_id=?", (JOB,)).fetchone()[0]
        state = db.execute("SELECT state FROM npp_jobs WHERE job_id=?", (JOB,)).fetchone()[0]
        return result, count, state


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    try:
        pinned = hass.npp.assets()
        for index, case in enumerate(CASES):
            result, count, state = run_case(index, case, pinned)
            line = f"case {index} {result} answers={count} job={state}"
            print(line)
            if (result is not None) != bool(count):
                print(f"FAIL answer-row-without-binding {index}")
                failed = True
            if line != EXPECTED[index]:
                print(f"FAIL answer-changed {index}")
                failed = True
    except Exception:
        # An incomplete check must fail without dumping exception details.
        print("FAIL check-error")
        failed = True
    print(f"{'FAIL' if failed else 'PASS'} npp_owner_answer_binding")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
