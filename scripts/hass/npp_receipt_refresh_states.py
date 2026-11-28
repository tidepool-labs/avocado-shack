#!/usr/bin/env python3
"""Replay confirmed card delivery and job transitions against offline fixtures."""

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

NAME = "npp_receipt_refresh_states"
CHAT = "chat-owner"
JOB = "a1b2"
PHOTO_SHA = "a" * 64
CARD_SHA = "c" * 64
GOOD = ("confirmed", CARD_SHA, 3, "guid-1")

# Version state, job state, current version, observed version, receipt, source.
CASES = (
    ("queued", "editing", 1, 1, GOOD, "ok"),
    ("superseded", "editing", 2, 1, GOOD, "ok"),
    ("queued", "editing", 1, 1, ("confirmed", "d" * 64, 3, "guid-1"), "ok"),
    ("queued", "editing", 1, 1, ("pending", CARD_SHA, 3, "guid-1"), "ok"),
    ("queued", "editing", 1, 1, ("confirmed", CARD_SHA, 1, "guid-1"), "ok"),
    ("queued", "editing", 1, 1, ("confirmed", CARD_SHA, 20, "guid-1"), "ok"),
    ("queued", "asking", 1, 1, GOOD, "ok"),
    ("queued", "editing", 2, 1, GOOD, "ok"),
    ("queued", "editing", 1, 1, GOOD, "absent"),
    ("queued", "editing", 1, 1, GOOD, "raises"),
    ("queued", "working", 1, 1, ("confirmed", CARD_SHA, 3, "x" * 513), "ok"),
)
EXPECTED = (
    "case 0 version=delivered delivered=yes guid=yes job=card_out",
    "case 1 version=superseded delivered=yes guid=yes job=editing",
    "case 2 version=queued delivered=no guid=no job=editing",
    "case 3 version=queued delivered=no guid=no job=editing",
    "case 4 version=queued delivered=no guid=no job=editing",
    "case 5 version=queued delivered=no guid=no job=editing",
    "case 6 version=delivered delivered=yes guid=yes job=asking",
    "case 7 version=delivered delivered=yes guid=yes job=editing",
    "case 8 version=queued delivered=no guid=no job=editing",
    "case 9 version=queued delivered=no guid=no job=editing",
    "case 10 version=delivered delivered=yes guid=no job=card_out",
)


def T(minutes):
    return datetime(2026, 11, 21, 14, tzinfo=timezone.utc) + timedelta(minutes=minutes)


def fixture(db, media_root):
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE outbox(id INTEGER PRIMARY KEY, chat TEXT, text TEXT, "
               "attachments TEXT, reply_to TEXT, ids_ok INTEGER)")

    def add(chat, text, attachments=(), reply_to=None, *, long_ok=False, ids_ok=False):
        return db.execute(
            "INSERT INTO outbox(chat,text,attachments,reply_to,ids_ok) VALUES (?,?,?,?,?)",
            (chat, text, json.dumps(list(attachments)), reply_to, int(bool(ids_ok))),
        ).lastrowid

    problems = []
    return SimpleNamespace(
        db=db, settings={"mediaRoot": media_root}, requests=openreq.OpenRequests(db),
        outbox=SimpleNamespace(add=add), _owner_chats={CHAT}, _now=lambda: T(10),
        _problem=lambda level, code: problems.append(code), _tx=nullcontext,
        _code=lambda hexdigest: hexdigest[:4], _live_reasons=lambda draft: [],
    )


def observe(i, case, pinned):
    version_state, job_state, current, n, receipt, source = case

    def receipt_for(outbox_id):
        if outbox_id != 7:
            return None
        if source == "raises":
            raise OSError("fixture source unavailable")
        state, digest, minute, guid = receipt
        return {"state": state, "png_sha256": digest, "confirmed_at": T(minute).isoformat(),
                "provider_guid": guid}

    with TemporaryDirectory() as media_root, closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        conv = fixture(db, media_root)
        j = job.Jobs(conv, None, pinned)
        request_id = conv.requests.put(CHAT, "p-req", T(0), skill="npp", texts=["fig jam"],
                                       slots={"intake": {}}, turns=8, attachments=[PHOTO_SHA])
        start, queued, deadline = (T(m).isoformat() for m in (0, 2, 30))
        db.execute("INSERT INTO npp_jobs(job_id,chat,sender,photo_sha,open_request_id,state,created_at,current_version) "
                   "VALUES (?,?,?,?,?,?,?,?)", (JOB, CHAT, "sender-1", PHOTO_SHA, request_id, job_state, start, current))
        segment = db.execute("INSERT INTO npp_segments(job_id,started_by,accepted_at,deadline_at,ended_at,outcome) "
                             "VALUES (?,?,?,?,?,?)", (JOB, "p-seg", start, deadline, queued, "card")).lastrowid
        db.execute("INSERT INTO npp_versions(job_id,n,segment_id,listing_json,listing_sha,patch_json,"
                   "card_png_sha,outbox_id,queued_at,state) VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (JOB, n, segment, "{}", "0" * 64, "{}", CARD_SHA, 7, queued, version_state))
        j.receipt_for = None if source == "absent" else receipt_for
        j.refresh_receipts()
        version = j.version(JOB, n)
        listing = db.execute("SELECT state, current_version FROM npp_jobs WHERE job_id=?", (JOB,)).fetchone()
        delivered = "yes" if version["delivered_at"] else "no"
        guid = "yes" if version["transport_message_id"] else "no"
        line = f"case {i} version={version['state']} delivered={delivered} guid={guid} job={listing['state']}"
        unsafe = False
        if listing["state"] == "card_out":
            active = j.version(JOB, listing["current_version"])
            unsafe = active is None or not active["delivered_at"]
        return line, unsafe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    if args:  # Even the end-of-options marker is not part of this no-argument CLI.
        parser.error("no arguments are accepted")

    failed = False
    try:
        pinned = hass.npp.assets()
        for i, case in enumerate(CASES):
            line, unsafe = observe(i, case, pinned)
            print(line)
            if unsafe:
                print(f"FAIL card-out-without-delivery {i}")
                failed = True
            if line != EXPECTED[i]:
                print(f"FAIL receipt-changed {i}")
                failed = True
    except Exception:
        # An incomplete check fails closed without exposing exception contents.
        print("FAIL check-error")
        failed = True
    print(f"{'FAIL' if failed else 'PASS'} {NAME}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
