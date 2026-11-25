"""The resume command, not chat history alone, determines the next OFF step."""
import contextlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from hass.tests import test_two_chat_restore as fixtures

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/demo_resume_step.py"


def _resume_tests():
    class ResumeTests(fixtures.TwoChatRestoreTests):
        def check_step(self, version, expected, code=0):
            before = ([p.read_bytes() for p in self.sources], self.commits_in(self.wt))
            run = subprocess.run([sys.executable, "-B", str(SCRIPT), "--state", str(self.state),
                                  "--media", str(self.media), "--worktree", str(self.wt),
                                  "--job", self.job, "--photo", str(self.held_photo),
                                  "--version", str(version)], capture_output=True, text=True, timeout=15)
            self.assertEqual((run.returncode, run.stdout.strip(), run.stderr), (code, expected, ""))
            self.assertEqual(before, ([p.read_bytes() for p in self.sources], self.commits_in(self.wt)))

        def test_resume_across_yes_and_hide(self):
            # Neither outbox history from a different chat nor a published flag
            # can move a restored listing forward without matching evidence.
            chat = fixtures.MCHAT
            self.job = self.two_pending()[chat]
            with tempfile.TemporaryDirectory() as tmp:
                self.wt, self.state, self.conv, self.media = self.restore(tmp)
                self.assertEqual(self.talk(chat, "resume changes"), "resume")
                self.held_photo = Path(tmp) / "held.png"
                original = fixtures.LISTINGS[chat]["photo"]
                assert isinstance(original, bytes)
                self.held_photo.write_bytes(original)
                catalog = self.wt / "storefront-mockup/catalog-products.js"
                transcript = self.state / "transcript.sqlite3"
                self.sources = [self.state / "conversation.sqlite3", transcript, catalog, self.held_photo]
                baseline = catalog.read_bytes()
                self.check_step(1, "REVIEW_CURRENT_PREVIEW")
                self.check_step(2, "HOLD version-mismatch", 1)
                card, = (self.media / "npp" / self.job).glob("card-*.png")
                saved = card.read_bytes()
                card.write_bytes(saved + b"x")
                try:
                    self.check_step(1, "HOLD card-bytes-missing-or-changed", 1)
                finally:
                    card.write_bytes(saved)
                with contextlib.closing(sqlite3.connect(transcript)) as db:
                    sha = fixtures.sha(saved)
                    event, = db.execute("SELECT id FROM events WHERE chat=? AND direction='out' AND attachments LIKE ?",
                                        (chat, f"%{sha}%")).fetchone()
                    with db:
                        db.execute("UPDATE events SET chat=? WHERE id=?", (fixtures.GCHAT, event))
                    try:
                        self.check_step(1, "HOLD card-not-in-chat", 1)
                    finally:
                        with db:
                            db.execute("UPDATE events SET chat=? WHERE id=?", (chat, event))

                self.assertEqual(self.talk(chat, f"yes {self.job}-1"), "approved")
                self.check_step(1, "REVIEW_TAKEDOWN")
                self.check_step(2, "HOLD version-mismatch", 1)
                still_served = catalog.read_bytes()
                first, rest = still_served.split(b"\n", 1)
                records = json.loads(first.removeprefix(b"const catalog=").rstrip(b";"))
                item = next(r for r in records if r["name"] == fixtures.LISTINGS[chat]["name"])
                item["description"] = "Fixture mismatch."
                catalog.write_bytes(b"const catalog=" + json.dumps(records).encode() + b";\n" + rest)
                try:
                    self.check_step(1, "HOLD served-card-differs", 1)
                finally:
                    catalog.write_bytes(still_served)
                self.assertEqual(self.talk(chat, "undo"), "proposed")
                self.check_step(1, "REVIEW_TAKEDOWN")  # a proposal alone is not a takedown
                code, = self.conv.db.execute("SELECT code FROM drafts WHERE state='proposed'").fetchone()
                self.assertEqual(self.talk(chat, f"yes {code}"), "approved")
                self.assertEqual(catalog.read_bytes(), baseline)
                self.check_step(1, "NOT_SERVED")
                catalog.write_bytes(still_served)
                try:
                    self.check_step(1, "HOLD served-state-conflict", 1)
                finally:
                    catalog.write_bytes(baseline)

    for name in dir(fixtures.TwoChatRestoreTests):
        if name.startswith("test_"):
            setattr(ResumeTests, name, None)
    return ResumeTests


ResumeTests = _resume_tests()

if __name__ == "__main__":
    unittest.main()
