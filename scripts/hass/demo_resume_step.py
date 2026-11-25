#!/usr/bin/env python3
"""Recommend the next human review step for one offline listing snapshot.

Run with python3 -B on a quiescent OFF rehearsal copy, not on live state.
REVIEW_CURRENT_PREVIEW: inspect the card and rerun the existing pre-yes gate.
REVIEW_TAKEDOWN: the approved card is served; inspect a scoped takedown for it.
NOT_SERVED: the previously approved card is absent from this catalog. Do not post
or repeat takedown. HOLD: evidence is missing, stale or inconsistent; stop.
This command never prints a confirmation code or sends or performs any action.
"""
from __future__ import annotations

import argparse
import contextlib
import sqlite3
import sys
from pathlib import Path

import demo_served_comparison as served

gate = served.gate


class ResumeParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "demo_resume_step: invalid arguments\n")


def photo_conflict(worktree, records, digests):
    for record in records:
        if record.get("image"):
            digest = served.served_photo_sha(worktree, record)
            if digest is None or digest in digests:
                return True
    return False


def resume(db, worktree, state, media, job, version, held):
    """Only fixed status labels leave this function, never saved data or codes."""
    row = db.execute("SELECT photo_sha, current_version, state, approval_row, chat FROM npp_jobs WHERE job_id=?",
                     (job,)).fetchone()
    if row is None:
        return "HOLD no-such-listing"
    if row["photo_sha"] != held:
        return "HOLD photo-mismatch"
    if version < 1 or row["current_version"] != version:
        return "HOLD version-mismatch"
    card = db.execute("""SELECT state, transport_message_id, outbox_id, change_id, draft_hash, base,
                         image_variant, image_sha256 FROM npp_versions WHERE job_id=? AND n=?""",
                      (job, version)).fetchone()
    if card is None:
        return "HOLD version-mismatch"
    name = gate.listing_name(db, job, version)
    if not isinstance(name, str) or not name.strip():
        return "HOLD listing-has-no-name"
    records = served.served_list(worktree)
    if records is None or any(not isinstance(r.get("name"), str) for r in records):
        return "HOLD catalog-unreadable"
    names = {r["name"] for r in records}

    if row["state"] == "card_out":
        history = db.execute("SELECT 1 FROM npp_approvals WHERE job_id=?", (job,)).fetchone()
        if row["approval_row"] is not None or history:
            return "HOLD approval-history-conflict"
        if not card["transport_message_id"]:
            return "HOLD card-not-delivered"
        events = (e for e in gate._viewer().rows(state) if e["chat"] == row["chat"])
        status, detail = gate.before_yes(db, media, events, job, held, version, names)
        if status != "READY":
            return f"HOLD {detail}"
        if (card["image_variant"] not in ("raw", "house", "polished")
                or not gate.SHA.fullmatch(card["image_sha256"] or "")):
            return "HOLD card-photo-unbound"
        if photo_conflict(worktree, records, {held, card["image_sha256"]}):
            return "HOLD served-state-conflict"
        return "REVIEW_CURRENT_PREVIEW"

    if row["state"] != "published" or card["state"] != "approved":
        return "HOLD listing-not-settled"
    binding = db.execute("""SELECT d.state FROM npp_approvals n
        JOIN approvals a ON a.id=n.approval_id
        JOIN drafts d ON d.row_id=? AND d.change_id=a.change_id AND d.draft_hash=a.draft_hash AND d.base=a.base
        WHERE n.job_id=? AND n.n=? AND n.outbox_id=? AND n.transport_message_id=?
        AND a.chat=? AND d.chat=a.chat AND a.change_id=? AND a.draft_hash=? AND a.base=?
        AND (SELECT count(*) FROM drafts WHERE change_id=d.change_id)=1""",
        (row["approval_row"], job, version, card["outbox_id"], card["transport_message_id"],
         row["chat"], card["change_id"], card["draft_hash"], card["base"])).fetchone()
    if not binding or binding["state"] not in ("applied", "verified", "reverted"):
        return "HOLD approval-unbound"
    approved = served.approved_card(db, job, version)
    if isinstance(approved, str):
        return "HOLD approved-card-missing"
    if name not in names:
        if photo_conflict(worktree, records, {held, approved[1]}):
            return "HOLD served-state-conflict"
        return "NOT_SERVED"
    if binding["state"] == "reverted":
        return "HOLD served-state-conflict"
    if served.compare(worktree, records, *approved):
        return "HOLD served-card-differs"
    return "REVIEW_TAKEDOWN"


def main(argv=None):
    p = ResumeParser(prog="demo_resume_step", description=(__doc__ or "").split("\n\n")[0])
    for name in ("state", "media", "worktree", "photo"):
        p.add_argument(f"--{name}", required=True, type=Path)
    p.add_argument("--job", required=True)
    p.add_argument("--version", required=True, type=int)
    args = p.parse_args(argv)
    try:
        if not gate.JOB.fullmatch(args.job):
            status = "HOLD no-such-listing"
        elif (photo_sha := gate.sha256_file(args.photo)) is None:
            status = "HOLD photo-unreadable"
        else:
            with contextlib.closing(gate.open_conversation(args.state)) as db:
                db.execute("BEGIN")
                status = resume(db, args.worktree, args.state, args.media, args.job, args.version, photo_sha)
    except (OSError, sqlite3.Error, ValueError, TypeError, served.gate._viewer().Refused):
        status = "HOLD could-not-check"
    print(status)
    return int(status.startswith("HOLD "))


if __name__ == "__main__":
    raise SystemExit(main())
