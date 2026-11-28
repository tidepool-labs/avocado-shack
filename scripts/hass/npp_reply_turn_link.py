#!/usr/bin/env python3
"""Check NPP reply threading, turn links, and card-only ID permission offline."""

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

from hass import npp
from hass.npp import job
from hass.skills import openreq


CHECK = "npp_reply_turn_link"
CHAT = "chat-owner"
JOB_ID = "a1b2"
CASES = (
    ("p-r0", 1, "plain question", ()),
    ("p-r1", 2, "card ready", ("/fixture/card.png",)),
    ("p-r2", 3, "second", ()),
    ("p-r9", None, "no turn", ()),
)
EXPECTED = (
    "case 0 reply_to=2026-11-21T14:01:00+00:00 ids_ok=0 attachments=[] linked=p-r0 dirty=a1b2",
    'case 1 reply_to=2026-11-21T14:02:00+00:00 ids_ok=1 attachments=["/fixture/card.png"] linked=p-r1 dirty=a1b2',
    "case 2 reply_to=2026-11-21T14:03:00+00:00 ids_ok=0 attachments=[] linked=p-r2 dirty=a1b2",
    "case 3 error=TypeError",
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
            "INSERT INTO outbox(chat, text, attachments, reply_to, ids_ok) VALUES (?, ?, ?, ?, ?)",
            (chat, text, json.dumps(list(attachments)), reply_to, int(bool(ids_ok))),
        ).lastrowid


class FixtureConversation:
    def __init__(self, db, media_root):
        self.db = db
        self.settings = {"mediaRoot": media_root}
        self.requests = openreq.OpenRequests(db)
        self.outbox = FixtureOutbox(db)
        self._owner_chats = {CHAT}
        self.problems = []

    def _now(self):
        return T(10)

    def _problem(self, level, code):
        self.problems.append(code)

    def _tx(self):
        return nullcontext()

    def _code(self, hexdigest):
        return hexdigest[:4]

    def _live_reasons(self, draft):
        return []


def seed(conv):
    db = conv.db
    photo = "a" * 64
    request_id = conv.requests.put(CHAT, "p-req", T(0), skill="npp", texts=["fig jam"],
                                   slots={"intake": {}}, turns=8, attachments=[photo])
    db.execute(
        "INSERT INTO npp_jobs(job_id, chat, sender, photo_sha, open_request_id, state, created_at) "
        "VALUES (?, ?, 'sender-1', ?, ?, 'working', ?)",
        (JOB_ID, CHAT, photo, request_id, T(0).isoformat()),
    )
    segment_id = db.execute(
        "INSERT INTO npp_segments(job_id, started_by, accepted_at, deadline_at) VALUES (?, 'p-seg', ?, ?)",
        (JOB_ID, T(0).isoformat(), T(30).isoformat()),
    ).lastrowid
    job_row = db.execute("SELECT * FROM npp_jobs WHERE job_id=?", (JOB_ID,)).fetchone()
    return job_row, segment_id


def observe_case(jobs, db, job_row, segment_id, index, case):
    provider_id, minute, text, attachments = case
    if minute is not None:
        received = T(minute)
        message = SimpleNamespace(provider_id=provider_id, received_at=received.isoformat(),
                                  reply_to=None, chat=CHAT)
        jobs.turn(JOB_ID, message, "answer", received, segment_id)
    jobs.dirty.clear()
    try:
        row_id = jobs.reply(job_row, text, provider_id, attachments)
    except TypeError:
        return f"case {index} error=TypeError", False

    row = db.execute("SELECT * FROM outbox WHERE id=?", (row_id,)).fetchone()
    links = db.execute("SELECT provider_id FROM npp_turns WHERE reply_outbox_id=? ORDER BY provider_id",
                       (row_id,))
    linked = ",".join(link["provider_id"] for link in links)
    dirty = ",".join(sorted(jobs.dirty))
    line = (f"case {index} reply_to={row['reply_to']} ids_ok={row['ids_ok']} "
            f"attachments={row['attachments']} linked={linked} dirty={dirty}")
    return line, row["ids_ok"] == 1 and json.loads(row["attachments"]) == []


def check():
    failed = False
    with TemporaryDirectory() as media_root, closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        conv = FixtureConversation(db, media_root)
        jobs = job.Jobs(conv, None, npp.assets())
        job_row, segment_id = seed(conv)
        for index, case in enumerate(CASES):
            line, ids_without_card = observe_case(jobs, db, job_row, segment_id, index, case)
            print(line)
            if ids_without_card:
                print(f"FAIL ids-without-card {index}")
                failed = True
            if line != EXPECTED[index]:
                print(f"FAIL reply-changed {index}")
                failed = True
    return failed


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    try:
        failed = check()
    except Exception:
        print("FAIL check-error")
        failed = True
    print(f"{'FAIL' if failed else 'PASS'} {CHECK}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
