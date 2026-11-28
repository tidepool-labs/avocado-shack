#!/usr/bin/env python3
"""Check the NPP listing-card dispatch gate with offline fixtures only."""

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

from hass import media, npp  # noqa: E402
from hass.npp import job  # noqa: E402
from hass.skills import openreq  # noqa: E402

CHAT = "chat-owner"
JOB_ID = "a1b2"
PHOTO_SHA = "a" * 64
TEXT = "card text"

# Version state, job state, current version, version n, send_card, receipt source,
# stored card condition, and whether the outbox row belongs to a version.
CASES = (
    ("queued", "editing", 1, 1, True, True, "ok", True),
    ("queued", "card_out", 1, 1, True, True, "ok", True),
    ("superseded", "editing", 1, 1, True, True, "ok", True),
    ("queued", "editing", 2, 1, True, True, "ok", True),
    ("queued", "editing", 1, 1, False, True, "ok", True),
    ("queued", "editing", 1, 1, True, False, "ok", True),
    ("queued", "editing", 1, 1, True, True, "missing", True),
    ("queued", "editing", 1, 1, True, True, "tampered", True),
    ("queued", "working", 1, 1, True, True, "ok", False),
)
EXPECTED = (
    "case 0 result=True sent=send_card",
    "case 1 result=False sent=none",
    "case 2 result=False sent=none",
    "case 3 result=False sent=none",
    "case 4 result=False sent=none",
    "case 5 result=False sent=none",
    "case 6 result=False sent=none",
    "case 7 result=False sent=none",
    "case 8 result=True sent=send",
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
            "INSERT INTO outbox(chat, text, attachments, reply_to, ids_ok) VALUES (?, ?, ?, ?, ?)",
            (chat, text, json.dumps(list(attachments)), reply_to, int(ids_ok)),
        ).lastrowid


def run_case(case):
    version_state, job_state, current, version, has_send_card, has_receipt, card_file, card_row = case
    with TemporaryDirectory() as root, closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        problems = []
        conv = SimpleNamespace(
            db=db, settings={"mediaRoot": str(Path(root).resolve())},
            requests=openreq.OpenRequests(db), outbox=FixtureOutbox(db),
            _owner_chats={CHAT}, _now=lambda: T(10),
            _problem=lambda level, code: problems.append(code), _tx=nullcontext,
            _code=lambda hexdigest: hexdigest[:4], _live_reasons=lambda draft: [],
        )
        j = job.Jobs(conv, None, npp.assets())
        request_id = conv.requests.put(CHAT, "p-req", T(0), skill="npp", texts=["fig jam"],
                                       slots={"intake": {}}, turns=8, attachments=[PHOTO_SHA])
        db.execute(
            "INSERT INTO npp_jobs(job_id, chat, sender, photo_sha, open_request_id, state, created_at, current_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (JOB_ID, CHAT, "sender-1", PHOTO_SHA, request_id, job_state, T(0).isoformat(), current),
        )
        png = media.KINDS["png"] + b"fixture-card"
        path, digest = j.artifacts.write_card(JOB_ID, png)
        outbox_id = conv.outbox.add(CHAT, TEXT, [str(path)], ids_ok=True)
        if card_file == "missing":
            digest = "e" * 64  # The version points to a digest with no stored artifact.
        elif card_file == "tampered":
            path.chmod(0o600)
            path.write_bytes(png + b"x")
        if card_row:
            segment_id = db.execute(
                "INSERT INTO npp_segments(job_id, started_by, accepted_at, deadline_at, ended_at) VALUES (?, ?, ?, ?, ?)",
                (JOB_ID, "p-seg", T(0).isoformat(), T(30).isoformat(), T(10).isoformat()),
            ).lastrowid
            db.execute(
                "INSERT INTO npp_versions(job_id, n, segment_id, listing_json, listing_sha, patch_json, "
                "card_png_sha, outbox_id, queued_at, state) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (JOB_ID, version, segment_id, "{}", "0" * 64, "{}", digest, outbox_id, T(10).isoformat(), version_state),
            )
        calls = []
        adapter = SimpleNamespace(send=lambda chat, text, attachments: calls.append("send"))
        if has_send_card:
            adapter.send_card = lambda row_id, chat, text, path, sha: calls.append("send_card")
        j.receipt_for = (lambda row: None) if has_receipt else None
        row = db.execute("SELECT * FROM outbox WHERE id = ?", (outbox_id,)).fetchone()
        return j.dispatch(adapter, row, TEXT), calls


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    if args:
        parser.error("no arguments are accepted")

    failed = False
    try:
        for i, case in enumerate(CASES):
            result, calls = run_case(case)
            line = f"case {i} result={result} sent={'+'.join(calls) or 'none'}"
            print(line)
            if result is False and calls:
                print(f"FAIL sent-on-false {i}")
                failed = True
            if case[-1] and "send" in calls:
                print(f"FAIL card-via-send {i}")
                failed = True
            if line != EXPECTED[i]:
                print(f"FAIL dispatch-changed {i}")
                failed = True
    except Exception:
        # A check that could not run must not pass or expose exception contents.
        print("FAIL check-error")
        failed = True
    print("FAIL npp_card_dispatch_gate" if failed else "PASS npp_card_dispatch_gate")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
