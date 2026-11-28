"""Offline drift check for canonical NPP listing-version rows."""

import argparse
from contextlib import closing, nullcontext
from datetime import datetime, timedelta, timezone
import hashlib
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


CASES = (
    (None, {"b": 1, "a": "fixture"}, None),
    (1, {"name": "Fig Jam"}, {"name": "Fig Jam"}),
    (None, {"name": "Caf\u00e9 Jam"}, {}),
    (None, {"price": float("nan")}, None),
    (2, {"z": {"b": 1, "a": 2}, "a": [3, 1]}, {"z": {"b": 1}}),
)
EXPECTED = (
    'case 0 n=1 parent=None listing={"a":"fixture","b":1} patch={} state=building current=1',
    'case 1 n=2 parent=1 listing={"name":"Fig Jam"} patch={"name":"Fig Jam"} state=building current=2',
    r'case 2 n=1 parent=None listing={"name":"Caf\u00e9 Jam"} patch={} state=building current=1',
    'case 3 error=ValueError rows=0 current=None',
    'case 4 n=3 parent=2 listing={"a":[3,1],"z":{"a":2,"b":1}} patch={"z":{"b":1}} state=building current=3',
)
CHAT = "chat-owner"
JOB_ID = "a1b2"
PHOTO = "a" * 64


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


def fixture(db, media_root, current_version):
    problems = []
    conv = SimpleNamespace(
        db=db, settings={"mediaRoot": media_root}, requests=openreq.OpenRequests(db),
        outbox=Outbox(db), _owner_chats={CHAT}, _now=lambda: T(10),
        _problem=lambda level, code: problems.append(code), _tx=nullcontext,
        _code=lambda hexdigest: hexdigest[:4], _live_reasons=lambda draft: [],
    )
    jobs = job.Jobs(conv, None, npp.assets())
    request_id = conv.requests.put(CHAT, "p-req", T(0), skill="npp", texts=["fig jam"],
                                   slots={"intake": {}}, turns=8, attachments=[PHOTO])
    accepted, deadline = T(0).isoformat(), T(30).isoformat()
    db.execute("INSERT INTO npp_jobs(job_id,chat,sender,photo_sha,open_request_id,state,created_at,current_version) "
               "VALUES (?,?,?,?,?,'working',?,?)",
               (JOB_ID, CHAT, "sender-1", PHOTO, request_id, accepted, current_version))
    # Prior versions belong to closed segments; freeze gets a fresh open one.
    for n in range(1, (current_version or 0) + 1):
        sid = db.execute("INSERT INTO npp_segments(job_id,started_by,accepted_at,deadline_at,ended_at) "
                         "VALUES (?,'p-seg',?,?,?)", (JOB_ID, accepted, deadline, accepted)).lastrowid
        db.execute("INSERT INTO npp_versions(job_id,n,parent_n,segment_id,listing_json,listing_sha,patch_json,state) "
                   "VALUES (?,?,?,?,'{}',?,'{}','superseded')", (JOB_ID, n, n - 1 or None, sid, "0" * 64))
    db.execute("INSERT INTO npp_segments(job_id,started_by,accepted_at,deadline_at) "
               "VALUES (?,'p-seg',?,?)", (JOB_ID, accepted, deadline))
    return jobs


def check_case(index, current_version, listing, patch):
    with TemporaryDirectory() as media_root, closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        jobs = fixture(db, media_root, current_version)
        select_job = "SELECT * FROM npp_jobs WHERE job_id=?"
        job_row = jobs.one(select_job, JOB_ID)
        segment = jobs.one("SELECT * FROM npp_segments WHERE job_id=? AND ended_at IS NULL", JOB_ID)
        plan = job.Plan(listing=listing, patch=patch)
        try:
            version = jobs.freeze(job_row, segment, plan)
        except ValueError:
            count = db.execute("SELECT COUNT(*) FROM npp_versions").fetchone()[0]
            current = jobs.one(select_job, JOB_ID)["current_version"]
            return f"case {index} error=ValueError rows={count} current={current}", False

        current = jobs.one(select_job, JOB_ID)["current_version"]
        stored = version["listing_json"]
        line = (f"case {index} n={version['n']} parent={version['parent_n']} listing={stored} "
                f"patch={version['patch_json']} state={version['state']} current={current}")
        return line, version["listing_sha"] != hashlib.sha256(stored.encode("utf-8")).hexdigest()


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    try:
        for index, case in enumerate(CASES):
            line, sha_mismatch = check_case(index, *case)
            print(line)
            if sha_mismatch:
                print(f"FAIL sha-mismatch {index}")
                failed = True
            if line != EXPECTED[index]:
                print(f"FAIL freeze-changed {index}")
                failed = True
    except Exception:
        print("FAIL check-error")
        failed = True
    print(f"{'FAIL' if failed else 'PASS'} npp_version_freeze_rows")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
