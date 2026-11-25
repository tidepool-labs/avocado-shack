#!/usr/bin/env python3
"""Check the host hands the NPP job runner the relay's delivery receipts.

Without the callback `Jobs.dispatch` leaves a card's outbox row unsent, `refresh_receipts` returns at once and every
coded yes is refused as not ready. The one production construction is `hass.host.make_worker`, so this builds a real
worker through it (fixtures only, in a TemporaryDirectory) and asks two questions of the real objects it returns:

1. does `conv.npp.dispatch` queue a card on the worker's relay sender (and does the same store pull it back)?
2. once the same store holds a confirmed receipt for that outbox row, does the worker's own `Jobs` mark the version
   delivered with the receipt's GUID and instant?

Exit 0 and `PASS npp_host_receipt_wiring` only when both are yes; exit 1 with `FAIL <reason>` lines otherwise.
Read-only: nothing outside the TemporaryDirectory is created or changed. No network, process or live service is used.
"""

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import os
from pathlib import Path
import struct
import sys
import tempfile
from unittest import mock
import zlib

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hass import conversation, host, npp, relay  # noqa: E402
from hass.npp import job as npp_job  # noqa: E402

NAME = "npp_host_receipt_wiring"
FIXED = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)  # the one instant: queued, acknowledged and refreshed
JOB, CHAT, VERSION, OUTBOX = "abcd", "c1", 1, 7
TEXT, GUID = "Fixture card", "fixture-guid-0001"


class ProbeError(Exception):
    """The fixture could not be built or read back; reported as `check-error` with no detail."""


def _chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


PNG = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
       + _chunk(b"IDAT", zlib.compress(b"\x00\x10\x20\x30")) + _chunk(b"IEND", b""))


class _Inert:
    """A stand-in for the editor, interpreter, stage port and inbox: nothing here is ever called by the probe."""

    def __init__(self, *args, **kwargs):
        pass


class _Receiver(_Inert):
    def handle(self, *args, **kwargs):
        raise AssertionError("the receiver is not drained by this check")


def _expect(condition):
    if not condition:
        raise ProbeError()


def _private_dir(path):
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)  # exact even with a restrictive umask
    return path


def _run(tmp, attempts):
    state = _private_dir(tmp / "state")
    media_root = _private_dir(state / "screenshots")  # inside the picture folder, so receipt wiring is tested alone
    host_dir = _private_dir(tmp / "host")
    worktree = _private_dir(tmp / "worktree")
    settings = {"npp": True, "skillsMode": "ops-only", "ownerChat": CHAT, "mediaRoot": str(media_root)}
    cfg = {"state": str(state), "approvals": "hold", "previewer": False, "pictures": True}

    def refuse(*args, **kwargs):
        attempts.append(1)
        raise OSError("network and process calls are not allowed")

    store = relay.RelayStore(host_dir)
    worker = None
    try:
        with contextlib.ExitStack() as stack:
            enter = stack.enter_context
            enter(mock.patch.object(host, "_worktree", lambda _cfg: str(worktree)))
            enter(mock.patch.object(host.editor_mod, "content_revision", lambda _root, previous=False: "sha256:fixture"))
            enter(mock.patch.object(host.inbox_mod, "Inbox", _Inert))
            enter(mock.patch.object(host.receiver, "Receiver", _Receiver))
            enter(mock.patch.object(conversation, "load_settings", lambda _sdir, photos=False: dict(settings)))
            enter(mock.patch.object(npp, "stages_for", lambda _conversation, _pinned: _Inert()))
            for owner, name in ((host.socket, "create_connection"), (host.socket, "getaddrinfo"),
                                (host.socket.socket, "connect"), (host.socket.socket, "connect_ex"),
                                (host.subprocess, "Popen"), (os, "system"), (os, "popen")):
                enter(mock.patch.object(owner, name, refuse))
            worker = host.make_worker(cfg, store, editor=_Inert(), build=lambda: _Inert(), clock=lambda: FIXED)
            return _measure(worker, store, attempts)
    finally:
        if worker is not None:
            jobs = getattr(worker.conv, "npp", None)
            if jobs is not None:
                jobs.executor.shutdown(wait=False)
            worker.conv.db.close()
        store.db.close()


def _measure(worker, store, attempts):
    conv, jobs, sender = worker.conv, worker.conv.npp, worker.sender
    _expect(jobs is not None and not attempts)
    path, digest = jobs.artifacts.write_card(JOB, PNG)
    stamp = FIXED.isoformat()
    with conv._tx():
        conv.db.execute("INSERT INTO npp_jobs(job_id, chat, sender, photo_sha, open_request_id, state, created_at, current_version)"
                        " VALUES (?,?,?,?,?,?,?,?)", (JOB, CHAT, "owner", "0" * 64, 1, "working", stamp, VERSION))
        conv.db.execute("INSERT INTO npp_versions(job_id, n, segment_id, listing_json, listing_sha, patch_json, card_png_sha,"
                        " outbox_id, queued_at, state) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (JOB, VERSION, 1, "{}", "0" * 64, "{}", digest, OUTBOX, stamp, "queued"))

    def bound():
        return store.db.execute("SELECT relay_id FROM card_receipt WHERE outbox_id=?", (OUTBOX,)).fetchone()

    # 1. the worker's own runner hands the card to the worker's own sender
    returned = jobs.dispatch(sender, {"id": OUTBOX, "chat": CHAT, "attachments": "[]"}, TEXT)
    queued = bound() is not None
    if not queued:  # fallback: queue the same card directly, only so receipt consumption is still measured; never counts as dispatch
        sender.send_card(OUTBOX, CHAT, TEXT, str(path), digest)
    pulled = store.pull(5, int(FIXED.timestamp()), card_receipts=True)
    _expect(len(pulled) == 1 and pulled[0].get("card") is True)
    item = pulled[0]
    _expect(bound() == (item["id"],))
    shot = store.picture(item["id"], 0)
    matched = item["chat"] == CHAT and item["text"] == TEXT and shot == (digest, PNG)
    dispatched = returned is True and queued and matched

    # 2. a confirmed receipt in the same store reaches the same persisted version through the worker's own jobs
    jobs.refresh_receipts()
    before = jobs.version(JOB, VERSION)
    _expect(before["state"] == "queued" and before["delivered_at"] is None and before["transport_message_id"] is None)
    store.acknowledge_receipt(item["id"], {"outcome": "sent", "png_sha256": digest, "provider_guid": GUID}, FIXED)
    receipt = store.receipt_for(OUTBOX)
    _expect(receipt["state"] == "confirmed" and receipt["png_sha256"] == digest and receipt["provider_guid"] == GUID
            and npp_job.instant(receipt["confirmed_at"]) == FIXED)
    jobs.refresh_receipts()
    after = jobs.version(JOB, VERSION)
    consumed = (after["state"] == "delivered" and after["transport_message_id"] == GUID
                and npp_job.instant(after["delivered_at"]) == FIXED)
    _expect(not attempts)
    return dispatched, consumed


def measure():
    """(card_dispatched, relay_receipt_consumed) from one fixture run; raises ProbeError when the probe cannot complete."""
    attempts = []
    try:
        with tempfile.TemporaryDirectory() as raw:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return _run(Path(raw).resolve(), attempts)
    except Exception:  # noqa: BLE001 - any failure of the probe is one fixed finding, never its text
        raise ProbeError() from None


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        dispatched, consumed = measure()
    except ProbeError:
        print("FAIL check-error")
        print(f"FAIL {NAME}")
        return 1
    yes = {True: "yes", False: "no"}
    print(f"host card_dispatched={yes[dispatched]} relay_receipt_consumed={yes[consumed]}")
    findings = [reason for ok, reason in ((dispatched, "card-not-dispatched"), (consumed, "receipt-unwired")) if not ok]
    for reason in findings:
        print(f"FAIL {reason}")
    print(f"FAIL {NAME}" if findings else f"PASS {NAME}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
