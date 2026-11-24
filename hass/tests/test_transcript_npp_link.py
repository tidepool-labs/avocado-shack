"""HRM-21: transcript rows name their NPP listing (`<job>`) or card version (`<job>-<n>`). Fixtures only, no network."""
import contextlib
from datetime import timedelta
import io
import json
import sqlite3
from types import SimpleNamespace
import unittest
from unittest import mock

from hass import transcript
from hass.npp.job import Plan
from hass.tests import test_npp_job as npp_b  # module import: its JobTests must not be collected (and re-run) here

RETAKE = "Please send a clearer photo of the front."
DUPLICATE = "Is this the same honey as the last one?"


class ScriptedStages(npp_b.Stages):
    """The NPP-B fixture stages, plus a scripted plan for the retake and duplicate-question replies."""
    script: str | None = None

    def plan(self, work):
        if self.script == "retake":
            return Plan(retake=RETAKE)
        if self.script == "duplicate":
            return Plan(questions=(("duplicate", DUPLICATE),), identified=True)
        return super().plan(work)


class TranscriptNppLinkTests(unittest.TestCase):
    # Reuse the NPP-B offline harness (fixture repo, scripted scheduler and transport) without re-running its tests.
    _h = npp_b.JobTests
    setUp, flush, work, job, version, confirm, yes, fetch, say = (
        _h.setUp, _h.flush, _h.work, _h.job, _h.version, _h.confirm, _h.yes, _h.fetch, _h.say)

    def start(self, *, source=True):
        self._h.start(self, source=source)
        self.stages = self.conv.npp.stages = ScriptedStages(self.editor, self.root)

    def rows(self):
        with contextlib.closing(transcript.read(self.repo.state)) as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id")]

    def out(self):
        return [r for r in self.rows() if r["direction"] == "out"]

    def inbound(self, pid):
        return next(r for r in self.rows() if r["direction"] == "in" and r["provider_id"] == pid)

    def replies_to(self, act):
        """The outbound rows queued by act() (a say or a work/flush), as (text, kind, draft_code)."""
        before = len(self.out())
        act()
        return [(r["text"], r["kind"], r["draft_code"]) for r in self.out()[before:]]

    def assert_reply(self, act, code, needle, kind="text"):
        got = self.replies_to(act)
        self.assertEqual(len(got), 1, got)
        text, actual_kind, actual_code = got[0]
        self.assertIn(needle, text)
        self.assertEqual((actual_kind, actual_code), (kind, code))

    def test_c1_inbound(self):
        # Every accepted NPP turn (start photo, edit, `?` retry, answer, `yes <job>-<n>`, cancel) names its listing.
        self.assertEqual(self.say("new honey", photos=1, pid="p-start"), "npp-working")
        self.work()
        jid = self.job()["job_id"]
        self.assertEqual(self.say("$2 each", pid="p-answer"), "npp-working")
        self.work()
        self.confirm(1)
        self.assertEqual(self.say("sell $3", pid="p-edit"), "npp-working")
        self.work()
        self.confirm(2)
        self.assertEqual(self.say(f"yes {jid}-1", pid="p-yes"), "no-target")
        self.assertEqual(self.say("no", pid="p-no"), "cancelled")
        turns = {pid for pid, in self.conv.db.execute("SELECT provider_id FROM npp_turns WHERE job_id=?", (jid,))}
        self.assertEqual(turns, {"p-start", "p-answer", "p-edit", "p-yes", "p-no"})
        for pid in sorted(turns):
            with self.subTest(pid=pid):
                self.assertEqual(self.inbound(pid)["draft_code"], jid)
        # `?` (retry after a failed render) is an NPP turn too.
        self.stages.render_fail = True
        self.say("sell $2", photos=1, pid="p-second")
        self.work()
        retry = self.job()["job_id"]
        self.stages.render_fail = False
        self.assertEqual(self.say("?", pid="p-retry"), "npp-working")
        self.assertEqual((self.inbound("p-second")["draft_code"], self.inbound("p-retry")["draft_code"]), (retry, retry))

    def test_c2_outbound(self):
        # Every NPP reply kind: card -> `<job>-<n>`; question, retake and every guard -> `<job>`.
        guards = self.conv.npp.replies["guards"]
        self.say("sell $2", photos=1)  # expired yes (approval path); first, as it publishes nothing
        self.work()
        self.confirm(1)
        jid = self.job()["job_id"]
        self.now += timedelta(seconds=3601)
        self.assert_reply(lambda: self.yes(1), jid, "expired")

        self.say("new honey", photos=1)
        q = self.replies_to(self.work)
        jid = self.job()["job_id"]
        self.assertEqual(q, [("What's the selling price?", "text", jid)])  # question
        self.say("$2 each")
        self.assert_reply(self.work, f"{jid}-1", f"{jid}-1", kind="photo")  # card v1
        self.assert_reply(lambda: self.yes(1), jid, guards["not_ready"])  # not_ready: card not yet delivered
        self.confirm(1)
        self.say("sell $3")
        self.assert_reply(self.work, f"{jid}-2", f"{jid}-2", kind="photo")  # card v2
        self.confirm(2)
        self.assert_reply(lambda: self.yes(1), jid, guards["replaced"])  # replaced
        self.assert_reply(lambda: self.yes(), jid, guards["which_card"])  # which_card
        self.assertEqual(self.say("pause changes"), "pause")
        self.assert_reply(lambda: self.yes(2), jid, "paused")  # paused
        self.say("resume changes")
        self.assertEqual(self.yes(2), "approved")
        self.assert_reply(lambda: self.yes(2), jid, "already saved")  # already-done

        self.stages.render_fail = True  # render_failed guard
        self.say("sell $2", photos=1)
        jid = self.job()["job_id"]
        self.assert_reply(self.work, jid, guards["render_failed"])
        self.stages.render_fail = False
        self.assert_reply(lambda: self.say("no"), jid, "cancelled")  # cancel by `no`

        self.stages.script = "retake"  # retake
        self.say("blurry", photos=1)
        jid = self.job()["job_id"]
        self.assert_reply(self.work, jid, RETAKE)
        self.say(f"no {jid}")

        self.stages.script = "duplicate"  # duplicate question, then the cancel it allows
        self.say("honey again", photos=1)
        jid = self.job()["job_id"]
        self.assert_reply(self.work, jid, DUPLICATE)
        self.assert_reply(lambda: self.say("no"), jid, "cancelled")
        self.stages.script = None

        self.say("new honey", photos=1)  # expired while answering a question (input path)
        self.work()
        jid = self.job()["job_id"]
        self.now += timedelta(seconds=2400)
        self.assert_reply(lambda: self.say("$9 each"), jid, "expired")
        # Every NPP reply row was linked (the approval's "Saved" line too); only the ordinary pause/resume replies keep None.
        unlinked = [r["text"] for r in self.out() if r["draft_code"] is None]
        self.assertEqual(len(unlinked), 2, unlinked)
        self.assertIn("resume changes", unlinked[0])
        self.assertIn("back on", unlinked[1])
        saved = [r for r in self.out() if r["text"].startswith("Saved:")]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["draft_code"], self.conv.db.execute(
            "SELECT job_id FROM npp_jobs WHERE state='published'").fetchone()[0])

    def test_c2_outbound_card_link_beats_inherited_context(self):
        # A card queued while another message is being handled (early flush) names its own card, not that message's code.
        self.say("sell $2", photos=1)
        jid = self.job()["job_id"]
        other = mock.Mock(metadata=lambda: {"draft_code": "beef", "latency_ms": 1})
        self.conv.outbox.transcript_context = other
        try:
            self.assert_reply(self.work, f"{jid}-1", f"{jid}-1", kind="photo")
        finally:
            self.conv.outbox.transcript_context = None
        self.assertIsNone(getattr(self.conv.outbox, "transcript_link", None))  # the link never outlives its reply

    def test_c2_outbound_transcript_failure_never_blocks_reply(self):
        # The existing `safe` rule holds for linked rows: a failed transcript write still queues the NPP card and guard.
        with mock.patch.object(transcript, "append", side_effect=OSError("fixture")):
            with self.assertLogs("hass.transcript", level="ERROR"):
                self.say("sell $2", photos=1)
                self.work()
                self.assertEqual(self.say("yes " + self.job()["job_id"] + "-1"), "no-target")
        self.assertEqual(self.version(1)["state"], "queued")
        self.assertEqual(len(self.transport.cards), 1)
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], 2)
        self.assertIsNone(getattr(self.conv.outbox, "transcript_link", None))

    def test_c3_unchanged(self):
        # None by default; a typed legacy code stays exactly as Capture.metadata() binds it; NPP never overwrites it.
        self.say("help", pid="c3-none")
        self.assertIsNone(self.inbound("c3-none")["draft_code"])
        self.assertTrue(self.out() and all(r["draft_code"] is None for r in self.out()))
        before = len(self.out())
        self.say("yes 1a2b", pid="c3-typed")  # a legacy (non-NPP) typed code: bound exactly as typed, as today
        self.assertEqual(self.inbound("c3-typed")["draft_code"], "1a2b")
        self.assertTrue(self.out()[before:] and all(r["draft_code"] == "1a2b" for r in self.out()[before:]))
        # An NPP turn row for the same message cannot replace the typed code on the inbound event.
        self.say("sell $2", photos=1)
        jid = self.job()["job_id"]
        self.conv.npp.turn(jid, SimpleNamespace(provider_id="c3-both", received_at=self.now.isoformat()), "other", self.now)
        self.say("no 1a2b", pid="c3-both")
        self.assertEqual(self.inbound("c3-both")["draft_code"], "1a2b")
        # A broken link lookup is no link, never an error that could cost the row.
        self.assertIsNone(transcript.npp_job(None, "c3-none"))

    def test_c4_old_rows(self):
        # Rows a pre-HRM-21 build wrote (NULL draft_code, a typed legacy code) export and read beside linked rows.
        old = [transcript.event("fixture-chat", "fixture-sender", "in", "text", "words", "old-1"),
               transcript.event("fixture-chat", "hass", "out", "text", "reply", reply_to="old-1"),
               transcript.event("fixture-chat", "fixture-sender", "in", "text", "yes 1a2b", "old-2", draft_code="1a2b")]
        for row in old:
            transcript.append(self.repo.state, **row)
        self.say("sell $2", photos=1)
        self.work()
        jid = self.job()["job_id"]
        rows = self.rows()
        self.assertEqual([r["draft_code"] for r in rows[:3]], [None, None, "1a2b"])
        self.assertEqual({r["draft_code"] for r in rows[3:]}, {jid, f"{jid}-1"})
        for command, extra in (("export", ["--since", "2000-01-01"]), ("stats", [])):
            with self.subTest(command=command):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    code = transcript.main([command, "--state", str(self.repo.state), *extra])
                self.assertEqual(code, 0)
                lines = [json.loads(s) for s in buf.getvalue().splitlines()]
                if command == "export":
                    self.assertEqual([d["draft_code"] for d in lines], [r["draft_code"] for r in rows])
                    self.assertEqual(lines[0]["provider_id"], "old-1")
                else:
                    self.assertEqual(sum(d["count"] for d in lines), len(rows))


if __name__ == "__main__":
    unittest.main()
