#!/usr/bin/env python3
"""Offline drift check for active NPP listings and reserved listing codes."""

import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp
from hass.npp import job
from hass.skills import openreq


STATES = (
    "working", "asking", "card_out", "editing", "retake",
    "approved", "published", "publish_failed", "cancelled", "expired",
)
CODES = ("a1b2", "A1B2", "a1b2c3", "ffff")
EXPECTED = (
    "case 0 working active=a1b2",
    "case 1 asking active=a1b2",
    "case 2 card_out active=a1b2",
    "case 3 editing active=a1b2",
    "case 4 retake active=a1b2",
    "case 5 approved active=none",
    "case 6 published active=none",
    "case 7 publish_failed active=none",
    "case 8 cancelled active=none",
    "case 9 expired active=none",
    "taken a1b2 yes",
    "taken A1B2 no",
    "taken a1b2c3 no",
    "taken ffff no",
)
CHAT, SENDER, LISTING = "chat-owner", "sender-1", "a1b2"
PHOTO = "a" * 64


def T(minutes):
    return datetime(2026, 11, 21, 14, tzinfo=timezone.utc) + timedelta(minutes=minutes)


class FakeOutbox:
    def __init__(self, db):
        self.db = db
        db.execute("CREATE TABLE outbox(id INTEGER PRIMARY KEY, chat TEXT, text TEXT, "
                   "attachments TEXT, reply_to TEXT, ids_ok INTEGER)")

    def add(self, chat, text, attachments=(), reply_to=None, *, long_ok=False, ids_ok=False):
        return self.db.execute(
            "INSERT INTO outbox(chat, text, attachments, reply_to, ids_ok) VALUES (?,?,?,?,?)",
            (chat, text, json.dumps(list(attachments)), reply_to, int(bool(ids_ok))),
        ).lastrowid


class FakeConversation:
    def __init__(self, db, media_root):
        self.db = db
        self.settings = {"mediaRoot": media_root}
        self.requests = openreq.OpenRequests(db)
        self.outbox = FakeOutbox(db)
        self._owner_chats = {CHAT}
        self.problems = []

    def _now(self):
        return T(10)

    def _problem(self, level, code):
        self.problems.append(code)

    @contextmanager
    def _tx(self):
        yield

    def _code(self, hexdigest):
        return hexdigest[:4]

    def _live_reasons(self, draft):
        return []


def insert_job(db, code, chat, sender, state, *, request_id=999, closed=False):
    db.execute(
        "INSERT INTO npp_jobs(job_id, chat, sender, state, photo_sha, open_request_id, "
        "created_at, closed_at) VALUES (?,?,?,?,?,?,?,?)",
        (code, chat, sender, state, PHOTO, request_id, T(0).isoformat(),
         T(5).isoformat() if closed else None),
    )


@contextmanager
def fixture(media_root, pinned):
    with closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        conv = FakeConversation(db, media_root)
        jobs = job.Jobs(conv, None, pinned)
        try:
            yield conv, jobs
        finally:
            jobs.executor.shutdown()


def check_lookup(media_root, pinned, report):
    for i, state in enumerate(STATES):
        # This boundary must not depend on the repo's mutable ACTIVE constant.
        closed = i >= 5
        with fixture(media_root, pinned) as (conv, jobs):
            request_id = conv.requests.put(
                CHAT, "p-req", T(0), skill="npp", texts=["fig jam"],
                slots={"intake": {}}, turns=8, attachments=[PHOTO],
            )
            insert_job(conv.db, LISTING, CHAT, SENDER, state, request_id=request_id, closed=closed)
            insert_job(conv.db, "c3d4", "chat-2", SENDER, "working")
            insert_job(conv.db, "e5f6", CHAT, "sender-2", "working")
            active = jobs.active(CHAT, SENDER)
            code = active["job_id"] if active is not None else "none"
            line = f"case {i} {state} active={code}"
            print(line)
            if active is not None and (active["chat"], active["sender"]) != (CHAT, SENDER):
                report(f"other-sender {i}")
            if closed and code == LISTING:
                report(f"closed-job-active {i}")
            if line != EXPECTED[i]:
                report(f"active-changed {i}")

    with fixture(media_root, pinned) as (conv, jobs):
        insert_job(conv.db, LISTING, CHAT, SENDER, "cancelled", closed=True)
        for i, code in enumerate(CODES, start=len(STATES)):
            line = f"taken {code} {'yes' if jobs.taken(code) else 'no'}"
            print(line)
            if line != EXPECTED[i]:
                report(f"taken-changed {code}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)
    failed = False

    def report(reason):
        nonlocal failed
        failed = True
        print(f"FAIL {reason}")

    try:
        with TemporaryDirectory() as media_root:
            check_lookup(media_root, hass.npp.assets(), report)
    except Exception:
        # An incomplete check is a failure. Never echo exception details.
        report("check-error")

    print(f"{'FAIL' if failed else 'PASS'} npp_active_job_lookup")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
