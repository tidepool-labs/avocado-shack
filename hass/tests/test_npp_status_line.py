"""Offline owner status replies against persisted listing state and the real outbox."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hass import conversation


CHAT, OWNER = "fixture-chat", "owner@example.invalid"
CODE = "4ed1"
NOW = datetime(2026, 1, 1, 18, tzinfo=timezone.utc)
STAMP = NOW.isoformat()


class NppStatusLineTests(unittest.TestCase):
    def setUp(self):
        state = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (state / "config.json").write_text(json.dumps({"settings": {
            "ownerChat": CHAT, "ownerSenders": [OWNER], "approvalTtlSeconds": 600,
            "npp": True, "mediaRoot": str(state / "media"),
        }}), encoding="utf-8")
        self.conv = conversation.Conversation(state, None, conversation.FixtureInterpreter({}),
                                              lambda: NOW, npp_stages=object())
        self.addCleanup(self.conv.db.close)
        self.db = self.conv.db

    def job(self, state, version=None):
        self.db.execute("INSERT INTO npp_jobs(job_id,chat,sender,photo_sha,open_request_id,state,created_at,current_version) "
                        "VALUES (?,?,?,?,1,?,?,?)", (CODE, CHAT, OWNER, "0" * 64, state, STAMP, version))

    def status(self, turn="status"):
        previous = self.db.execute("SELECT COALESCE(MAX(id), 0) FROM outbox").fetchone()[0]
        msg = conversation.Inbound(turn, CHAT, OWNER, "status", received_at=STAMP)
        self.assertEqual(self.conv.handle(msg), "status")
        [(text, attachments)] = self.db.execute("SELECT text,attachments FROM outbox WHERE id>?", (previous,))
        self.assertEqual(json.loads(attachments), [])
        return text

    def test_c1_card_out(self):
        # An unversioned code or the old card's version would send the owner to the wrong approval.
        self.job("card_out", 2)
        self.assertEqual(self.status().splitlines()[0],
                         "Card 4ed1-2 is waiting for your yes (reply yes 4ed1-2, or tell me what to change).")

    def test_c2_asking(self):
        # A raw question ID, unfilled template, or an expired question is not the owner's open prompt.
        self.job("asking")
        for qid, text, state in (
            ("near_maker", "Is that the Blue Spruce Orchard already on the website?", "open"),
            ("selling_price", "What's the selling price?", "expired"),
        ):
            row = self.conv.outbox.add(CHAT, text)
            self.db.execute("INSERT INTO npp_questions VALUES (?,?,?,?,NULL,NULL,?)", (CODE, qid, row, STAMP, state))
        self.assertEqual(self.status().splitlines()[0],
                         "Waiting for your answer: Is that the Blue Spruce Orchard already on the website?")

    def test_c3_working(self):
        # Editing can still carry a prior version; neither state may advertise approval.
        self.job("working")
        for state, version in (("working", None), ("editing", 2)):
            with self.subTest(state=state):
                self.db.execute("UPDATE npp_jobs SET state=?, current_version=? WHERE job_id=?", (state, version, CODE))
                line = self.status(state).splitlines()[0]
                self.assertEqual(line, "I'm still drawing the card for listing 4ed1.")
                self.assertNotRegex(line.lower(), r"\byes\b|approv|\bpost\b")

    def test_c4_rest_unchanged(self):
        # Compare the actual ordinary reply to the suffix; a replacement or second header must not change it.
        ordinary = self.status("without-job")
        self.assertTrue(ordinary.startswith("Everything is ready.\nNothing is waiting for your yes."))
        self.job("retake")
        self.assertEqual(self.status("retake"), "The listing 4ed1 is still open.\n" + ordinary)
        self.db.execute("UPDATE npp_jobs SET state='card_out', current_version=2 WHERE job_id=?", (CODE,))
        self.assertEqual(self.status("delivered").partition("\n")[2], ordinary)
        for state in ("approved", "published", "publish_failed", "cancelled"):
            with self.subTest(state=state):
                self.db.execute("UPDATE npp_jobs SET state=? WHERE job_id=?", (state, CODE))
                self.assertEqual(self.status(state), ordinary)
