"""L15: the demo operator's pre-yes gate (scripts/hass/demo_pre_yes_gate.py) on a restored OFF install with two owners' cards pending.

Mike's and G's synthetic listings each have a delivered card; the state is backed up with the originals, restored (paused) and
resumed. The gate (run as the real command) is READY only for the matching photo + newest version + delivered card + not yet
served, and prints the exact yes. Every mismatch prints ABORT before any yes and leaves the transcript bytes, commits, public
names and approvals untouched. After one real yes, the served photo is Mike's photo and G's card is still only a card.
Fixtures only: throwaway repos, no network, no service, no live site.
"""
import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hass.tests import test_two_chat_restore as trc
from hass.tests.test_editor import git

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/demo_pre_yes_gate.py"
_spec = importlib.util.spec_from_file_location("demo_pre_yes_gate", SCRIPT)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def d12(data):
    return hashlib.sha256(data).hexdigest()[:12]


def _make():
    class PreYesGateTests(trc.TwoChatRestoreTests):
        """Reuses the two-chat restore fixture; its own journeys are run by test_two_chat_restore, not here."""

        def fingerprint(self, wt, state, conv):
            return (d12((Path(state) / "transcript.sqlite3").read_bytes()), self.commits_in(wt), sorted(self.names_in(wt)),
                    conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], git(wt, "status", "--porcelain"))

        def run_files(self, which, state, media, wt, job, photo_file, version):
            cmd = [sys.executable, "-B", str(SCRIPT), which, "--state", str(state), "--worktree", str(wt), "--job", job,
                   "--photo", str(photo_file), "--version", str(version)]
            if which == "before":
                cmd += ["--media", str(media)]
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            self.assertEqual(done.stderr, "")
            return done.returncode, done.stdout.strip()

        def run_gate(self, which, wt, state, media, job, photo, version):
            photo_file = Path(self._photos) / f"{d12(photo)}.png"
            photo_file.write_bytes(photo)
            return self.run_files(which, state, media, wt, job, photo_file, version)

        def must_abort(self, want, wt, state, media, conv, job, photo, version):
            before = self.fingerprint(wt, state, conv)
            code, out = self.run_gate("before", wt, state, media, job, photo, version)
            self.assertEqual((code, out), (1, f"ABORT {want}"))
            self.assertEqual(before, self.fingerprint(wt, state, conv), want + ": the gate changed something")

        def test_pre_yes_gate(self):
            jobs = self.two_pending()
            mike, gee = trc.LISTINGS[trc.MCHAT], trc.LISTINGS[trc.GCHAT]
            self.assertNotEqual(mike["photo"], gee["photo"])
            source = (self.repo.head(), self.site(), self.commits())
            with tempfile.TemporaryDirectory() as tmp:
                self._photos = Path(tmp) / "photos"
                self._photos.mkdir(mode=0o700)
                wt, state, conv, media = self.restore(tmp)
                self.conv = conv
                self.assertEqual(self.talk(trc.MCHAT, "resume changes"), "resume")
                jm, jg = jobs[trc.MCHAT], jobs[trc.GCHAT]
                args = (wt, state, media)

                # the matching trio is READY and names the exact yes
                self.assertEqual(self.run_gate("before", *args, jm, mike["photo"], 1), (0, f"READY yes {jm}-1"))
                self.assertEqual(self.run_gate("before", *args, jg, gee["photo"], 1), (0, f"READY yes {jg}-1"))

                # mismatches abort, with nothing moved
                self.must_abort("photo-mismatch", *args, conv, jm, gee["photo"], 1)
                self.must_abort("photo-mismatch", *args, conv, jg, mike["photo"], 1)
                self.must_abort("version-mismatch", *args, conv, jm, mike["photo"], 2)
                self.must_abort("no-such-listing", *args, conv, "ffff", mike["photo"], 1)
                card, = Path(media).glob(f"npp/{jm}/card-*.png")
                saved = card.read_bytes()
                card.write_bytes(saved + b"x")
                self.must_abort("card-bytes-missing-or-changed", *args, conv, jm, mike["photo"], 1)
                card.unlink()
                self.must_abort("card-bytes-missing-or-changed", *args, conv, jm, mike["photo"], 1)
                card.write_bytes(saved)
                os.chmod(card, 0o600)
                self.assertEqual(self.run_gate("before", *args, jm, mike["photo"], 1), (0, f"READY yes {jm}-1"))

                # a card the chat never carried (event list without it) and a card saved but never delivered
                card_sha = conv.db.execute("SELECT card_png_sha FROM npp_versions WHERE job_id=?", (jm,)).fetchone()[0]
                events = gate._viewer().rows(state)
                self.assertEqual(sum(1 for e in events if e["direction"] == "out" and card_sha in e["attachments"]), 1)
                without = [e for e in events if not (e["direction"] == "out" and card_sha in e["attachments"])]
                self.assertEqual(gate.before_yes(conv.db, media, without, jm, hashlib.sha256(mike["photo"]).hexdigest(), 1,
                                                 set(self.names_in(wt))), ("ABORT", "card-not-in-chat"))
                was = conv.db.execute("SELECT state, delivered_at FROM npp_versions WHERE job_id=?", (jm,)).fetchone()
                conv.db.execute("UPDATE npp_versions SET state='queued', delivered_at=NULL WHERE job_id=?", (jm,))
                self.must_abort("card-not-delivered", *args, conv, jm, mike["photo"], 1)
                conv.db.execute("UPDATE npp_versions SET state=?, delivered_at=? WHERE job_id=?", (was[0], was[1], jm))
                self.assertEqual(self.run_gate("before", *args, jm, mike["photo"], 1), (0, f"READY yes {jm}-1"))

                # unusable inputs: a missing photo file and a bad job id are labels, never a traceback
                done = subprocess.run([sys.executable, "-B", str(SCRIPT), "before", "--state", str(state), "--worktree", str(wt),
                                       "--job", jm, "--photo", str(Path(tmp) / "nope.png"), "--version", "1", "--media", str(media)],
                                      capture_output=True, text=True, timeout=60)
                self.assertEqual((done.returncode, done.stdout.strip(), done.stderr), (1, "ABORT photo-unreadable", ""))
                self.must_abort("no-such-listing", *args, conv, "../x", mike["photo"], 1)

                # a link anywhere on a path is refused, never followed: photo leaf or parent, card parent, media root, worktree, state
                link_dir, real = Path(tmp) / "linkdir", Path(tmp) / "real-photos"
                real.mkdir(mode=0o700)
                (real / "m.png").write_bytes(mike["photo"])
                link_dir.symlink_to(real, target_is_directory=True)
                leaf = Path(tmp) / "leaf.png"
                leaf.symlink_to(real / "m.png")
                self.assertEqual(self.run_files("before", state, media, wt, jm, real / "m.png", 1), (0, f"READY yes {jm}-1"))
                for photo_path in (link_dir / "m.png", leaf):
                    self.assertEqual(self.run_files("before", state, media, wt, jm, photo_path, 1), (1, "ABORT photo-unreadable"))
                    self.assertEqual(self.run_files("after", state, media, wt, jm, photo_path, 1), (1, "ABORT photo-unreadable"))
                moved = Path(tmp) / "moved-card-dir"
                card_dir = Path(media) / "npp" / jm
                card_dir.rename(moved)
                card_dir.symlink_to(moved, target_is_directory=True)
                self.assertEqual(self.run_files("before", state, media, wt, jm, real / "m.png", 1),
                                 (1, "ABORT card-bytes-missing-or-changed"))
                card_dir.unlink()
                moved.rename(card_dir)
                for name, field in (("media-link", "media"), ("worktree-link", "wt"), ("state-link", "state")):
                    link = Path(tmp) / name
                    link.symlink_to({"media": media, "wt": wt, "state": state}[field], target_is_directory=True)
                    use = {"media": media, "wt": wt, "state": state}
                    use[field] = link
                    code, out = self.run_files("before", use["state"], use["media"], use["wt"], jm, real / "m.png", 1)
                    self.assertEqual(code, 1, (name, out))
                    self.assertIn(out, {"ABORT card-bytes-missing-or-changed", "ABORT catalog-unreadable", "ABORT could-not-check"})
                self.assertEqual(self.run_files("before", state, media, wt, jm, real / "m.png", 1), (0, f"READY yes {jm}-1"))

                # the one yes posts Mike's listing only; the gate then reports what is served
                before_commits = self.commits_in(wt)
                self.assertEqual(self.talk(trc.MCHAT, f"yes {jm}-1"), "approved")
                self.assertEqual(self.commits_in(wt), before_commits + 1)
                self.assertIn(mike["name"], self.names_in(wt))
                self.assertNotIn(gee["name"], self.names_in(wt))
                self.assertEqual(self.run_gate("after", wt, state, media, jm, mike["photo"], 1), (0, "SERVED undo"))
                self.assertEqual(self.run_gate("after", wt, state, media, jm, gee["photo"], 1), (1, "ABORT photo-mismatch"))
                self.assertEqual(self.run_gate("after", wt, state, media, jg, gee["photo"], 1), (1, "ABORT not-served"))
                # the same yes is not offered twice, and G's own gate is untouched
                code, out = self.run_gate("before", *args, jm, mike["photo"], 1)
                self.assertEqual(code, 1, out)
                self.assertTrue(out.startswith("ABORT "), out)
                self.assertEqual(self.run_gate("before", *args, jg, gee["photo"], 1), (0, f"READY yes {jg}-1"))
                # one take-down word removes it
                self.assertEqual(self.talk(trc.MCHAT, "undo"), "proposed")
            self.assertEqual((self.repo.head(), self.site(), self.commits()), source)

    # Only the gate's own journey runs here; the inherited journeys belong to test_two_chat_restore.
    for name in dir(trc.TwoChatRestoreTests):
        if name.startswith("test"):
            setattr(PreYesGateTests, name, None)
    return PreYesGateTests


PreYesGateTests = _make()

if __name__ == "__main__":
    unittest.main()
