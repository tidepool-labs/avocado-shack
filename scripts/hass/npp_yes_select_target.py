#!/usr/bin/env python3
"""Check NPP yes-target selection offline against 16 synthetic fixtures."""

import argparse
from collections import namedtuple
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


Case = namedtuple("Case", "state versions current n accepted received reply_to receipt live")
SINGLE = Case("card_out", ((1, "delivered", 1, "g1"),), 1, None, 5, 5, None, True, True)
MULTI = SINGLE._replace(versions=((1, "superseded", 1, "g1"), (2, "delivered", 3, "g2")), current=2)
CASES = (
    SINGLE,
    SINGLE._replace(n=1),
    SINGLE._replace(n=2),
    MULTI,
    MULTI._replace(n=2),
    MULTI._replace(n=1),
    SINGLE._replace(state="approved", versions=((1, "approved", 1, "g1"),)),
    SINGLE._replace(receipt=False),
    SINGLE._replace(state="editing"),
    SINGLE._replace(versions=((1, "delivered", 6, "g1"),)),
    MULTI._replace(reply_to="g2"),
    MULTI._replace(reply_to="g1"),
    MULTI._replace(reply_to="g9"),
    MULTI._replace(n=3, reply_to="g2"),
    SINGLE._replace(live=False),
    SINGLE._replace(received=1),
)

# Replayed against Jobs.select on the base checkout, not derived from its rules.
EXPECTED = (
    "case 0 ok 1",
    "case 1 ok 1",
    "case 2 not_ready -",
    "case 3 which_card -",
    "case 4 ok 2",
    "case 5 replaced -",
    "case 6 already-done -",
    "case 7 not_ready -",
    "case 8 not_ready -",
    "case 9 not_ready -",
    "case 10 ok 2",
    "case 11 replaced -",
    "case 12 not_ready -",
    "case 13 which_card -",
    "case 14 not_ready -",
    "case 15 not_ready -",
)

CHAT = "chat-owner"
JOB_ID = "a1b2"
PHOTO_SHA = "a" * 64
TOOL = "npp_yes_select_target"


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


def seed(db, requests, case):
    request_id = 999
    if case.live:
        request_id = requests.put(CHAT, "p-req", T(0), skill="npp", texts=["fig jam"],
                                  slots={"intake": {}}, turns=8, attachments=[PHOTO_SHA])
    db.execute(
        "INSERT INTO npp_jobs(job_id,chat,sender,photo_sha,open_request_id,state,created_at,current_version) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (JOB_ID, CHAT, "sender-1", PHOTO_SHA, request_id, case.state, T(0).isoformat(), case.current),
    )
    for n, state, minute, transport_id in case.versions:
        delivered = T(minute).isoformat()
        segment_id = db.execute(
            "INSERT INTO npp_segments(job_id,started_by,accepted_at,deadline_at,ended_at,outcome) "
            "VALUES (?,?,?,?,?,'card')",
            (JOB_ID, "p-seg", T(0).isoformat(), T(30).isoformat(), delivered),
        ).lastrowid
        db.execute(
            "INSERT INTO npp_versions(job_id,n,segment_id,listing_json,listing_sha,patch_json,"
            "outbox_id,queued_at,state,delivered_at,transport_message_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (JOB_ID, n, segment_id, "{}", "0" * 64, "{}", 100 + n, T(minute - 0.5).isoformat(),
             state, delivered, transport_id),
        )


def run_case(i, case):
    with TemporaryDirectory() as media_root, closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        problems = []
        conv = SimpleNamespace(
            db=db, settings={"mediaRoot": media_root}, requests=openreq.OpenRequests(db),
            outbox=FixtureOutbox(db), _owner_chats={CHAT}, _now=lambda: T(10),
            _problem=lambda level, code: problems.append(code), _tx=nullcontext,
            _code=lambda hexdigest: hexdigest[:4], _live_reasons=lambda draft: [],
        )
        jobs = job.Jobs(conv, None, hass.npp.assets())
        jobs.receipt_for = (lambda row: None) if case.receipt else None
        seed(db, conv.requests, case)
        job_row = jobs.one("SELECT * FROM npp_jobs WHERE job_id=?", JOB_ID)
        msg = SimpleNamespace(provider_id=f"p-yes-{i}", received_at=T(case.received).isoformat(),
                              reply_to=case.reply_to, chat=CHAT)
        reason, target = jobs.select(job_row, msg, case.n, T(case.accepted), conv._now())
        turn = jobs.one("SELECT 1 FROM npp_turns WHERE provider_id=? AND kind='yes'", msg.provider_id)
        line = f"case {i} {'ok' if reason is None else reason} {target['n'] if target is not None else '-'}"
        return line, turn is not None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)
    failed = False
    try:
        for i, (case, expected) in enumerate(zip(CASES, EXPECTED, strict=True)):
            line, has_turn = run_case(i, case)
            print(line)
            if not has_turn:
                print(f"FAIL no-turn {i}")
                failed = True
            if line != expected:
                print(f"FAIL target-changed {i}")
                failed = True
    except Exception:
        print("FAIL check-error")
        failed = True
    print(f"{'FAIL' if failed else 'PASS'} {TOOL}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
