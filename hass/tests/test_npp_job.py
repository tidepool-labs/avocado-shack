"""NPP-B offline contract replay. Only the stage scheduler and transport are scripted."""
from concurrent.futures import Future
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import unittest
from unittest.mock import patch

from hass import conversation, photo_polish, statebackup
from hass.npp.job import Card, Plan
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, STRANGER, T0
from hass.tests.test_editor import git
from hass.tests.test_photo_draft import JPG, PNG
from hass.tests.test_set_photo import PhotoRepo


class Scheduler:
    def __init__(self):
        self.steps = []

    def submit(self, fn, *args):
        future = Future()
        self.steps.append((future, fn, args))
        return future

    def run(self):
        future, fn, args = self.steps.pop(0)
        future.set_result(fn(*args))


class Transport:
    def __init__(self):
        self.texts, self.cards, self.receipts = [], {}, {}
        self.fail = False

    def send(self, chat, text, attachments):
        if attachments or "Post this?" in text:
            raise AssertionError("NPP prompt was sent via the legacy path")
        self.texts.append(text)

    def send_card(self, row, chat, text, png_path, digest):
        if self.fail:
            raise OSError("fixture enqueue failed")
        if row in self.cards:
            raise AssertionError("card was re-enqueued")
        self.cards[row] = text, Path(png_path).read_bytes(), digest

    def receipt_for(self, row):
        return self.receipts.get(row)


class Stages:
    def __init__(self, editor, root):
        self.editor, self.root = editor, root
        self.observed = []
        self.render_fail = False

    def takes_turn(self, text, state):
        return bool(re.match(r"(?:\$|sell|shorter)", text))

    def plan(self, work):
        req = work.request
        self.observed.append((tuple(req["attachments"]), work.deadline))
        if any("unreadable" in t for t in req["texts"]):
            return Plan(questions=(("identity", "What is it, or can you send a clearer photo?"),))
        price = req["slots"]["intake"].get("price")
        if price is None:
            return Plan(questions=(("price", "What's the selling price?"),), identified=True)
        return Plan(listing={"price": price})

    def render(self, work, listing):
        if self.render_fail:
            return None
        sha = work.request["attachments"][0]
        out = self.editor.prepare([{"op": "product.add", "args": {
            "name": "Fixture honey", "brand": "Producer not identified", "category": "pantry", "description": "Wildflower honey.",
            "photo": sha, "imageAlt": "A honey jar", "sellingPrice": f"{float(listing['price']):.2f}"}}])
        if out["result"] != "ok":
            raise AssertionError(out)
        draft = out["draft"]
        path, digest = next(iter(draft["assets"].items()))
        return Card(draft, PNG, "raw", path, digest.removeprefix("sha256:"), "picture: your own photo")

    def cap(self, work, listing):
        plan = self.plan(work)
        return (plan, self.render(work, listing or plan.listing)) if plan.listing else plan


class JobTests(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        self.root = self.repo.state.parent / "pictures"
        self.root.mkdir(mode=0o700)
        self.transport = Transport()
        self.now, self.serial = T0, 0
        self.editor = conversation.Editor(self.repo.state)
        self.interpreter = conversation.FixtureInterpreter({})
        self.settings = {**SETTINGS, "mediaRoot": str(self.root), "npp": True, "approvalTtlSeconds": 3600}
        self.base = self.repo.head()
        self.start()

    def start(self, *, source=True):
        if hasattr(self, "conv"):
            self.conv.db.close()
        cfg = self.repo.state / "config.json"
        cfg.write_text(json.dumps({**json.loads(cfg.read_text()), "settings": self.settings}))
        self.scheduler, self.stages = Scheduler(), Stages(self.editor, self.root)
        self.conv = conversation.Conversation(self.repo.state, self.editor, self.interpreter, lambda: self.now,
                                              photos=self, npp_stages=self.stages, npp_executor=self.scheduler,
                                              npp_receipt_for=self.transport.receipt_for if source else None)
        self.addCleanup(self.conv.db.close)

    def fetch(self, pid, count):
        return [JPG, PNG][:count]

    def say(self, text, *, photos=0, accepted=None, sender=OWNER, kind="new", pid=None, apply=True):
        self.serial += 1
        self.now += timedelta(seconds=1)
        msg = conversation.Inbound(pid or f"test-{self.serial}", CHAT, sender, text, kind=kind,
                                   received_at=(accepted or self.now).isoformat(), attachments=photos)
        return self.conv.handle(msg, forwarded_at=accepted or self.now, apply=apply)

    def flush(self):
        self.conv.flush(self.transport)

    def work(self):
        for _ in range(8):
            self.flush()
            if self.scheduler.steps:
                self.scheduler.run()
        self.assertFalse(self.scheduler.steps, "fixture work did not settle")

    def job(self):
        return self.conv.db.execute("SELECT * FROM npp_jobs ORDER BY rowid DESC LIMIT 1").fetchone()

    def version(self, n):
        return self.conv.npp.version(self.job()["job_id"], n)

    def confirm(self, n, *, state="confirmed", digest=None, at=None):
        v = self.version(n)
        self.transport.receipts[v["outbox_id"]] = dict(state=state, png_sha256=digest or v["card_png_sha"],
                                                        provider_guid=f"fixture-message-{n}", confirmed_at=(at or self.now).isoformat())
        self.flush()

    def yes(self, n=None, **kw):
        code = self.job()["job_id"] + (f"-{n}" if n is not None else "")
        return self.say(f"yes {code}", **kw)

    def assert_unpublished(self):
        self.assertEqual(self.repo.head(), self.base)
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 0)

    def test_restart_and_pending_receive_time_do_not_upgrade_yes(self):
        # 34: failed send retains the row. Receipt arrives after a yes accepted by inbox but before worker pickup.
        self.say("sell $2", photos=1)
        self.transport.fail = True
        with self.assertRaises(OSError):
            self.work()
        row = self.version(1)["outbox_id"]
        self.assertIsNone(self.conv.db.execute("SELECT sent_at FROM outbox WHERE id=?", (row,)).fetchone()[0])
        self.start()
        self.assertEqual(self.yes(1, pid="early-yes"), "no-target")
        with self.assertRaises(OSError):
            self.flush()  # card still fails, but cannot hold the guard behind it
        self.assertEqual(self.transport.texts, [self.conv.npp.replies["guards"]["not_ready"]])
        self.assertFalse(self.transport.cards)
        self.assertIsNone(self.conv.db.execute("SELECT sent_at FROM outbox WHERE id=?", (row,)).fetchone()[0])
        self.assert_unpublished()
        self.transport.fail = False
        self.flush()
        self.assertEqual(self.version(1)["outbox_id"], row)
        self.assertEqual(self.job()["state"], "working")
        self.now += timedelta(seconds=5)
        arrival = self.now
        self.now += timedelta(seconds=5)
        self.confirm(1, state="unconfirmed")
        self.assertEqual(self.job()["state"], "working")
        self.confirm(1, digest="0" * 64)
        self.assertEqual(self.job()["state"], "working")
        self.confirm(1)
        self.start()
        self.assertEqual(self.yes(1, pid="early-yes"), "duplicate")
        self.assertEqual(self.yes(1, accepted=arrival, pid="queued-yes"), "no-target")
        self.assertEqual(self.say(f"yes {self.job()['job_id']}-1", pid="queued-yes"), "duplicate")
        self.assert_unpublished()
        self.assertEqual(self.yes(1), "approved")
        self.assertNotEqual(self.repo.head(), self.base)
        self.assertEqual(self.job()["state"], "published")
        receipt = self.conv.db.execute("SELECT * FROM approvals JOIN npp_approvals ON approvals.id=approval_id").fetchone()
        self.assertEqual((receipt["outbox_id"], receipt["n"], receipt["draft_hash"], receipt["transport_message_id"]),
                         (row, 1, self.version(1)["draft_hash"], "fixture-message-1"))

    def test_no_source_does_not_dispatch_or_approve(self):
        # Staged production default: even a sender with a tracked method cannot promote a card without an injected source.
        self.start(source=False)
        self.say("sell $2", photos=1)
        self.work()
        self.assertEqual(self.version(1)["state"], "queued")
        self.assertFalse(self.transport.cards)
        self.assertEqual(self.yes(1), "no-target")
        self.assert_unpublished()
        self.settings["npp"] = False
        self.start()
        self.flush()  # switch-off must not leak a queued prompt into the ordinary outbox
        self.assertFalse(self.transport.cards)

    def test_delivered_restart_sole_code_owner_and_repeat(self):
        # 24 / approve-twice: a confirmed version survives restart without resends and binds exactly one A2 commit.
        self.say("sell $2", photos=1)
        self.work()
        self.confirm(1)
        self.start()
        self.flush()
        self.assertEqual(len(self.transport.cards), 1)
        self.assertEqual(self.yes(sender=STRANGER), "ignored")
        self.assertEqual(self.yes(kind="edited"), "not-read")
        self.assertEqual(self.yes(apply=False), "approval-held")
        self.assert_unpublished()
        self.assertEqual(self.yes(), "approved")
        head = self.repo.head()
        self.assertNotEqual(head, self.base)
        self.assertEqual(self.yes(), "no-target")
        self.assertEqual(self.repo.head(), head)
        self.flush()
        self.assertIn("already saved", self.transport.texts[-1])

    def test_fold_and_supersede_keep_one_card_per_segment(self):
        # 25 / 35: early edits fold; after freeze a new version wins. Replaced or ambiguous yes writes nothing.
        self.say("sell $2", photos=2)
        self.flush()
        self.say("sell $3")
        self.work()
        self.assertEqual(len(self.stages.observed[-1][0]), 2)
        self.assertEqual(len(self.transport.cards), 1)
        self.confirm(1)
        self.say("sell $4")
        self.flush()
        self.scheduler.run()
        self.flush()  # v2 frozen but not dispatched
        self.assertEqual(self.version(2)["state"], "building")
        self.say("sell $5")
        self.assertEqual(self.yes(), "no-target")
        self.work()
        self.assertEqual(self.version(2)["state"], "superseded")
        self.assertIsNone(self.version(2)["outbox_id"])
        self.confirm(3)
        self.assertEqual(len(self.transport.cards), 2)
        self.assertEqual(self.yes(1), "no-target")
        self.assertEqual(self.yes(), "no-target")
        self.flush()
        self.assertIn("replaced", self.transport.texts[-2])
        self.assertIn("Which card", self.transport.texts[-1])
        self.assert_unpublished()
        self.assertEqual(self.yes(3), "approved")
        self.assertEqual(self.version(3)["image_sha256"], self.version(1)["image_sha256"])
        self.assertIn('"sellingPrice": "5.00"', (self.repo.wt / "hass/content/products.json").read_text())
        self.assertEqual(self.say("undo"), "proposed")  # ordinary undo needs its own approval, even for an NPP change

    def test_render_failure_withholds_prompt_and_retry_has_its_own_version(self):
        # A failed capture must neither queue a text-only approval nor reuse the failed version on retry.
        self.stages.render_fail = True
        self.say("sell $2", photos=1)
        self.work()
        self.assertFalse(self.transport.cards)
        self.assertIn("couldn't draw", self.transport.texts[-1])
        self.assertEqual(self.yes(1), "no-target")
        self.stages.render_fail = False
        self.assertEqual(self.say("?"), "npp-working")
        self.work()
        self.confirm(2)
        self.assertEqual(self.yes(1), "no-target")
        self.assert_unpublished()
        self.assertEqual(self.yes(2), "approved")

    def test_question_wait_excluded_and_expired_answer_has_no_draft(self):
        # §1.3: open-request inactivity TTL, not the one-hour approval TTL.
        # say() adds one second; the precise deadline is inclusive in OpenRequests.
        for seconds, expected in ((1799, "card_out"), (1800, "expired"), (2400, "expired")):
            with self.subTest(seconds=seconds):
                self.say("new honey", photos=1)
                self.work()
                jid = self.job()["job_id"]
                self.assertEqual(self.job()["state"], "asking")
                self.assertIsNone(self.version(1))
                self.now += timedelta(seconds=seconds)
                self.say("$9 each")
                answer = self.now
                self.work()
                if expected == "card_out":
                    self.confirm(1)
                    self.assertEqual(self.stages.observed[-1][1], answer + timedelta(seconds=100))
                else:
                    self.assertIsNone(self.version(1))
                    self.assertIn("expired", self.transport.texts[-1])
                self.assertEqual(self.job()["state"], expected)
                self.assert_unpublished()
                if expected == "card_out":
                    self.say(f"no {jid}")

    def test_deadline_fallback_and_late_result_have_no_second_reply(self):
        # 21/22: pending result cannot hold up a command, and cannot write after the cap's complete-card or question reply.
        for text, terminal in (("sell $2", "card_out"), ("unreadable", "asking")):
            with self.subTest(text=text):
                before = len(self.transport.texts) + len(self.transport.cards)
                self.say(text, photos=1)
                self.flush()
                self.assertEqual(self.say("help"), "help")
                self.flush()
                self.now += timedelta(seconds=100)
                self.flush()
                if terminal == "card_out":
                    self.confirm(1)
                else:
                    self.assertIsNone(self.version(1))
                self.scheduler.run()
                self.flush()
                self.assertEqual(len(self.transport.texts) + len(self.transport.cards), before + 2)
                self.assertEqual(self.job()["state"], terminal)
                self.say("no")
                self.flush()

    def test_restart_before_polish_decision_does_not_start_twice(self):
        # 23: durable start marker precedes the launch; restart settles fallback instead of spawning another edit.
        self.settings.update(houseRender=True, photo_polish=True, itemIntake=True)
        self.start()
        with patch.object(photo_polish, "start", return_value=None) as launch:
            self.say("sell $2", photos=1, pid="original-photo")
            self.flush()
            self.scheduler.run()
            self.flush()
            self.flush()
            self.assertFalse(self.transport.cards)
            self.assertIsNotNone(self.job()["polish_started_at"])
            launch.assert_called_once()
            self.start()
            self.flush()
            launch.assert_called_once()
            decision = photo_polish.decision(self.root, self.job()["photo_sha"])
            assert decision is not None
            self.assertEqual((decision["use"], decision["code"]), ("house", "not-run"))
            self.work()
            [row] = self.transport.cards
            version = self.version(1)
            self.assertEqual((version["outbox_id"], version["image_variant"]), (row, "raw"))
            # The card becomes visible after restart, but still answers the start turn.
            self.assertEqual(self.conv.npp.one("SELECT provider_id FROM npp_turns WHERE reply_outbox_id=?", row)[0],
                             "original-photo")

    def test_backup_admits_only_frozen_job_artifacts(self):
        # Without media/npp admission even a private exact card would be refused or restored without its frozen bytes.
        self.say("sell $2", photos=1)
        self.work()
        png = next((self.root / "npp").glob("*/*.png"))
        self.assertEqual(hashlib.sha256(png.read_bytes()).hexdigest(), self.version(1)["card_png_sha"])
        out = self.root.parent / "backups"
        out.mkdir(mode=0o700)
        made = statebackup.create(self.repo.state, out, now=self.now)
        self.assertEqual(made["result"], "ok", made)
        saved = Path(made["backup"])
        rel = Path("media") / png.relative_to(self.root)
        self.assertEqual((saved / rel).read_bytes(), PNG)
        self.assertEqual(statebackup.verify(saved)["result"], "ok")
        restored_wt = self.root.parent / "restored-wt"
        git(self.repo.main, "worktree", "add", "-qb", "hass/npp-drill", str(restored_wt))
        target, images = self.root.parent / "restore", self.root.parent / "restore-media"
        self.assertEqual(statebackup.restore(saved, target, restored_wt, media_into=images)["result"], "ok")
        self.assertEqual((images / png.relative_to(self.root)).read_bytes(), PNG)
        self.assertEqual(json.loads((target / "config.json").read_text())["settings"]["mediaRoot"], str(images.resolve()))
        # Contract: a default backup of an NPP state carries the originals its open jobs resume from, so a media restore
        # that keeps npp on can still open the source photo (bug: npp on, mediaRoot at an empty originals/).
        sha = self.job()["photo_sha"]
        self.assertEqual(made["media"], 1)
        rel_orig = Path("originals") / sha[:2] / f"{sha}.jpg"
        self.assertEqual((images / rel_orig).read_bytes(), (self.root / rel_orig).read_bytes())
        self.assertTrue((images / rel_orig.with_suffix(".json")).is_file())
        self.assertFalse((images / "web").exists())  # web copies are regenerable and stay out of the backup
        self.assertTrue(json.loads((target / "config.json").read_text())["settings"]["npp"])
        (png.parent / "unrelated.json").write_text("{}")
        self.assertEqual(statebackup.create(self.repo.state, out, now=self.now)["result"], "refused")

    def test_restore_without_originals_turns_npp_off(self):
        # Contract: a backup that holds job artifacts but no source photo restores with npp off (bug: npp on, nothing to resume).
        self.say("sell $2", photos=1)
        self.work()
        shutil.rmtree(self.root / "originals")
        out = self.root.parent / "backups"
        out.mkdir(mode=0o700)
        saved = Path(statebackup.create(self.repo.state, out, now=self.now)["backup"])
        restored_wt = self.root.parent / "restored-wt"
        git(self.repo.main, "worktree", "add", "-qb", "hass/npp-drill", str(restored_wt))
        target, images = self.root.parent / "restore", self.root.parent / "restore-media"
        self.assertEqual(statebackup.restore(saved, target, restored_wt, media_into=images)["result"], "ok")
        self.assertFalse(json.loads((target / "config.json").read_text())["settings"]["npp"])

    def test_restore_with_unrelated_original_but_missing_job_photo_turns_npp_off(self):
        # Contract: npp stays on only if every open job's own photo is in the backup; another photo does not stand in
        # (bug: any original at all kept npp on with the job's source photo absent).
        self.say("sell $2", photos=1)
        self.work()
        sha = self.job()["photo_sha"]
        orig = self.root / "originals" / sha[:2] / f"{sha}.jpg"
        data = orig.read_bytes() + b"unrelated"
        other = hashlib.sha256(data).hexdigest()
        stray = self.root / "originals" / other[:2] / f"{other}.jpg"
        stray.parent.mkdir(exist_ok=True)
        stray.write_bytes(data)
        stray.with_suffix(".json").write_text(json.dumps({**json.loads(orig.with_suffix(".json").read_text()), "sha256": other}))
        orig.unlink()
        orig.with_suffix(".json").unlink()
        out = self.root.parent / "backups"
        out.mkdir(mode=0o700)
        saved = Path(statebackup.create(self.repo.state, out, now=self.now)["backup"])
        restored_wt = self.root.parent / "restored-wt"
        git(self.repo.main, "worktree", "add", "-qb", "hass/npp-drill", str(restored_wt))
        target, images = self.root.parent / "restore", self.root.parent / "restore-media"
        self.assertEqual(statebackup.restore(saved, target, restored_wt, media_into=images)["result"], "ok")
        self.assertTrue((images / stray.relative_to(self.root)).is_file())
        self.assertFalse((images / orig.relative_to(self.root)).exists())
        self.assertFalse(json.loads((target / "config.json").read_text())["settings"]["npp"])

    # Contract (rule: NPP stays on after a restore only if EVERY photo of EVERY open job is in the restored originals; a
    # request that cannot be read fails closed and the report names the job). Bug caught: only npp_jobs.photo_sha was checked.
    def restore_open_jobs(self, tag="", media=True):
        out = self.root.parent / f"backups{tag}"
        out.mkdir(mode=0o700)
        saved = Path(statebackup.create(self.repo.state, out, now=self.now)["backup"])
        restored_wt = self.root.parent / f"restored-wt{tag}"
        git(self.repo.main, "worktree", "add", "-qb", f"hass/npp-drill{tag}", str(restored_wt))
        target, images = self.root.parent / f"restore{tag}", self.root.parent / f"restore-media{tag}"
        got = statebackup.restore(saved, target, restored_wt, media_into=images if media else None)
        self.assertEqual(got["result"], "ok", got)
        return got, json.loads((target / "config.json").read_text())["settings"]

    def original(self, sha):
        return next(p for p in (self.root / "originals" / sha[:2]).glob(f"{sha}.*") if p.suffix != ".json")

    def two_photo_job(self):
        self.say("sell $2", photos=2)
        self.work()
        shas = json.loads(self.conv.db.execute("SELECT attachments_json FROM open_requests").fetchone()[0])
        self.assertEqual(len(shas), 2)
        self.assertEqual(self.job()["photo_sha"], shas[0])
        return shas

    def test_restore_keeps_npp_on_when_every_photo_of_the_open_job_is_present(self):
        self.two_photo_job()
        got, settings = self.restore_open_jobs()
        self.assertTrue(settings["npp"])
        self.assertNotIn("nppOff", got)

    def test_restore_turns_npp_off_when_second_photo_of_open_job_is_missing(self):
        first, second = self.two_photo_job()
        job = self.job()["job_id"]
        gone = self.original(second)
        gone.unlink()
        gone.with_suffix(".json").unlink()
        got, settings = self.restore_open_jobs()
        self.assertTrue((self.root.parent / "restore-media" / self.original(first).relative_to(self.root)).is_file())
        self.assertFalse(settings["npp"])
        self.assertEqual(got["nppOff"], [{"job": job, "why": f"original missing: {second[:12]}"}])

    def test_restore_turns_npp_off_when_an_open_job_request_cannot_be_read(self):
        self.two_photo_job()
        job = self.job()["job_id"]
        for n, sql in enumerate(("UPDATE open_requests SET attachments_json = 'not json'",
                                 "UPDATE open_requests SET attachments_json = '{}'",
                                 "UPDATE open_requests SET attachments_json = '[\"zz\"]'",
                                 "UPDATE open_requests SET attachments_json = '[7]'", "DELETE FROM open_requests")):
            with self.subTest(sql=sql):
                self.conv.db.execute(sql)
                self.conv.db.commit()
                got, settings = self.restore_open_jobs(str(n))
                self.assertFalse(settings["npp"])
                self.assertEqual([p["job"] for p in got["nppOff"]], [job])
                self.assertRegex(got["nppOff"][0]["why"], "request (missing|unreadable)")

    def test_backup_and_restore_of_npp_artifacts_do_not_depend_on_the_umask(self):
        # Contract: every backup/restore directory is 0700 whatever the umask. Bug: media/npp was made by
        # mkdir(parents=True) at 0755 under CI's umask 022, so verify said "corrupt" (a developer's umask 077 hid it).
        self.addCleanup(os.umask, os.umask(0o022))
        self.say("sell $2", photos=1)
        self.work()
        got, settings = self.restore_open_jobs()
        self.assertTrue(settings["npp"])
        restored = self.root.parent / "restore-media"
        self.assertEqual([oct(p.stat().st_mode & 0o777) for p in (restored, restored / "npp", restored / "originals")], ["0o700"] * 3)

    def test_restore_ignores_the_photos_of_a_closed_job(self):
        # A closed job needs none of its photos: with its second original gone, npp still stays on (no open jobs = unchanged).
        _, second = self.two_photo_job()
        self.conv.db.execute("UPDATE npp_jobs SET closed_at = ?, state = 'expired'", (self.now.isoformat(),))
        self.conv.db.commit()
        gone = self.original(second)
        gone.unlink()
        gone.with_suffix(".json").unlink()
        got, settings = self.restore_open_jobs()
        self.assertTrue(settings["npp"])
        self.assertNotIn("nppOff", got)

    # Contract: a restore without media turns NPP off, and the report still names each open job that cannot resume and
    # why (bug: with no media_into the open-job check was skipped, so nppOff was missing).
    def test_restore_without_media_names_each_open_job(self):
        first, second = self.two_photo_job()
        job = self.job()["job_id"]
        got, settings = self.restore_open_jobs(media=False)
        self.assertFalse(settings["npp"])
        self.assertEqual(got["nppOff"], [{"job": job, "why": f"original missing: {first[:12]}, {second[:12]}"}])

    def test_restore_without_media_names_job_with_unreadable_request(self):
        self.two_photo_job()
        job = self.job()["job_id"]
        self.conv.db.execute("UPDATE open_requests SET attachments_json = 'not json'")
        self.conv.db.commit()
        got, settings = self.restore_open_jobs(media=False)
        self.assertFalse(settings["npp"])
        self.assertEqual([p["job"] for p in got["nppOff"]], [job])
        self.assertRegex(got["nppOff"][0]["why"], "request (missing|unreadable)")

    def test_restore_without_media_and_no_open_jobs_has_no_nppoff(self):
        self.two_photo_job()
        self.conv.db.execute("UPDATE npp_jobs SET closed_at = ?, state = 'expired'", (self.now.isoformat(),))
        self.conv.db.commit()
        got, settings = self.restore_open_jobs(media=False)
        self.assertFalse(settings["npp"])
        self.assertNotIn("nppOff", got)

