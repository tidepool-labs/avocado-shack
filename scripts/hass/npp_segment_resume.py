#!/usr/bin/env python3
"""Check listing segment continuation and rollover using offline fixtures."""

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


CHAT = "chat-owner"
JOB_ID = "a1b2"
PHOTO_SHA = "a" * 64

# Job exists, current version, open segment, frozen version, turn kind.
CASES = (
    (False, None, False, False, "start"),
    (True, None, True, False, "answer"),
    (True, 1, True, True, "edit"),
    (True, 1, False, False, "edit"),
    (True, 1, True, False, "edit"),
    (True, None, False, False, "photo"),
)
EXPECTED = (
    "case 0 segments=1 open=1 revision=0 ended=- deadline_s=100 job=- versions=- turn=start@open",
    "case 1 segments=2 open=1 revision=1 ended=card deadline_s=1800 job=working versions=- turn=answer@open",
    "case 2 segments=3 open=1 revision=0 ended=card,superseded deadline_s=100 job=editing "
    "versions=1:superseded,2:superseded turn=edit@open",
    "case 3 segments=2 open=1 revision=0 ended=card deadline_s=100 job=editing versions=1:superseded turn=edit@open",
    "case 4 segments=2 open=1 revision=1 ended=card deadline_s=1800 job=editing versions=1:delivered turn=edit@open",
    "case 5 segments=2 open=1 revision=0 ended=card deadline_s=100 job=working versions=- turn=photo@open",
)


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


def insert_segment(db, ended_at=None, outcome=None):
    return db.execute(
        "INSERT INTO npp_segments(job_id,started_by,accepted_at,deadline_at,ended_at,outcome) "
        "VALUES (?,?,?,?,?,?)",
        (JOB_ID, "p-seg", T(0).isoformat(), T(30).isoformat(), ended_at, outcome),
    ).lastrowid


def insert_version(db, n, parent, segment, state):
    db.execute(
        "INSERT INTO npp_versions(job_id,n,parent_n,segment_id,listing_json,listing_sha,patch_json,state) "
        "VALUES (?,?,?,?,?,?,?,?)", (JOB_ID, n, parent, segment, "{}", "0" * 64, "{}", state),
    )


def job_row(db):
    return db.execute("SELECT * FROM npp_jobs WHERE job_id=?", (JOB_ID,)).fetchone()


def seed_case(conv, exists, current_version, is_open, frozen):
    db = conv.db
    request_id = conv.requests.put(CHAT, "p-req", T(0), skill="npp", texts=["fig jam"],
                                   slots={"intake": {}}, turns=8, attachments=[PHOTO_SHA])
    state = "working" if current_version is None else "card_out"
    db.execute(
        "INSERT INTO npp_jobs(job_id,chat,sender,photo_sha,open_request_id,state,created_at,current_version) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (JOB_ID, CHAT, "sender-1", PHOTO_SHA, request_id, state, T(0).isoformat(), current_version),
    )
    ended = insert_segment(db, T(1).isoformat(), "card")
    if current_version == 1:
        insert_version(db, 1, None, ended, "delivered")
    if is_open:
        segment = insert_segment(db)
        if frozen:
            insert_version(db, 2, 1, segment, "building")
    if not exists:
        db.execute("DELETE FROM npp_versions")
        db.execute("DELETE FROM npp_segments")
        db.execute("DELETE FROM npp_jobs")
    return job_row(db)


def observe(db, index, provider_id):
    segments = db.execute("SELECT * FROM npp_segments WHERE job_id=? ORDER BY segment_id", (JOB_ID,)).fetchall()
    opened = [segment for segment in segments if segment["ended_at"] is None]
    current = opened[-1] if opened else None
    revision = deadline_s = "-"
    if current is not None:
        revision = current["revision"]
        deadline = datetime.fromisoformat(current["deadline_at"])
        accepted = datetime.fromisoformat(current["accepted_at"])
        deadline_s = int((deadline - accepted).total_seconds())
    ended = ",".join(segment["outcome"] or "-" for segment in segments if segment["ended_at"] is not None) or "-"
    listing_job = job_row(db)
    state = listing_job["state"] if listing_job else "-"
    versions = db.execute("SELECT n,state FROM npp_versions WHERE job_id=? ORDER BY n", (JOB_ID,))
    version_states = ",".join(f"{n}:{version_state}" for n, version_state in versions) or "-"
    turn = db.execute("SELECT kind,segment_id FROM npp_turns WHERE provider_id=? AND job_id=?",
                      (provider_id, JOB_ID)).fetchone()
    kind = turn["kind"] if turn else "-"
    destination = "open" if turn and current and turn["segment_id"] == current["segment_id"] else "other"
    return (f"case {index} segments={len(segments)} open={len(opened)} revision={revision} "
            f"ended={ended} deadline_s={deadline_s} job={state} versions={version_states} "
            f"turn={kind}@{destination}", len(opened))


def run_case(index, case, pinned):
    exists, current_version, is_open, frozen, kind = case
    with TemporaryDirectory() as media_root, closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        conv = FixtureConversation(db, media_root)
        jobs = job.Jobs(conv, None, pinned)
        row = seed_case(conv, exists, current_version, is_open, frozen)
        msg = SimpleNamespace(provider_id=f"p-res-{index}", received_at=T(5).isoformat(), reply_to=None, chat=CHAT)
        jobs._resume(JOB_ID, row, msg, kind, T(5), T(6))
        return observe(db, index, msg.provider_id)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    try:
        pinned = hass.npp.assets()
        for index, (case, expected) in enumerate(zip(CASES, EXPECTED, strict=True)):
            line, open_count = run_case(index, case, pinned)
            print(line)
            if open_count != 1:
                print(f"FAIL open-segments {index}")
                failed = True
            if line != expected:
                print(f"FAIL resume-changed {index}")
                failed = True
    except Exception:
        # An incomplete check fails closed without leaking exception text.
        print("FAIL check-error")
        failed = True
    print("FAIL npp_segment_resume" if failed else "PASS npp_segment_resume")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
