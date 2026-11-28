#!/usr/bin/env python3
"""Replay synthetic listing edits and check that the private intake never shrinks."""

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
from hass.npp.private_numbers import Finance
from hass.skills import openreq


NAME = "npp_private_screen_sticky"
CHAT = "chat-owner"
STEPS = (
    (Finance("fig jam", "5 each", (0, 2), frozenset({"3"}), has_cost=True), ["a" * 64], True),
    (Finance("call it fig jam"), [], False),
    (Finance("put it in pantry", private=frozenset({"12"}), has_qty=True), [], False),
    (Finance("make it", "6 per lb", (0, 2)), [], True),
    (Finance("from miners"), [], True),
    (Finance("new picture"), ["b" * 64], False),
    (Finance("paid", private=frozenset({"3.50"})), [], False),
)
EXPECTED = (
    "step 0 npp-working price='5' sold_by='item' private=['3'] cost=yes qty=no texts=1 turn=start",
    "step 1 npp-working price='5' sold_by='item' private=['3'] cost=yes qty=no texts=2 turn=edit",
    "step 2 npp-working price='5' sold_by='item' private=['12', '3'] cost=yes qty=yes texts=3 turn=edit",
    "step 3 npp-working price='6' sold_by='pound' private=['12', '3'] cost=yes qty=yes texts=4 turn=edit",
    "step 4 npp-working price=None sold_by=None private=['12', '3'] cost=yes qty=yes texts=5 turn=edit",
    "step 5 npp-working price=None sold_by=None private=['12', '3'] cost=yes qty=yes texts=6 turn=photo",
    "step 6 npp-working price=None sold_by=None private=['12', '3', '3.5'] cost=yes qty=yes texts=7 turn=edit",
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

    _tx = staticmethod(nullcontext)

    def _code(self, hexdigest):
        return hexdigest[:4]

    def _live_reasons(self, draft):
        return []


def yes_no(value):
    return "yes" if value else "no"


def check():
    failed = False
    with TemporaryDirectory() as media_root, closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        conv = FixtureConversation(db, media_root)
        jobs = job.Jobs(conv, None, hass.npp.assets())
        previous_private, previous_cost, previous_qty = set(), False, False
        for i, ((finance, photos, replace_price), expected) in enumerate(zip(STEPS, EXPECTED, strict=True)):
            now = T(i + 1)
            msg = SimpleNamespace(provider_id=f"p-in-{i}", received_at=now.isoformat(), reply_to=None, chat=CHAT)
            result = jobs.input(msg, "sender-1", now, now, finance, photos, replace_price=replace_price)
            request = conv.requests.get(CHAT, now)
            turn = db.execute("SELECT kind FROM npp_turns WHERE provider_id = ?", (msg.provider_id,)).fetchone()
            if request is None or turn is None:
                raise ValueError("missing intake request or recorded turn")
            slot = request["slots"]["intake"]
            private, cost, qty = slot["private"], slot["has_cost"], slot["has_qty"]
            line = (f"step {i} {result} price={slot['price']!r} sold_by={slot['sold_by']!r} "
                    f"private={private!r} cost={yes_no(cost)} qty={yes_no(qty)} "
                    f"texts={len(request['texts'])} turn={turn['kind']}")
            print(line)
            current_private = set(private)
            if previous_private - current_private or (previous_cost and not cost) or (previous_qty and not qty):
                print(f"FAIL declassified {i}")
                failed = True
            if line != expected:
                print(f"FAIL slot-changed {i}")
                failed = True
            previous_private, previous_cost, previous_qty = current_private, cost, qty
    return not failed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    parser.parse_args(args)
    if args:  # argparse otherwise accepts a bare "--".
        parser.error("no arguments accepted")
    try:
        passed = check()
    except Exception:
        # Report an incomplete check without echoing exception contents.
        print("FAIL check-error")
        passed = False
    print(f"{'PASS' if passed else 'FAIL'} {NAME}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
