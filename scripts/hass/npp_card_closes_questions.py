#!/usr/bin/env python3
"""Offline drift guard for the questions a card or follow-up can close."""

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


CASES = ((), ("item",), ("selling_price", "item"), ("near_maker",))
EXPECTED = (
    "case 0 category:answered:- duplicate:open:- item:answered:p-card maker:expired:- "
    "near_maker:open:- selling_price:answered:p-card selling_price:answered:p-card",
    "case 1 category:answered:- duplicate:open:- item:open:- maker:expired:- "
    "near_maker:open:- selling_price:answered:p-card selling_price:answered:p-card",
    "case 2 category:answered:- duplicate:open:- item:open:- maker:expired:- "
    "near_maker:open:- selling_price:open:- selling_price:open:-",
    "case 3 category:answered:- duplicate:open:- item:answered:p-card maker:expired:- "
    "near_maker:open:- selling_price:answered:p-card selling_price:answered:p-card",
)
TOOL = "npp_card_closes_questions"


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


def observe(still_open):
    with TemporaryDirectory() as media_root, closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        problems = []
        conv = SimpleNamespace(
            db=db, settings={"mediaRoot": media_root}, requests=openreq.OpenRequests(db),
            outbox=FixtureOutbox(db), _owner_chats={"chat-owner"}, _now=lambda: T(10),
            _problem=lambda level, code: problems.append(code), _tx=nullcontext,
            _code=lambda hexdigest: hexdigest[:4], _live_reasons=lambda draft: [],
        )
        jobs = job.Jobs(conv, None, hass.npp.assets())
        photo = "a" * 64
        request_id = conv.requests.put("chat-owner", "p-req", T(0), skill="npp", texts=["fig jam"],
                                       slots={"intake": {}}, turns=8, attachments=[photo])
        db.executemany(
            "INSERT INTO npp_jobs(job_id,chat,sender,photo_sha,open_request_id,state,created_at) "
            "VALUES (?,?,?,?,?,'asking',?)",
            [("a1b2", "chat-owner", "sender-1", photo, request_id, T(0).isoformat()),
             ("c3d4", "chat-2", "sender-2", photo, 999, T(0).isoformat())],
        )
        db.executemany(
            "INSERT INTO npp_questions(job_id,qid,asked_outbox_id,asked_at,state) VALUES (?,?,1,?,?)",
            [(jid, qid, T(1).isoformat(), state) for jid, qid, state in (
                ("a1b2", "selling_price", "open"), ("a1b2", "selling_price", "open"),
                ("a1b2", "item", "open"), ("a1b2", "duplicate", "open"),
                ("a1b2", "near_maker", "open"), ("a1b2", "category", "answered"),
                ("a1b2", "maker", "expired"), ("c3d4", "selling_price", "open"),
            )],
        )
        jobs.answer_questions("a1b2", "p-card", T(5), still_open)
        rows = db.execute("SELECT qid,state,answered_by FROM npp_questions "
                          "WHERE job_id='a1b2' ORDER BY qid,rowid").fetchall()
        other = db.execute("SELECT state FROM npp_questions "
                           "WHERE job_id='c3d4' AND qid='selling_price'").fetchall()
        return rows, [row[0] for row in other] == ["open"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    parser.parse_args(args)
    if args:
        parser.error("no arguments allowed")

    failed = False
    for i, still_open in enumerate(CASES):
        try:
            rows, other_open = observe(still_open)
        except Exception:
            print("FAIL check-error")
            failed = True
            break
        line = f"case {i} " + " ".join(
            f"{qid}:{state}:{answered_by if answered_by is not None else '-'}"
            for qid, state, answered_by in rows
        )
        print(line)
        owner_states = [(qid, state) for qid, state, _ in rows if qid in ("duplicate", "near_maker")]
        for changed, reason in (
            (owner_states != [("duplicate", "open"), ("near_maker", "open")], "owner-ask-closed"),
            (not other_open, "other-job-touched"),
            (line != EXPECTED[i], "question-changed"),
        ):
            if changed:
                print(f"FAIL {reason} {i}")
                failed = True
    print(f"{'FAIL' if failed else 'PASS'} {TOOL}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
