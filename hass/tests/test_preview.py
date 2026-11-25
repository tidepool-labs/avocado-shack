"""H06 browser tests: private proposal preview, verified result, verify failure (real loopback server + Chromium).

The writer worktree gets the full tracked storefront-mockup (assets linked read-only) so the real pages render.
Skipped only when PLAYWRIGHT_MODULE is unset (CI exports it; locally also set CHROMIUM_PATH as in BASELINE).
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import os
import shutil
import socket
import stat
import unittest
from pathlib import Path

from hass import conversation, preview
from hass.content_model import REPO_ROOT
from hass.tests.test_editor import git
from hass.tests.test_undo import H06TestCase

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class RecordingPreviewer(preview.Previewer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.results = []

    def capture(self, files, target, out_png):
        self.results.append(super().capture(files, target, out_png))
        return self.results[-1]


class BrowserCase(H06TestCase):
    env = None

    def make_previewer(self):
        wt = self.repo.wt
        for rel in git(REPO_ROOT, "ls-files", "storefront-mockup").splitlines():
            if not rel.startswith("storefront-mockup/assets/") and not (wt / rel).exists():
                (wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, wt / rel)
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "full site")
        return RecordingPreviewer(wt, self.env)


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class PreviewTests(BrowserCase):
    def snapshot(self):
        return git(REPO_ROOT, "status", "--porcelain"), self.repo.status(), self.repo.head()

    def test_proposal_preview_is_private_and_isolated(self):
        before = self.snapshot()
        draft, _reply = self.propose("desc")
        [sent] = self.out.sent[-1:]
        png = self.repo.state / "screenshots" / f"{draft['change_id']}-proposal.png"
        self.assertEqual(sent["attachments"], [str(png)])
        self.assertEqual(png.read_bytes()[:8], PNG_SIGNATURE)
        self.assertEqual(stat.S_IMODE(png.stat().st_mode), 0o600)
        self.assertNotIn("I couldn't make a picture", sent["text"])
        self.assertEqual(self.previewer.results[-1]["checks"],
                         {p + k: True for p in ("", "desktop:") for k in ("productShown", "description", "availabilityShown", "noPageErrors", "noPosts")})
        server = self.previewer.last_server
        with self.assertRaises(ProcessLookupError):
            os.kill(server["pid"], 0)
        with self.assertRaises(ConnectionRefusedError):
            socket.create_connection(("127.0.0.1", server["port"]), timeout=2).close()
        self.assertEqual(self.snapshot(), before)

    def test_applied_change_is_verified_with_a_screenshot(self):
        draft, _reply = self.propose("desc")
        self.assertEqual(self.say("yes"), "approved")
        [sent] = self.sent()
        [row] = self.drafts()
        self.assertEqual((row["state"], self.commits()), ("verified", 1))
        self.assertEqual(row["screenshot"], str(self.repo.state / "screenshots" / f"{draft['change_id']}-result.png"))
        self.assertEqual(Path(row["screenshot"]).read_bytes()[:8], PNG_SIGNATURE)
        result = self.previewer.results[-1]
        self.assertEqual((result["ok"], result["checks"]["productShown"], result["checks"]["description"]),
                         (True, True, True))
        self.assertEqual((sent["text"], sent["attachments"]),
                         (f"Saved and checked: {row['summary']}\n{conversation.answers.NOT_LIVE}",
                          [row["screenshot"]]))


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class VerifyFailureTests(BrowserCase):
    env = {**os.environ, "PLAYWRIGHT_MODULE": "/nonexistent/hass-test/playwright"}

    def test_failed_check_is_reported_not_retried(self):
        draft, reply = self.propose("desc")
        self.assertTrue(reply.startswith(conversation.PREVIEW_FAILED_HEAD), reply)  # HASS-CHAT-1: said first, then tried again
        self.assertIn(conversation.PREVIEW_RETRY_LINE, reply)
        self.assertEqual(self.say("yes"), "approved")
        [reply] = self.replies()
        [row] = self.drafts()
        self.assertTrue(reply.startswith("I saved it, but the preview check didn't pass: "), reply)
        self.assertEqual((row["state"], self.commits()), ("applied", 1))
        self.assertTrue(row["reason"].startswith("not verified: "), row["reason"])
        self.conv = conversation.Conversation(str(self.repo.state), self.editor, self.interp, lambda: self.now,
                                              self.previewer)
        self.assertEqual((self.replies(), self.commits(), self.drafts()[0]["state"]), ([], 1, "applied"))


if __name__ == "__main__":
    unittest.main()
