"""AV1222-07 (H09): the photo demo with the REAL previewer. Photo + caption -> draft -> yes -> real screenshot check finds
the new image on the product card -> undo restores the old one, in ONE `fixture_chat.py --preview` run (run in-process so
every real capture result can be read). Skipped when PLAYWRIGHT_MODULE is unset, like test_demo_browser.
Run: python3 -B -m unittest hass.tests.test_demo_browser_photo -v
"""

import contextlib
import io
import json
import os
import stat
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from hass import fixture_chat, preview
from hass.content_model import REPO_ROOT
from hass.tests import test_demo_transcript_photo as photo
from hass.tests import test_demo_browser as _db
from hass.tests.test_demo_browser import MISSING_PLAYWRIGHT, PNG_SIGNATURE
from hass.tests.test_editor import git
from hass.tests.test_set_photo import PID


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class DemoBrowserPhotoTests(unittest.TestCase):
    fresh, query, site = photo.PhotoDemoTranscriptTests.fresh, photo.PhotoDemoTranscriptTests.query, _db.DemoBrowserTests.site  # the browser test's full-site helper

    def run_chain(self, repo, extra=(), playwright=None):
        """(reply rows, [(out png name, target, capture result)]) of one --preview run on the demo with its times at now."""
        rows = [json.loads(s) for s in photo.DEMO.read_text("utf-8").splitlines()] + list(extra)
        shift = datetime.now(timezone.utc) - datetime.fromisoformat(rows[0]["at"])
        path = repo.state.parent / "photo-now.jsonl"
        path.write_text("".join(json.dumps({**r, "at": (datetime.fromisoformat(r["at"]) + shift).isoformat()}) + "\n"
                                for r in rows), "utf-8")
        seen, real, out = [], preview.Previewer.capture, io.StringIO()

        def record(previewer, files, target, out_png, assets=None):
            result = real(previewer, files, target, out_png, assets)
            seen.append((Path(out_png).name, target, result))
            return result

        env = {"PLAYWRIGHT_MODULE": playwright} if playwright else {}
        with mock.patch.dict(os.environ, env), mock.patch.object(preview.Previewer, "capture", record), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()) as err:
            code = fixture_chat.main(["--state", str(repo.state), "--fixture", str(path), "--interpreter",
                                      str(photo.MAPPING), "--photos", str(photo.MEDIA), "--preview"])
        self.assertEqual((code, err.getvalue()), (0, ""))
        return [json.loads(line) for line in out.getvalue().splitlines()], seen

    def test_whole_chain_shows_the_new_photo_then_the_old_one(self):
        repo, before = self.site(), git(REPO_ROOT, "status", "--porcelain")
        original = repo.product(PID)["image"]
        stranger = {**json.loads(photo.DEMO.read_text("utf-8").splitlines()[0]), "id": "photo-demo-9",
                    "sender": "stranger@example.invalid", "at": "2026-11-02T09:08:00-08:00"}
        rows, seen = self.run_chain(repo, [stranger])
        texts = [r["text"] for r in rows]
        self.assertEqual([next((k for k in photo.KINDS if t.startswith(k)), t) for t in texts],
                         photo.EXPECTED[:3] + ["Saved and checked: ", "Here's what we changed lately:",
                                               "To undo that, I'd change it back:", "Saved and checked: "])
        edit, undo = self.query(repo, "SELECT * FROM drafts ORDER BY row_id")
        self.assertEqual((edit["state"], undo["state"]), ("reverted", "verified"))
        results = [(name, target, shot) for name, target, shot in seen if "-result" in name]
        self.assertEqual([n for n, _t, _s in results], [f"{edit['change_id']}-result.png", f"{undo['change_id']}-result.png"])
        for (_name, target, shot), image in zip(results, (photo.INSTALLED, original)):  # read from the real captures
            self.assertEqual(target["image"], image)
            self.assertTrue(shot["ok"] and shot["checks"]["imageShown"] and shot["checks"]["desktop:imageShown"], shot)
        self.assertNotEqual(photo.INSTALLED, original)
        self.assertEqual(repo.product(PID)["image"], original)  # undo restored the old image
        state = repo.state.resolve()
        for row in rows:
            for name in row["attachments"]:
                png = Path(name)
                self.assertEqual((stat.S_IMODE(png.stat().st_mode), png.read_bytes()[:8]), (0o600, PNG_SIGNATURE))
                self.assertTrue(png.resolve().is_relative_to(state) and not png.is_symlink(), name)
                self.assertFalse(png.resolve().is_relative_to(repo.wt.resolve()) or png.resolve().is_relative_to(REPO_ROOT))
        messages = {r["provider_id"]: r["disposition"] for r in self.query(repo, "SELECT * FROM messages")}
        self.assertEqual(messages["photo-demo-9"], "ignored")  # the stranger's photo: no draft, no reply
        self.assertEqual((len(messages), len(texts)), (8, 7))
        self.assertEqual(git(REPO_ROOT, "status", "--porcelain"), before)

    def test_missing_playwright_reports_the_failed_check_and_does_not_retry(self):
        repo = self.site()
        rows, seen = self.run_chain(repo, playwright=MISSING_PLAYWRIGHT)
        texts = [r["text"] for r in rows]
        edit, undo = self.query(repo, "SELECT * FROM drafts ORDER BY row_id")
        self.assertTrue(texts[3].startswith("I saved it, but the preview check didn't pass: "), texts[3])
        self.assertTrue(all(not r["attachments"] for r in rows))
        self.assertTrue(all(not shot["ok"] for _n, _t, shot in seen))
        self.assertNotIn("verified", (edit["state"], undo["state"]))
        self.assertTrue(undo["reason"].startswith("not verified: "), undo["reason"])
        for draft in (edit, undo):  # one result check each, not retried
            self.assertEqual(sum(f"{draft['change_id']}-result" in n for n, _t, _s in seen), 1)


if __name__ == "__main__":
    unittest.main()
