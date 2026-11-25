#!/usr/bin/env python3
"""Check a frozen NPP card PNG can be read by the relay that sends it.

The card is written under the media store, while the relay reads pictures only
from its screenshots folder. This offline probe sends one card from each place
through a real local relay store and reports whether the picture travelled and
the receipt was confirmed. Run as `python3 -B scripts/hass/npp_card_relay_picture.py`.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import struct
import sys
import tempfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import relay  # noqa: E402
from hass.npp import receipt  # noqa: E402

TRAILER = "npp_card_relay_picture"
NOW_EPOCH = 1_700_000_000
MEDIA_OUTBOX_ID = 7
SCREENSHOTS_OUTBOX_ID = 8
CHAT = "c1"
GUID = "fixture-guid"


class ProbeError(Exception):
    """The probe could not complete its relay lifecycle."""


def synthetic_png():
    """A valid 1x1 PNG built from the standard library."""
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixel = zlib.compress(b"\x00\xff\xff\xff")
    return relay.PNG_SIG + chunk(b"IHDR", header) + chunk(b"IDAT", pixel) + chunk(b"IEND", b"")


def send_and_ack(store, sender, outbox_id, path, png, sha):
    """Queue one card, pull it as the Mac does, ACK it as sent; return (pictured, confirmed)."""
    rid = sender.send_card(outbox_id, CHAT, "Fixture card", str(path), sha)
    if store.receipt_for(outbox_id)["state"] != "pending":
        raise ProbeError("receipt was not pending after enqueue")
    pulled = store.pull(1, NOW_EPOCH, card_receipts=True)  # without this pull the ACK is a no-op
    if len(pulled) != 1 or pulled[0].get("id") != rid or pulled[0].get("card") is not True:
        raise ProbeError("pull did not return this card")
    shots = pulled[0].get("shots")
    pictured = shots == [{"idx": 0, "sha256": sha, "size": len(png)}] and store.picture(rid, 0) == (sha, png)
    now_utc = datetime.fromtimestamp(NOW_EPOCH, timezone.utc)
    store.acknowledge_receipt(rid, {"outcome": "sent", "png_sha256": sha, "provider_guid": GUID}, now_utc)
    record = store.receipt_for(outbox_id)
    if record["state"] not in ("failed", "confirmed"):
        raise ProbeError("receipt still pending after ACK")
    confirmed = (record["state"] == "confirmed" and record["png_sha256"] == sha
                 and record["provider_guid"] == GUID)
    return rid, bool(pictured), confirmed


def measure():
    """{'media': (pictured, confirmed), 'screenshots': (pictured, confirmed)}; ProbeError or OSError if incomplete."""
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw).resolve()
        host, shots_dir, media = root / "host", root / "state" / "screenshots", root / "media"
        host.mkdir(mode=0o700)
        shots_dir.mkdir(parents=True)
        media.mkdir()
        png = synthetic_png()
        path, sha = receipt.Artifacts(media).write_card("abcd", png)
        control = shots_dir / "fixture.png"
        control.write_bytes(png)
        store = relay.RelayStore(host)
        try:
            sender = relay.RelaySender(store, (CHAT,), lambda: NOW_EPOCH, shots_dir, None)
            media_rid, *media_result = send_and_ack(store, sender, MEDIA_OUTBOX_ID, path, png, sha)
            shots_rid, *shots_result = send_and_ack(store, sender, SCREENSHOTS_OUTBOX_ID, control, png, sha)
            if media_rid == shots_rid:
                raise ProbeError("the control reused the media relay id")
        finally:
            store.db.close()
    return {"media": tuple(media_result), "screenshots": tuple(shots_result)}


def yes_no(value):
    return "yes" if value else "no"


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    try:
        result = measure()
        media, shots = result["media"], result["screenshots"]
    except Exception:  # any setup, I/O or lifecycle failure is one named finding, never a traceback
        print("FAIL check-error")
        print(f"FAIL {TRAILER}")
        return 1
    print(f"relay media_card pictured={yes_no(media[0])} confirmed={yes_no(media[1])}")
    print(f"relay screenshots_card pictured={yes_no(shots[0])} confirmed={yes_no(shots[1])}")
    findings = []
    if not all(shots):  # fail closed: a broken control means the media result proves nothing
        findings.append("FAIL reference-broken")
    else:
        if not media[0]:
            findings.append("FAIL card-picture-dropped")
        if not media[1]:
            findings.append("FAIL card-unconfirmed")
    for line in findings:
        print(line)
    print(f"FAIL {TRAILER}" if findings else f"PASS {TRAILER}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
