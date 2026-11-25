"""L20: one OFF operator run, end to end, with the real commands in the order docs/hass/finish-off-operator-run.md gives.

The demo is interrupted while both owners' cards wait for a yes. The operator then, with the shipped commands:
  1. inventories the state backup (a damaged copy is refused, and the restore command refuses it and creates nothing);
  2. restores it on a paused OFF copy (the one command that writes: a new state folder and media folder only) and resumes;
  3. asks the resume step what is next (the current delivered preview; an older/newer version number is refused);
  4. runs the pre-yes gate, and only then the owner types the one coded yes for exactly that version;
  5. compares what the shop serves with the approved card, and asks the resume step again (take-down is next);
     a stale pre-yes receipt for the same version now aborts;
  6. takes the card down with `undo` + its coded yes; the shop is back to how it was, the resume step says NOT_SERVED;
  7. resumes the other owner's waiting listing, which was never touched.
Every command runs as a real subprocess. Around each inspection command (inventory, resume step, pre-yes gate, served
comparison) every file under the folders it is given (backup, source state, restored state and media, shop worktree,
held photos) is byte-identical. Around the restore the backup and the source state are byte-identical, the target folders
did not exist before, and only they appear; a refused restore creates neither. The yes and undo are the owner's chat
messages, not commands. Fixtures only (throwaway repos), no network, service, live site or private data.
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from hass import statebackup
from hass.tests import test_two_chat_restore as trc

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "scripts/hass"
DOC = ROOT / "docs/hass/finish-off-operator-run.md"
INSPECT = ("demo_restore_inventory", "demo_resume_step", "demo_pre_yes_gate", "demo_served_comparison")


def tree(*roots):
    """Every file and link under each root (or the root file itself): path -> (mode, sha256 or link target)."""
    out = {}
    for root in map(Path, roots):
        for path in [root, *sorted(root.rglob("*"))] if root.is_dir() else [root]:
            st = path.lstat()
            if path.is_symlink():
                out[str(path)] = (st.st_mode, "link:" + str(path.readlink()))
            elif path.is_file():
                out[str(path)] = (st.st_mode, hashlib.sha256(path.read_bytes()).hexdigest())
            else:
                out[str(path)] = (st.st_mode, None)
    return out


def _make():
    class OperatorRunTests(trc.TwoChatRestoreTests):
        """Reuses the two-chat restore fixture; its own journeys are run by test_two_chat_restore, not here."""

        def run_tool(self, name, *args, watch):
            """One inspection command as a real subprocess; everything under ``watch`` must be byte-identical."""
            self.assertIn(name, INSPECT)
            before = tree(*watch)
            done = subprocess.run([sys.executable, "-B", str(TOOLS / f"{name}.py"), *map(str, args)],
                                  capture_output=True, text=True, timeout=120, cwd=ROOT)
            self.assertEqual(done.stderr, "", name)
            self.assertEqual(tree(*watch), before, f"{name} changed something it only reads")
            self.log.append((name, done.returncode, done.stdout.strip()))
            return done.returncode, done.stdout.strip()

        def run_restore(self, backup, into, worktree, media):
            """The restore command (`hass/statebackup.py drill`) as a real subprocess: it may create only ``into`` and
            ``media``; the backup and the source state stay byte-identical."""
            self.assertFalse(into.exists() or media.exists())
            keep = tree(backup, self.repo.state)
            siblings = {p.name for p in into.parent.iterdir()} | {p.name for p in media.parent.iterdir()}
            done = subprocess.run([sys.executable, "-B", "hass/statebackup.py", "drill", str(backup), "--into", str(into),
                                   "--worktree", str(worktree), "--media-into", str(media)],
                                  capture_output=True, text=True, timeout=120, cwd=ROOT)
            self.assertEqual(done.stderr, "")
            self.assertEqual(tree(backup, self.repo.state), keep, "the restore changed the backup or the source state")
            appeared = ({p.name for p in into.parent.iterdir()} | {p.name for p in media.parent.iterdir()}) - siblings
            self.assertLessEqual(appeared, {into.name, media.name}, "the restore created something else")
            result = json.loads(done.stdout)
            self.log.append(("statebackup drill", done.returncode, result["result"]))
            return done.returncode, result

        def inspect(self, name, *args):
            return self.run_tool(name, *args, watch=(self.state, self.media, self.wt, *self.held.values()))

        def listing_args(self, chat, version, *, media=True):
            out = ["--state", self.state, "--worktree", self.wt, "--job", self.jobs[chat],
                   "--photo", self.held[chat], "--version", version]
            return (["--media", self.media] if media else []) + out

        def test_one_operator_run(self):
            started = time.monotonic()
            self.log = []
            jobs = self.two_pending()  # the interruption: both cards delivered, no yes yet
            m, g = trc.MCHAT, trc.GCHAT
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                # 1. inventory the backup; a damaged copy is refused and the restore refuses it too
                out = tmp / "backups"
                out.mkdir(mode=0o700)
                made = statebackup.create(self.repo.state, out)
                self.assertEqual(made["result"], "ok", made)
                backup = Path(made["backup"])
                code, said = self.run_tool("demo_restore_inventory", backup, watch=(backup, self.repo.state))
                self.assertEqual(code, 0, said)
                self.assertEqual(said.splitlines()[0], "BACKUP ok items=2 served-state=present", said)
                self.assertEqual(sorted(said.splitlines()[1:]),
                                 sorted(f"ITEM {jobs[c]} waiting-for-yes history=1/1 originals=1 card=1 served=no"
                                        for c in (m, g)), said)
                damaged = tmp / "damaged"
                shutil.copytree(backup, damaged, symlinks=True)
                victim = damaged / "config.json"
                victim.write_bytes(victim.read_bytes() + b" ")
                self.assertEqual(self.run_tool("demo_restore_inventory", damaged, watch=(damaged, self.repo.state)),
                                 (1, "REFUSED backup-not-intact"))
                spare = tmp / "spare-worktree"
                trc.git(self.repo.main, "worktree", "add", "-q", "-b", "hass/spare", str(spare), self.repo.head())
                spare_before = tree(spare)
                code, refused = self.run_restore(damaged, tmp / "not-restored", spare, tmp / "not-restored-media")
                self.assertNotEqual((code, refused["result"]), (0, "ok"), refused)
                self.assertFalse((tmp / "not-restored").exists() or (tmp / "not-restored-media").exists())
                self.assertEqual(tree(spare), spare_before)

                # 2. restore the intact backup on a paused OFF copy, then resume
                self.wt = tmp / "drill-worktree"
                trc.git(self.repo.main, "worktree", "add", "-q", "-b", "hass/drill", str(self.wt), self.repo.head())
                self.media = tmp / "restored-media"
                wt_before = tree(self.wt)
                code, drilled = self.run_restore(backup, tmp / "restored", self.wt, self.media)
                self.assertEqual((code, drilled["result"]), (0, "ok"), drilled)
                self.assertEqual(tree(self.wt), wt_before, "the restore changed the shop worktree")
                self.assertTrue(drilled["paused"], drilled)
                self.state = Path(drilled["state"])
                self.assertTrue(self.state.is_relative_to(tmp / "restored"), drilled)
                self.live = trc._clocked_editor(self)(self.state)
                self.conv = self.open_conv(self.state, self.live)
                self.assertEqual(self.talk(m, "resume changes"), "resume")
                self.held = {}
                for chat in (m, g):
                    self.held[chat] = tmp / f"held-{chat}.png"
                    self.held[chat].write_bytes(trc.LISTINGS[chat]["photo"])
                catalog = self.wt / "storefront-mockup/catalog-products.js"
                served_before = catalog.read_bytes()
                commits = self.commits_in(self.wt)

                # 3. what is next? the current delivered preview; any other version number is refused
                self.assertEqual(self.inspect("demo_resume_step", *self.listing_args(m, 1)), (0, "REVIEW_CURRENT_PREVIEW"))
                self.assertEqual(self.inspect("demo_resume_step", *self.listing_args(m, 2)), (1, "HOLD version-mismatch"))

                # 4. the pre-yes gate, then exactly one coded yes for that version
                self.assertEqual(self.inspect("demo_pre_yes_gate", "before", *self.listing_args(m, 1)),
                                 (0, f"READY yes {jobs[m]}-1"))
                self.assertEqual((catalog.read_bytes(), self.commits_in(self.wt)), (served_before, commits))
                self.assertEqual(self.talk(m, f"yes {jobs[m]}-1"), "approved")
                self.assertEqual(self.commits_in(self.wt), commits + 1)
                self.assertIn(trc.LISTINGS[m]["name"], self.names_in(self.wt))
                self.assertNotIn(trc.LISTINGS[g]["name"], self.names_in(self.wt))

                # 5. the shop serves the approved card; take-down is next; a stale pre-yes receipt now aborts
                self.assertEqual(self.inspect("demo_served_comparison", *self.listing_args(m, 1, media=False)),
                                 (0, "MATCH undo"))
                self.assertEqual(self.inspect("demo_pre_yes_gate", "after", *self.listing_args(m, 1, media=False)),
                                 (0, "SERVED undo"))
                self.assertEqual(self.inspect("demo_resume_step", *self.listing_args(m, 1)), (0, "REVIEW_TAKEDOWN"))
                self.assertEqual(self.inspect("demo_pre_yes_gate", "before", *self.listing_args(m, 1)),
                                 (1, "ABORT listing-not-waiting-for-a-yes"))

                # 6. take-down: `undo` alone changes nothing a visitor sees; its coded yes restores the shop
                self.assertEqual(self.talk(m, "undo"), "proposed")
                self.assertEqual(self.inspect("demo_resume_step", *self.listing_args(m, 1)), (0, "REVIEW_TAKEDOWN"))
                undo, = self.conv.db.execute("SELECT code FROM drafts WHERE state='proposed'").fetchone()
                self.assertEqual(self.talk(m, f"yes {undo}"), "approved")
                self.assertEqual(catalog.read_bytes(), served_before)
                self.assertEqual(self.inspect("demo_resume_step", *self.listing_args(m, 1)), (0, "NOT_SERVED"))
                self.assertEqual(self.inspect("demo_served_comparison", *self.listing_args(m, 1, media=False)),
                                 (1, "MISMATCH not-served"))

                # 7. resume the other owner's waiting listing, untouched by all of the above
                self.assertEqual(self.inspect("demo_resume_step", *self.listing_args(g, 1)), (0, "REVIEW_CURRENT_PREVIEW"))
                self.assertEqual(self.inspect("demo_pre_yes_gate", "before", *self.listing_args(g, 1)),
                                 (0, f"READY yes {jobs[g]}-1"))

            seconds = time.monotonic() - started
            self.assertLess(seconds, 120)
            # every command the document lists was exercised, and nothing it printed carries a name or path
            doc = DOC.read_text("utf-8")
            for name in sorted({n for n, _c, _s in self.log}):
                self.assertIn("hass/statebackup.py drill" if name == "statebackup drill" else f"scripts/hass/{name}.py",
                              doc)
            for _n, _c, said in self.log:
                for chat in (m, g):
                    self.assertNotIn(trc.LISTINGS[chat]["name"], said)
                self.assertNotIn(str(tmp), said)
            self.assertEqual(len(self.log), 16, json.dumps(self.log))

    for name in dir(trc.TwoChatRestoreTests):
        if name.startswith("test_"):
            setattr(OperatorRunTests, name, None)
    return OperatorRunTests


OperatorRunTests = _make()

if __name__ == "__main__":
    unittest.main()
