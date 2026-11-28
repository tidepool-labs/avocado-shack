#!/usr/bin/env python3
"""Replay NPP input routing with synthetic messages and an in-memory request store."""

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
from hass.npp.private_numbers import Finance
from hass.skills import openreq

NAME = "npp_input_request_routing"
CHAT = "chat-owner"
SENDER = "sender-1"
PHOTO_A = "a" * 64
PHOTO_B = "b" * 64
CASES = (
    ("editing", "expired", []),
    ("editing", "expired", [PHOTO_B]),
    (None, "none", []),
    (None, "unrelated", [PHOTO_A]),
    (None, "none", [PHOTO_A]),
    ("editing", "live", []),
    ("asking", "live", []),
    ("card_out", "live", [PHOTO_B]),
)
EXPECTED = (
    "case 0 npp-expired jobs=a1b2:expired turn=answer outbox=1 duplicate=answered",
    "case 1 npp-working jobs=a1b2:expired,3668:working turn=start outbox=0 duplicate=answered",
    "case 2 None jobs=- turn=- outbox=0 duplicate=-",
    "case 3 None jobs=- turn=- outbox=0 duplicate=-",
    "case 4 npp-working jobs=293f:working turn=start outbox=0 duplicate=-",
    "case 5 npp-working jobs=a1b2:working turn=edit outbox=0 duplicate=answered",
    "case 6 npp-working jobs=a1b2:working turn=answer outbox=0 duplicate=answered",
    "case 7 npp-working jobs=a1b2:editing turn=photo outbox=0 duplicate=expired",
)


def T(minutes):
    return datetime(2026, 11, 21, 14, tzinfo=timezone.utc) + timedelta(minutes=minutes)


class Outbox:
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
        self.outbox = Outbox(db)
        self._owner_chats = {CHAT}
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


def seed_job(db, state, request_id):
    created, ended, deadline = (T(m).isoformat() for m in (0, 1, 30))
    version = 1 if state == "card_out" else None
    db.execute("INSERT INTO npp_jobs(job_id,chat,sender,photo_sha,open_request_id,state,created_at,current_version) "
               "VALUES ('a1b2',?,?,?,?,?,?,?)", (CHAT, SENDER, PHOTO_A, request_id, state, created, version))
    segment = db.execute(
        "INSERT INTO npp_segments(job_id,started_by,accepted_at,deadline_at,ended_at,outcome) "
        "VALUES ('a1b2','p-seg',?,?,?,'card')", (created, deadline, ended),
    ).lastrowid
    if version is not None:
        db.execute("INSERT INTO npp_versions(job_id,n,segment_id,listing_json,listing_sha,patch_json,state) "
                   "VALUES ('a1b2',1,?,'{}',?,'{}','delivered')", (segment, "0" * 64))
    db.execute("INSERT INTO npp_questions(job_id,qid,asked_outbox_id,asked_at,answered_by,answered_at,state) "
               "VALUES ('a1b2','duplicate',1,?,'p-seg',?,'answered')", (created, ended))


def run_case(index, state, request, photos, assets):
    now = T(100 if request == "expired" else 10)
    with TemporaryDirectory() as media_root, closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        conv = FixtureConversation(db, media_root, now)
        jobs = job.Jobs(conv, None, assets)
        request_id = 999
        if request != "none":
            skill = "item.add" if request == "unrelated" else "npp"
            request_id = conv.requests.put(CHAT, "p-req", T(0), skill=skill, texts=["fig jam"],
                                           slots={"intake": {}}, turns=8,
                                           attachments=[PHOTO_A] if skill == "npp" else [])
        if state is not None:
            seed_job(db, state, request_id)

        # Read the same stored row on both sides, independently of the routing lookup.
        def unrelated_open():
            return request == "unrelated" and db.execute(
                "SELECT 1 FROM open_requests WHERE request_id=? AND state='open'", (request_id,),
            ).fetchone() is not None

        waiting = unrelated_open()
        msg = SimpleNamespace(provider_id=f"p-route-{index}", received_at=now.isoformat(), reply_to=None, chat=CHAT)
        result = jobs.input(msg, SENDER, now, now, Finance(public_words="fixture words"), list(photos))
        replaced = waiting and not unrelated_open()
        states = ",".join(f"{jid}:{status}" for jid, status in db.execute(
            "SELECT job_id,state FROM npp_jobs ORDER BY rowid")) or "-"
        turn = db.execute("SELECT kind FROM npp_turns WHERE provider_id=?", (msg.provider_id,)).fetchone()
        outbox = db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
        duplicate = db.execute("SELECT state FROM npp_questions WHERE job_id='a1b2' AND qid='duplicate'").fetchone()
        line = (f"case {index} {result} jobs={states} turn={turn[0] if turn else '-'} "
                f"outbox={outbox} duplicate={duplicate[0] if duplicate else '-'}")
        return line, replaced


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    try:
        assets = hass.npp.assets()
        for index, case in enumerate(CASES):
            line, replaced = run_case(index, *case, assets)
            print(line)
            if replaced:
                print(f"FAIL replaced-unrelated {index}")
                failed = True
            if line != EXPECTED[index]:
                print(f"FAIL route-changed {index}")
                failed = True
    except Exception:
        # Do not echo an exception message or traceback into the bounded report.
        print("FAIL check-error")
        failed = True
    print(f"{'FAIL' if failed else 'PASS'} {NAME}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
