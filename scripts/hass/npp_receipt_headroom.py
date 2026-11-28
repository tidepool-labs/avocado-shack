#!/usr/bin/env python3
"""Measure receipt headroom with a synthetic job and the real NPP writer."""

import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.npp import receipt
from hass.npp.job import Jobs

ROWS = 100
JOB_ID = "abcdef123456"
STAMP = "2026-11-21T02:12:00.000000-08:00"


class FixtureConversation:
    def __init__(self, db, media_root):
        self.db = db
        self.settings = {"mediaRoot": media_root}
        self.problems = []

    def _problem(self, *args):
        self.problems.append(args)


def seed(db):
    db.execute(
        "INSERT INTO npp_jobs (job_id, chat, sender, photo_sha, open_request_id, "
        "state, created_at, closed_at, polish_started_at) "
        "VALUES (?, 'c', 's', ?, 1, 'publish_failed', ?, ?, ?)",
        (JOB_ID, "f" * 64, STAMP, STAMP, STAMP),
    )
    for k in range(ROWS):
        db.execute(
            "INSERT INTO npp_segments (segment_id, job_id, started_by, accepted_at, "
            "deadline_at, ended_at, outcome) VALUES (?, ?, 'p', ?, ?, ?, 'render-failed')",
            (k + 1, JOB_ID, STAMP, STAMP, STAMP),
        )
        db.execute(
            "INSERT INTO npp_versions (job_id, n, parent_n, segment_id, listing_json, "
            "patch_json, listing_sha, image_variant, image_sha256, change_id, draft_hash, "
            "card_png_sha, outbox_id, delivered_at, state) "
            "VALUES (?, ?, NULL, ?, '{}', '{}', ?, 'polished', ?, ?, ?, ?, ?, ?, 'superseded')",
            (JOB_ID, 999999000 + k, k + 1, "e" * 64, "d" * 64, "chg-" + "c" * 12,
             "b" * 64, "a" * 64, 9223372036854775000 + k, STAMP),
        )


def check(findings):
    with TemporaryDirectory() as media_root, closing(sqlite3.connect(":memory:")) as db:
        db.row_factory = sqlite3.Row
        conv = FixtureConversation(db, media_root)
        jobs = Jobs(conv, None, npp.assets(), executor=object())
        seed(db)
        jobs.dirty.add(JOB_ID)
        jobs.write_receipts()

        path = Path(media_root) / "npp" / JOB_ID / "receipt.json"
        try:
            path.lstat()
        except FileNotFoundError:
            missing = True
        else:
            missing = False
        if missing or any("npp-receipt-write-failed" in args for args in conv.problems):
            findings.append("receipt-not-written")
        if not missing:
            size = len(receipt.read_artifact(path))
            cap = receipt.RECEIPT_MAX
            print(f"receipt rows={ROWS} bytes={size} cap={cap}")
            if size * 2 > cap:
                findings.append("receipt-over-half")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    findings = []
    try:
        check(findings)
    except Exception:
        # The checker reports a stable label, not exception text or fixture data.
        findings.append("check-error")
    for reason in findings:
        print(f"FAIL {reason}")
    print("FAIL npp_receipt_headroom" if findings else "PASS npp_receipt_headroom")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
