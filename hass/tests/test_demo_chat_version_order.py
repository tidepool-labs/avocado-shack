"""H43: exercise late preview confirmation with synthetic files and no live services."""

import base64
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
import struct
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import zlib

from hass.npp.job import Jobs
from scripts.hass import npp_chat_page


JOB = "a043"
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def at(seconds):
    return (T0 + timedelta(seconds=seconds)).isoformat()


def pixel(rgb):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0" + rgb)) + chunk(b"IEND", b""))


class DemoChatVersionOrderTests(unittest.TestCase):
    def test_later_confirmation_keeps_v1_superseded_and_keeps_each_bubbles_original_evidence(self):
        # Unlike the single-card receipt tests, this crosses the durable receipt → viewer boundary
        # with version and arrival order opposed. Sorting on n or replacing either time/PNG fails.
        root = Path(self.enterContext(TemporaryDirectory()))
        db = self.enterContext(closing(sqlite3.connect(":memory:")))
        db.row_factory = sqlite3.Row
        receipts = {}
        now = T0 + timedelta(seconds=8)
        clock = SimpleNamespace(db=db, settings={"mediaRoot": root}, _now=lambda: now, _tx=lambda: db)
        jobs = Jobs(clock, None, ({"assets": {}}, None, {}), receipt_for=receipts.get)
        self.addCleanup(jobs.executor.shutdown)
        old, current = pixel(b"\xff\0\0"), pixel(b"\0\0\xff")
        old_path, old_sha = jobs.artifacts.write_card(JOB, old)
        current_path, current_sha = jobs.artifacts.write_card(JOB, current)
        with db:
            db.execute("INSERT INTO npp_jobs (job_id,chat,sender,photo_sha,open_request_id,state,created_at,current_version)"
                       " VALUES (?,?,?,?,1,'editing',?,2)", (JOB, "fixture-chat", "owner", "0" * 64, at(0)))
            db.executemany("INSERT INTO npp_versions (job_id,n,segment_id,listing_json,listing_sha,patch_json,"
                           "card_png_sha,outbox_id,queued_at,state) VALUES (?,?,?,'{}',?,'{}',?,?,?,?)",
                           [(JOB, n, n, "0" * 64, sha, row, at(queued), state) for n, sha, row, queued, state in
                            ((1, old_sha, 41, 0, "superseded"), (2, current_sha, 42, 5, "queued"))])

        def confirm(row, sha, seconds):
            receipts[row] = dict(state="confirmed", png_sha256=sha, confirmed_at=at(seconds),
                                 provider_guid=f"fixture-{row}")
            jobs.refresh_receipts()
            jobs.write_receipts()

        def event(n, seconds, sha):
            return dict(id=n, utc=at(seconds), chat="fixture-chat", sender="Hass", direction="out",
                        kind="card", text="Fixture preview", attachments=[sha], disposition="sent")

        def view(*events):
            # Exercise the real JSONL reader even when the export's line order is reversed.
            export = root / "export.jsonl"
            export.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
            directory = old_path.parent
            files = (export, old_path, current_path, directory / "receipt.json")
            before = [p.read_bytes() for p in files]
            page, missing, ambiguous = npp_chat_page.render(
                npp_chat_page.read_events(export, "fixture-chat"), directory,
                npp_chat_page.load_receipts(directory.parent))
            self.assertEqual([p.read_bytes() for p in files], before, "viewing changed the copied evidence")
            self.assertEqual((missing, ambiguous), ([], []))
            return re.findall(r"<article\b.*?</article>", page, re.DOTALL)

        def check_bubble(bubble, version, confirmed_at, observed_at, png):
            self.assertIn(version + " · " + at(confirmed_at), bubble)
            self.assertIn("Hass · " + at(observed_at), bubble)
            [encoded] = re.findall(r'src="data:image/png;base64,([^\"]+)"', bubble)
            self.assertEqual(base64.b64decode(encoded, validate=True), png)

        timely = event(1, 8, current_sha)
        confirm(42, current_sha, 7)
        [v2] = view(timely)  # Both files already exist, but v1 has not arrived in chat.
        check_bubble(v2, f"{JOB}-2 delivered", 7, 8, current)

        now = T0 + timedelta(seconds=32)
        confirm(41, current_sha, 30)  # v2's bytes cannot confirm the older outbox row.
        self.assertIsNone(jobs.version(JOB, 1)["delivered_at"])
        confirm(41, old_sha, 30)
        v2, v1 = view(event(2, 32, old_sha), timely)
        check_bubble(v2, f"{JOB}-2 delivered", 7, 8, current)
        check_bubble(v1, f"{JOB}-1 superseded", 30, 32, old)
        self.assertEqual(jobs.one("SELECT current_version FROM npp_jobs WHERE job_id = ?", JOB)[0], 2)
        self.assertEqual(jobs.one("SELECT count(*) FROM npp_approvals")[0], 0)
