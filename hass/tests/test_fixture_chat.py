"""AV-N3 tests: `fixture_chat.py --preview` runs the full H06 path (proposal screenshot, apply, checked result).

The CLI runs as a subprocess against a throwaway repo, linked writer worktree and 0700 state dir (the H05/H06 test
cases), with a mapping file that turns the fixture's request into the production `product.edit` op. Nothing is sent.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hass.content_model import REPO_ROOT
from hass.owner_answers import NOT_LIVE
from hass.tests.test_conversation import CHAT
from hass.tests.test_editor import git
from hass.tests.test_preview import PNG_SIGNATURE, BrowserCase
from hass import conversation

FIXTURE = REPO_ROOT / "hass" / "tests" / "fixtures" / "conversation-preview.jsonl"
REQUEST = "Update the avocado description"
MAPPING = {REQUEST: {"ops": [{"op": "product.edit", "args": {"id": "photo-product-001",
                                                             "description": "Ripe and creamy."}}], "revises": None}}
MISSING_PLAYWRIGHT = "/nonexistent/hass-test/playwright"


class FixtureChatPreviewTests(BrowserCase):
    def run_cli(self, *flags, state=None, env=None):
        mapping = self.repo.state.parent / "interpreter.json"
        mapping.write_text(json.dumps(MAPPING), "utf-8")
        run = subprocess.run([sys.executable, str(REPO_ROOT / "hass" / "fixture_chat.py"), "--state",
                              str(state or self.repo.state), "--fixture", str(FIXTURE), "--interpreter", str(mapping),
                              *flags], capture_output=True, text=True, cwd=REPO_ROOT, env=env or os.environ.copy())
        return run, [json.loads(line) for line in run.stdout.splitlines()]

    def drafts(self):
        db = sqlite3.connect(self.repo.state / "conversation.sqlite3")
        db.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in db.execute("SELECT * FROM drafts ORDER BY row_id")]
        finally:
            db.close()

    def test_failed_preview_is_reported_not_retried(self):
        run, rows = self.run_cli("--preview", env={**os.environ, "PLAYWRIGHT_MODULE": MISSING_PLAYWRIGHT})
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        self.assertEqual(len(rows), 2)
        [row] = self.drafts()
        self.assertTrue(rows[0]["text"].startswith(conversation.PREVIEW_FAILED_HEAD), rows[0]["text"])  # HASS-CHAT-1: said first, then tried again
        self.assertIn(conversation.PREVIEW_RETRY_LINE, rows[0]["text"])
        self.assertEqual(rows[0]["attachments"], [])
        self.assertTrue(rows[1]["text"].startswith("I saved it, but the preview check didn't pass: "), rows[1])
        self.assertEqual((row["state"], self.commits()), ("applied", 1))
        self.assertTrue(row["reason"].startswith("not verified: "), row["reason"])
        with self.subTest("uninitialised state dir"):
            empty = Path(tempfile.mkdtemp(prefix="hass-n3-", dir=self.repo.state.parent))
            empty.chmod(0o700)
            run, rows = self.run_cli("--preview", state=empty)
            self.assertEqual((run.returncode, run.stdout, rows), (2, "", []))
            self.assertIn("UnsafeState", run.stderr)
            self.assertEqual(sorted(p.name for p in empty.iterdir()), [])

    def test_without_the_flag_nothing_changes(self):
        run, rows = self.run_cli(env={**os.environ, "PLAYWRIGHT_MODULE": MISSING_PLAYWRIGHT})
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        [row] = self.drafts()
        self.assertEqual([r["attachments"] for r in rows], [[], []])
        self.assertNotIn("I couldn't make a picture of how it will look.", rows[0]["text"])
        self.assertEqual(rows[1]["text"], f"Saved: {row['summary']}\n{NOT_LIVE}")
        self.assertFalse((self.repo.state / "screenshots").exists())
        self.assertEqual((row["state"], self.commits()), ("applied", 1))

    @unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
    def test_browser_preview_attaches_private_screenshots(self):
        before = git(REPO_ROOT, "status", "--porcelain")
        run, rows = self.run_cli("--preview")
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        [row] = self.drafts()
        proposal = self.repo.state / "screenshots" / f"{row['change_id']}-proposal.png"
        result = self.repo.state / "screenshots" / f"{row['change_id']}-result.png"
        self.assertEqual([r["chat"] for r in rows], [CHAT, CHAT])
        self.assertEqual(rows[0]["attachments"], [str(proposal)])
        self.assertTrue(rows[1]["text"].startswith("Saved and checked:"), rows[1])
        self.assertEqual(rows[1]["attachments"], [str(result)])
        for png in (proposal, result):
            self.assertEqual(png.read_bytes()[:8], PNG_SIGNATURE)
            self.assertEqual(stat.S_IMODE(png.stat().st_mode), 0o600)
        self.assertEqual((row["state"], self.commits()), ("verified", 1))
        self.assertEqual(git(REPO_ROOT, "status", "--porcelain"), before)


if __name__ == "__main__":
    unittest.main()
