#!/usr/bin/env python3
"""Replay the NPP card picture gate without a live conversation or site."""

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

from hass import media, npp
from hass.npp import job
from hass.skills import openreq


OWNER = "chat-owner"
JID = "a1b2"
IMAGE_PATH = "items/fixture-a.png"
IMAGE_SHA = "a" * 64
CASES: tuple[dict, ...] = (
    {},
    {"chat": "chat-stranger"},
    {"variant": "legacy"},
    {"digest": "f" * 64},
    {"previous": "different"},
    {"previous": "different", "turn_kind": "photo"},
    {"previous": "same"},
    {"live_reasons": ("fixture-reason",)},
    {"png": b"not a png"},
    {"note": "picture: house style"},
    {"note": "x" * 200},
    {"persist_result": "no"},
    {"persist_result": "ok"},
)
EXPECTED = (
    "case 0 outcome=card version=queued job=working attach=1 note=no",
    "case 1 outcome=render-failed version=superseded job=editing attach=0 note=no",
    "case 2 outcome=render-failed version=superseded job=editing attach=0 note=no",
    "case 3 outcome=render-failed version=superseded job=editing attach=0 note=no",
    "case 4 outcome=render-failed version=superseded job=editing attach=0 note=no",
    "case 5 outcome=card version=queued job=working attach=1 note=no",
    "case 6 outcome=card version=queued job=working attach=1 note=no",
    "case 7 outcome=render-failed version=superseded job=editing attach=0 note=no",
    "case 8 outcome=render-failed version=superseded job=editing attach=0 note=no",
    "case 9 outcome=card version=queued job=working attach=1 note=yes",
    "case 10 outcome=card version=queued job=working attach=1 note=no",
    "case 11 outcome=render-failed version=superseded job=editing attach=0 note=no",
    "case 12 outcome=card version=queued job=working attach=1 note=no",
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


def seed_segment(db, n, *, parent=None, picture=(None, None, None)):
    historical = picture[0] is not None
    sid = db.execute(
        "INSERT INTO npp_segments(job_id,started_by,accepted_at,deadline_at,ended_at,outcome) "
        "VALUES (?,?,?,?,?,?)",
        (JID, "p-seg", T(0).isoformat(), T(30).isoformat(),
         T(1).isoformat() if historical else None, "card" if historical else None),
    ).lastrowid
    db.execute(
        "INSERT INTO npp_versions(job_id,n,parent_n,segment_id,listing_json,listing_sha,patch_json,"
        "image_variant,image_path,image_sha256,state) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (JID, n, parent, sid, "{}", "0" * 64, "{}", *picture,
         "superseded" if historical else "building"),
    )
    db.execute("UPDATE npp_jobs SET current_version=? WHERE job_id=?", (n, JID))
    return sid


def run_case(index, pinned, *, chat=OWNER, variant="raw", digest=IMAGE_SHA, previous=None,
             turn_kind="edit", live_reasons=(), png=None, note="", persist_result=None):
    with TemporaryDirectory() as root, closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        problems = []
        conv = SimpleNamespace(
            db=db, settings={"mediaRoot": str(Path(root).resolve())},
            requests=openreq.OpenRequests(db), outbox=FixtureOutbox(db),
            _owner_chats={OWNER}, _now=lambda: T(10),
            _problem=lambda level, code: problems.append(code), _tx=nullcontext,
            _code=lambda hexdigest: hexdigest[:4], _live_reasons=lambda draft: list(live_reasons),
        )
        if live_reasons:
            conv.settings["liveSite"] = True
        candidate = persist_result is not None
        stages = SimpleNamespace(persist=lambda draft: {"result": persist_result}) if candidate else None
        jobs = job.Jobs(conv, stages, pinned)
        # No work is submitted to the executor during this replay.
        with jobs.executor:
            request_id = conv.requests.put(
                OWNER, "p-req", T(0), skill="npp", texts=["fig jam"],
                slots={"intake": {}}, turns=8, attachments=[IMAGE_SHA],
            )
            db.execute(
                "INSERT INTO npp_jobs(job_id,chat,sender,photo_sha,open_request_id,state,created_at) "
                "VALUES (?,?,?,?,?,'working',?)",
                (JID, chat, "sender-1", IMAGE_SHA, request_id, T(0).isoformat()),
            )
            if previous:
                picture = (("raw", IMAGE_PATH, IMAGE_SHA) if previous == "same"
                           else ("raw", "items/fixture-old.png", "b" * 64))
                seed_segment(db, 1, picture=picture)
            n = 2 if previous else 1
            sid = seed_segment(db, n, parent=1 if previous else None)
            msg = SimpleNamespace(provider_id="p-fin", received_at=T(4).isoformat(),
                                  reply_to=None, chat=OWNER)
            jobs.turn(JID, msg, turn_kind, T(4), segment=sid)
            draft = {"assets": {IMAGE_PATH: "sha256:" + digest}, "change_id": "change-1",
                     "draft_hash": "abcdef12", "base": "base-1"}
            if png is None:
                png = media.KINDS["png"] + b"fixture-card"
            card = job.Card(draft, png, variant, IMAGE_PATH, IMAGE_SHA, note, candidate)
            # Snapshot the original match before finish can change the mutable draft.
            picture_matches = draft["assets"].get(card.image_path) == "sha256:" + card.image_sha256
            job_row = jobs.one("SELECT * FROM npp_jobs WHERE job_id=?", JID)
            segment = jobs.one("SELECT * FROM npp_segments WHERE segment_id=?", sid)
            jobs.finish(job_row, segment, jobs.version(JID, n), card, T(5))

            outcome = db.execute("SELECT outcome FROM npp_segments WHERE segment_id=?", (sid,)).fetchone()[0]
            version = db.execute("SELECT state FROM npp_versions WHERE job_id=? AND n=?", (JID, n)).fetchone()[0]
            state = db.execute("SELECT state FROM npp_jobs WHERE job_id=?", (JID,)).fetchone()[0]
            out = db.execute("SELECT text, attachments FROM outbox ORDER BY id DESC LIMIT 1").fetchone()
            count = len(json.loads(out["attachments"])) if out else 0
            bracket = "yes" if out and note and f" ({note})" in out["text"] else "no"
            line = f"case {index} outcome={outcome} version={version} job={state} attach={count} note={bracket}"
            return line, bool(count and not picture_matches)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    parser.parse_args(args)
    if args:
        parser.error("no arguments accepted")

    failed = False
    try:
        pinned = npp.assets()
        for index, (case, expected) in enumerate(zip(CASES, EXPECTED, strict=True)):
            line, mismatched_attachment = run_case(index, pinned, **case)
            print(line)
            if mismatched_attachment:
                print(f"FAIL card-without-picture-match {index}")
                failed = True
            if line != expected:
                print(f"FAIL gate-changed {index}")
                failed = True
    except Exception:
        print("FAIL check-error")
        failed = True
    print("FAIL npp_card_picture_gate" if failed else "PASS npp_card_picture_gate")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
