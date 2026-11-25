"""L20: one OFF operator run, end to end, with the real commands in the order docs/hass/finish-off-operator-run.md gives.

The demo is interrupted while both owners' cards wait for a yes. The operator then, using only the shipped read-only commands:
  1. inventories the state backup (a damaged copy is refused and cannot be restored);
  2. restores it on a paused OFF copy and resumes;
  3. asks the resume step what is next (the current delivered preview; an older/newer version number is refused);
  4. runs the pre-yes gate, and only then the owner types the one coded yes for exactly that version;
  5. compares what the shop serves with the approved card, and asks the resume step again (take-down is next);
     a stale pre-yes receipt for the same version now aborts;
  6. takes the card down with `undo` + its coded yes; the shop is back to how it was, the resume step says NOT_SERVED;
  7. resumes the other owner's waiting listing, which was never touched.
Every command runs as a real subprocess and only reads: the restored state, transcript, catalog and held photo are
byte-identical around each run. Fixtures only (throwaway repos), no network, service, live site or private data.
"""
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


def _make():
    class OperatorRunTests(trc.TwoChatRestoreTests):
        """Reuses the two-chat restore fixture; its own journeys are run by test_two_chat_restore, not here."""

        def run_tool(self, name, *args):
            before = self.snapshot()
            done = subprocess.run([sys.executable, "-B", str(TOOLS / f"{name}.py"), *map(str, args)],
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual(done.stderr, "", name)
            self.assertEqual(self.snapshot(), before, f"{name} changed something it only reads")
            self.log.append((name, done.returncode, done.stdout.strip()))
            return done.returncode, done.stdout.strip()

        def snapshot(self):
            paths = getattr(self, "watched", [])
            return [p.read_bytes() if p.exists() else None for p in paths]

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
                # 1. inventory the backup; a damaged copy is refused and does not restore
                out = tmp / "backups"
                out.mkdir(mode=0o700)
                made = statebackup.create(self.repo.state, out)
                self.assertEqual(made["result"], "ok", made)
                backup = Path(made["backup"])
                code, said = self.run_tool("demo_restore_inventory", backup)
                self.assertEqual(code, 0, said)
                self.assertEqual(said.splitlines()[0], "BACKUP ok items=2 served-state=present", said)
                self.assertEqual(sorted(said.splitlines()[1:]),
                                 sorted(f"ITEM {jobs[c]} waiting-for-yes history=1/1 originals=1 card=1 served=no"
                                        for c in (m, g)), said)
                damaged = tmp / "damaged"
                shutil.copytree(backup, damaged, symlinks=True)
                victim = damaged / "config.json"
                victim.write_bytes(victim.read_bytes() + b" ")
                self.assertEqual(self.run_tool("demo_restore_inventory", damaged), (1, "REFUSED backup-not-intact"))
                spare = tmp / "spare-worktree"
                trc.git(self.repo.main, "worktree", "add", "-q", "-b", "hass/spare", str(spare), self.repo.head())
                refused = statebackup.drill(damaged, tmp / "not-restored", spare, media_into=tmp / "not-restored-media")
                self.assertNotEqual(refused["result"], "ok", refused)
                self.assertFalse((tmp / "not-restored").exists())

                # 2. restore the intact backup on a paused OFF copy, then resume
                self.wt = tmp / "drill-worktree"
                trc.git(self.repo.main, "worktree", "add", "-q", "-b", "hass/drill", str(self.wt), self.repo.head())
                self.media = tmp / "restored-media"
                drilled = statebackup.drill(backup, tmp / "restored", self.wt, media_into=self.media)
                self.assertEqual(drilled["result"], "ok", drilled)
                self.assertTrue(drilled["paused"], drilled)
                self.state = Path(drilled["state"])
                self.live = trc._clocked_editor(self)(self.state)
                self.conv = self.open_conv(self.state, self.live)
                self.assertEqual(self.talk(m, "resume changes"), "resume")
                self.held = {}
                for chat in (m, g):
                    self.held[chat] = tmp / f"held-{chat}.png"
                    self.held[chat].write_bytes(trc.LISTINGS[chat]["photo"])
                catalog = self.wt / "storefront-mockup/catalog-products.js"
                self.watched = [self.state / "conversation.sqlite3", self.state / "transcript.sqlite3", catalog,
                                *self.held.values()]
                served_before = catalog.read_bytes()
                commits = self.commits_in(self.wt)

                # 3. what is next? the current delivered preview; any other version number is refused
                self.assertEqual(self.run_tool("demo_resume_step", *self.listing_args(m, 1)), (0, "REVIEW_CURRENT_PREVIEW"))
                self.assertEqual(self.run_tool("demo_resume_step", *self.listing_args(m, 2)), (1, "HOLD version-mismatch"))

                # 4. the pre-yes gate, then exactly one coded yes for that version
                self.assertEqual(self.run_tool("demo_pre_yes_gate", "before", *self.listing_args(m, 1)),
                                 (0, f"READY yes {jobs[m]}-1"))
                self.assertEqual((catalog.read_bytes(), self.commits_in(self.wt)), (served_before, commits))
                self.assertEqual(self.talk(m, f"yes {jobs[m]}-1"), "approved")
                self.assertEqual(self.commits_in(self.wt), commits + 1)
                self.assertIn(trc.LISTINGS[m]["name"], self.names_in(self.wt))
                self.assertNotIn(trc.LISTINGS[g]["name"], self.names_in(self.wt))

                # 5. the shop serves the approved card; take-down is next; a stale pre-yes receipt now aborts
                self.assertEqual(self.run_tool("demo_served_comparison", *self.listing_args(m, 1, media=False)),
                                 (0, "MATCH undo"))
                self.assertEqual(self.run_tool("demo_pre_yes_gate", "after", *self.listing_args(m, 1, media=False)),
                                 (0, "SERVED undo"))
                self.assertEqual(self.run_tool("demo_resume_step", *self.listing_args(m, 1)), (0, "REVIEW_TAKEDOWN"))
                self.assertEqual(self.run_tool("demo_pre_yes_gate", "before", *self.listing_args(m, 1)),
                                 (1, "ABORT listing-not-waiting-for-a-yes"))

                # 6. take-down: `undo` alone changes nothing a visitor sees; its coded yes restores the shop
                self.assertEqual(self.talk(m, "undo"), "proposed")
                self.assertEqual(self.run_tool("demo_resume_step", *self.listing_args(m, 1)), (0, "REVIEW_TAKEDOWN"))
                undo, = self.conv.db.execute("SELECT code FROM drafts WHERE state='proposed'").fetchone()
                self.assertEqual(self.talk(m, f"yes {undo}"), "approved")
                self.assertEqual(catalog.read_bytes(), served_before)
                self.assertEqual(self.run_tool("demo_resume_step", *self.listing_args(m, 1)), (0, "NOT_SERVED"))
                self.assertEqual(self.run_tool("demo_served_comparison", *self.listing_args(m, 1, media=False)),
                                 (1, "MISMATCH not-served"))

                # 7. resume the other owner's waiting listing, untouched by all of the above
                self.assertEqual(self.run_tool("demo_resume_step", *self.listing_args(g, 1)), (0, "REVIEW_CURRENT_PREVIEW"))
                self.assertEqual(self.run_tool("demo_pre_yes_gate", "before", *self.listing_args(g, 1)),
                                 (0, f"READY yes {jobs[g]}-1"))

            seconds = time.monotonic() - started
            self.assertLess(seconds, 120)
            # every command the document lists was exercised, and nothing it printed carries a name or path
            doc = DOC.read_text("utf-8")
            for name in sorted({n for n, _c, _s in self.log}):
                self.assertIn(f"scripts/hass/{name}.py", doc)
            for _n, _c, said in self.log:
                for chat in (m, g):
                    self.assertNotIn(trc.LISTINGS[chat]["name"], said)
                self.assertNotIn(str(tmp), said)
            self.assertEqual(len(self.log), 14, json.dumps(self.log))

    for name in dir(trc.TwoChatRestoreTests):
        if name.startswith("test_"):
            setattr(OperatorRunTests, name, None)
    return OperatorRunTests


OperatorRunTests = _make()

if __name__ == "__main__":
    unittest.main()
