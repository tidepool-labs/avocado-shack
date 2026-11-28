"""Offline stop/resume contract at the real Conversation, Jobs and outbox boundaries."""
from datetime import timedelta
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from hass import conversation
from hass.npp.job import Card, Plan
from hass.tests import test_npp_job as fixtures


QUESTION = "What's the selling price?"


class ListingReplay:
    def __init__(self, directory):
        self.now = fixtures.T0
        self.serial = 0
        self.executor = fixtures.Scheduler()
        self.sink = Mock(spec=["send", "send_card"])
        self.receipts = {}
        self.editor = Mock(spec=["show", "apply"])
        self.editor.apply.return_value = {"result": "applied"}

        root = Path(directory)
        (root / "config.json").write_text(json.dumps({
            "settings": {**fixtures.SETTINGS, "mediaRoot": str(root / "pictures"),
                         "npp": True, "houseRender": True, "photo_polish": True},
        }), encoding="utf-8")
        photos = Mock(spec=["fetch"])
        photos.fetch.return_value = [fixtures.JPG]
        self.conv = conversation.Conversation(
            root, self.editor, conversation.FixtureInterpreter({}), lambda: self.now,
            photos=photos, npp_stages=self, npp_executor=self.executor,
            npp_receipt_for=self.receipts.get,
        )

    def takes_turn(self, text, state):
        return text.startswith("sell ")

    def plan(self, work):
        price = work.request["slots"]["intake"]["price"]
        return (Plan(questions=(("selling_price", QUESTION),), identified=True)
                if price is None else Plan(listing={"price": price}))

    def render(self, work, listing):
        sha = work.request["attachments"][0]
        path = "assets/products/fixture.jpg"
        draft = {"assets": {path: "sha256:" + sha}, "change_id": "fixture-change",
                 "draft_hash": "sha256:" + hashlib.sha256(listing["price"].encode()).hexdigest(),
                 "base": "a" * 40, "ops": [], "records": []}
        self.editor.show.return_value = {"draft": draft}
        return Card(draft, fixtures.PNG, "raw", path, sha)

    @property
    def job(self):
        return self.conv.db.execute("SELECT * FROM npp_jobs").fetchone()

    @property
    def version(self):
        jobs = self.conv.npp
        assert jobs is not None
        return jobs.version(self.job["job_id"], 1)

    def say(self, text, *, photo=False):
        self.serial += 1
        self.now += timedelta(seconds=1)
        msg = conversation.Inbound(f"fixture-{self.serial}", fixtures.CHAT, fixtures.OWNER, text,
                                   received_at=self.now.isoformat(), attachments=int(photo))
        return self.conv.handle(msg, forwarded_at=self.now)

    def flush(self):
        return self.conv.flush(self.sink)

    def pump(self):
        jobs = self.conv.npp
        assert jobs is not None
        jobs.pump()

    def receipt(self):
        version = self.version
        self.now += timedelta(seconds=1)
        self.receipts[version["outbox_id"]] = {
            "state": "confirmed", "png_sha256": version["card_png_sha"],
            "provider_guid": "fixture-card-receipt", "confirmed_at": self.now.isoformat(),
        }

    def outbox(self):
        return [tuple(row) for row in self.conv.db.execute("SELECT id, sent_at FROM outbox ORDER BY id")]


class StopPauseTests(unittest.TestCase):
    def setUp(self):
        # Never run an image model; count attempts at the actual launch boundary.
        patcher = patch.object(conversation.photo_polish, "start")
        self.image_edit = patcher.start()
        self.addCleanup(patcher.stop)

    def replay(self):
        scratch = TemporaryDirectory(prefix="npp-stop-")
        self.addCleanup(scratch.cleanup)
        replay = ListingReplay(scratch.name)
        self.addCleanup(replay.conv.db.close)
        self.assertIsNotNone(replay.conv.npp)
        return replay

    def stop(self, replay):
        before = replay.outbox()
        self.assertEqual(replay.say("stop"), "pause")
        self.assertTrue(replay.conv._paused())
        after = replay.outbox()
        self.assertEqual(after[:-1], before)
        self.assertIsNone(after[-1][1])
        return after[-1][0]  # Stop acknowledgement is not a job reply.

    def start_render(self, replay, *, new_photo=True):
        self.assertEqual(replay.say("sell $2 each", photo=new_photo), "npp-working")
        self.assertEqual(replay.flush(), 0)  # submit plan
        replay.executor.run()
        self.assertEqual(replay.flush(), 0)  # consume plan and freeze version
        self.assertEqual(replay.flush(), 0)  # submit render
        self.assertEqual(replay.version["state"], "building")
        self.assertEqual(len(replay.executor.steps), 1)

    def ready_card(self, replay):
        self.start_render(replay)
        replay.executor.run()
        # Pump independently to leave a real outbox row pending before the next flush.
        replay.pump()
        version = replay.version
        self.assertEqual(version["state"], "queued")
        self.assertIsNone(version["delivered_at"])
        self.assertIn((version["outbox_id"], None), replay.outbox())
        replay.sink.send_card.assert_not_called()

    def test_c1_stop_holds_replies(self):
        # A completed worker, pending text/card, and late receipt must each be held and released once.
        for window in ("late-question", "queued-question", "queued-card", "late-receipt"):
            with self.subTest(window=window):
                replay = self.replay()
                question = window.endswith("question")
                pending = None
                if question:
                    self.assertEqual(replay.say("Fixture jam", photo=True), "npp-working")
                    self.assertEqual(replay.flush(), 0)
                    self.assertEqual(len(replay.executor.steps), 1)
                    if window == "queued-question":
                        replay.executor.run()
                        replay.pump()
                        [(pending, sent_at)] = replay.outbox()
                        self.assertIsNone(sent_at)
                else:
                    self.ready_card(replay)
                    pending = replay.version["outbox_id"]
                    if window == "late-receipt":
                        self.assertEqual(replay.flush(), 1)
                        replay.sink.send_card.assert_called_once()
                self.assertEqual(replay.job["state"], "asking" if window == "queued-question" else "working")
                before = replay.outbox()
                ack = self.stop(replay)
                replay.sink.reset_mock()
                if window == "late-question":
                    replay.executor.run()
                elif window == "late-receipt":
                    replay.receipt()

                self.assertEqual((replay.flush(), replay.flush()), (1, 0))  # only the stop acknowledgement
                self.assertTrue(dict(replay.outbox())[ack])
                self.assertEqual([row for row in replay.outbox() if row[0] != ack], before)
                replay.sink.send.assert_called_once()
                replay.sink.send_card.assert_not_called()
                if not question:
                    self.assertEqual(replay.version["state"], "queued")
                    self.assertIsNone(replay.version["delivered_at"])

                replay.sink.reset_mock()
                self.assertEqual(replay.say("resume changes"), "resume")
                self.assertEqual((replay.flush(), replay.flush()), (1 if window == "late-receipt" else 2, 0))
                if pending is not None:
                    self.assertTrue(dict(replay.outbox())[pending])
                if question:
                    sent_questions = [call for call in replay.sink.send.call_args_list if call.args[1] == QUESTION]
                    self.assertEqual(len(sent_questions), 1)
                    replay.sink.send_card.assert_not_called()
                elif window == "queued-card":
                    replay.sink.send_card.assert_called_once()
                    self.assertEqual(replay.sink.send_card.call_args.args[0], pending)
                else:
                    replay.sink.send_card.assert_not_called()
                    self.assertEqual(replay.version["state"], "delivered")
                    self.assertEqual(replay.version["transport_message_id"], "fixture-card-receipt")

    def test_c2_no_publish_paused(self):
        # An actually delivered card is otherwise approvable: a queued/unknown code would prove nothing.
        replay = self.replay()
        self.ready_card(replay)
        self.assertEqual(replay.flush(), 1)
        replay.receipt()
        self.assertEqual(replay.flush(), 0)
        version = dict(replay.version)
        self.assertEqual(version["state"], "delivered")
        self.stop(replay)
        self.assertEqual(replay.flush(), 1)
        replay.sink.reset_mock()
        code = replay.job["job_id"]
        expected = "Changes are paused, so nothing will be saved yet. Say resume changes first, then yes."
        for suffix in ("", "-1"):
            self.assertEqual(replay.say(f"yes {code}{suffix}"), "no-target")
            self.assertEqual(replay.flush(), 1)
            replay.sink.send.assert_called_once_with(fixtures.CHAT, expected, [])
            self.assert_unpublished(replay)
            replay.sink.reset_mock()
            self.assertEqual(replay.job["state"], "card_out")
            self.assertEqual(dict(replay.version), version)
        self.assertEqual(replay.say("resume changes"), "resume")
        self.assert_unpublished(replay)  # resume itself never applies a held yes
        self.assertEqual(replay.say(f"yes {code}-1"), "approved")
        replay.editor.apply.assert_called_once_with(version["change_id"], version["draft_hash"])
        self.assertEqual(replay.job["state"], "published")

    def assert_unpublished(self, replay):
        replay.editor.apply.assert_not_called()
        replay.sink.send_card.assert_not_called()
        for table in ("approvals", "npp_approvals"):
            self.assertEqual(replay.conv.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.assertIsNone(replay.job["approval_row"])

    def test_c3_resume_once(self):
        # Resume the same in-flight render rather than opening a new segment or launching a second photo edit.
        replay = self.replay()
        self.assertEqual(replay.say("Fixture jam", photo=True), "npp-working")
        self.assertEqual(replay.flush(), 0)
        replay.executor.run()
        self.assertEqual(replay.flush(), 1)  # first segment asks for price
        replay.sink.send.assert_called_once_with(fixtures.CHAT, QUESTION, [])
        self.start_render(replay, new_photo=False)
        version = replay.version
        self.image_edit.assert_called_once()
        self.stop(replay)
        self.assertEqual(replay.flush(), 1)
        self.assertEqual(replay.say("resume changes"), "resume")
        self.assertFalse(replay.conv._paused())
        self.assertEqual(len(replay.executor.steps), 1)
        replay.executor.run()
        self.assertEqual(replay.flush(), 2)  # resume acknowledgement and the second segment's card
        replay.receipt()
        self.assertEqual((replay.flush(), replay.flush()), (0, 0))
        replay.sink.send_card.assert_called_once()
        self.assertEqual(replay.version["state"], "delivered")
        self.assertEqual(replay.version["segment_id"], version["segment_id"])
        self.assertEqual(replay.version["image_sha256"], replay.job["photo_sha"])
        counts = replay.conv.db.execute(
            "SELECT COUNT(t.reply_outbox_id) FROM npp_segments s LEFT JOIN npp_turns t USING(segment_id) "
            "GROUP BY s.segment_id ORDER BY s.segment_id"
        ).fetchall()
        self.assertEqual([row[0] for row in counts], [1, 1])
        self.image_edit.assert_called_once()

    def test_c4_cancel_paused(self):
        # A late render must not resurrect the job; cancellation itself must leave the paused outbox quiet.
        replay = self.replay()
        self.start_render(replay)
        self.stop(replay)
        self.assertEqual(replay.flush(), 1)
        replay.sink.reset_mock()
        before = replay.outbox()
        self.assertEqual(replay.say(f"no {replay.job['job_id']}"), "cancelled")
        replay.executor.run()
        sent = (replay.flush(), replay.flush())
        self.assertTrue(replay.conv._paused())
        self.assertEqual(replay.job["state"], "cancelled")
        self.assertIsNotNone(replay.job["closed_at"])
        self.assertEqual(replay.version["state"], "superseded")
        self.assertIsNone(replay.version["delivered_at"])
        self.assert_unpublished(replay)
        self.assertEqual((sent, replay.outbox(), replay.sink.mock_calls), ((0, 0), before, []))

        self.assertEqual(replay.say("resume changes"), "resume")
        self.assertEqual((replay.flush(), replay.flush()), (1, 0))  # no deferred cancellation acknowledgement
        replay.sink.send_card.assert_not_called()

        # The same coded cancellation still acknowledges when changes are enabled.
        enabled = self.replay()
        self.start_render(enabled)
        self.assertEqual(enabled.say(f"no {enabled.job['job_id']}"), "cancelled")
        self.assertEqual(enabled.flush(), 1)
        enabled.sink.send.assert_called_once_with(fixtures.CHAT, "Okay, I've cancelled that. Nothing changed.", [])
