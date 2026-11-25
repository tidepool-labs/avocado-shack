"""L18: the demo owner's restore inventory (scripts/hass/demo_restore_inventory.py) on two synthetic OFF state backups.

Two owners' cards are pending; backup A is taken with both still waiting, one real yes then posts Mike's listing and backup B is
taken. The command (run as the real command) classifies each listing by job code from the backup alone: history, photo original,
card picture and the served catalog inside the content bundle. It refuses a backup that has history and media but no served-state
input, a backup that does not verify, and one whose history cannot be read; it compares A with B per listing. It only reads: every
file of both backups, the live state dir and the shop are byte-identical (and mtime-identical) around every run.
Fixtures only: throwaway repos, no network, no service, no live site.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hass import statebackup
from hass.tests import test_two_chat_restore as trc
from hass.tests.test_editor import git

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/demo_restore_inventory.py"


def tree(root):
    """Everything under root: path -> (mode, size, mtime_ns, sha256 for files, link target for links)."""
    out = {}
    for path in sorted(Path(root).rglob("*")):
        st = path.lstat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None
        out[str(path.relative_to(root))] = (st.st_mode, st.st_size, st.st_mtime_ns, digest, os.readlink(path) if path.is_symlink() else None)
    return out


def _make():
    class RestoreInventoryTests(trc.TwoChatRestoreTests):
        """Reuses the two-chat restore fixture; its own journeys are run by test_two_chat_restore, not here."""

        def backup(self, out):
            made = statebackup.create(self.repo.state, out)
            self.assertEqual(made["result"], "ok", made)
            self.assertEqual(statebackup.verify(made["backup"])["result"], "ok")
            return Path(made["backup"])

        def run_inv(self, *paths, against=None):
            cmd = [sys.executable, "-B", str(SCRIPT), *map(str, paths)] + (["--against", str(against)] if against else [])
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            self.assertEqual(done.stderr, "")
            return done.returncode, done.stdout.strip().splitlines()

        def tamper_copy(self, src, dst, mutate):
            """A copy of backup `src` that still verifies (manifest kept in step) after `mutate(dir, manifest)`."""
            shutil.copytree(src, dst, symlinks=True)
            manifest_path = Path(dst) / "MANIFEST.json"
            doc = json.loads(manifest_path.read_text("utf-8"))
            mutate(Path(dst), doc)
            manifest_path.write_text(json.dumps(doc), encoding="utf-8")
            os.chmod(manifest_path, 0o600)
            return Path(dst)

        def drop(self, bdir, doc, rel):
            (Path(bdir) / rel).unlink()
            del doc["files"][rel]

        def test_restore_inventory(self):
            jobs = self.two_pending()
            jm, jg = jobs[trc.MCHAT], jobs[trc.GCHAT]
            mike, gee = trc.LISTINGS[trc.MCHAT], trc.LISTINGS[trc.GCHAT]
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "backups"
                out.mkdir(mode=0o700)
                a = self.backup(out)
                live_before = (tree(self.repo.state), self.repo.head(), self.commits())
                scratch_before = sorted(p.name for p in Path(tempfile.gettempdir()).glob("restore-inventory-*"))

                # A: both cards waiting, nothing served, each listing's pieces counted
                snap = tree(a)
                self.assertEqual(self.run_inv(a), (0, [
                    "BACKUP ok items=2 served-state=present",
                    *sorted(f"ITEM {j} waiting-for-yes history=1/1 originals=1 card=1 served=no" for j in (jm, jg))]))
                self.assertEqual(tree(a), snap, "the inventory changed the backup")
                self.assertEqual((tree(self.repo.state), self.repo.head(), self.commits()), live_before)

                # one real yes posts Mike's listing; backup B is taken afterwards
                self.assertEqual(self.talk(trc.MCHAT, f"yes {jm}-1"), "approved")
                b = self.backup(out)
                snap_a, snap_b = tree(a), tree(b)
                code, lines = self.run_inv(b)
                self.assertEqual(code, 0, lines)
                self.assertEqual(lines[0], "BACKUP ok items=2 served-state=present")
                want = {jm: "served history=1/1 originals=1 card=1 served=yes", jg: "waiting-for-yes history=1/1 originals=1 card=1 served=no"}
                self.assertEqual(sorted(lines[1:]), sorted(f"ITEM {j} {text}" for j, text in want.items()), lines)

                # A against B: only Mike's listing moved, and the served-state commit moved with it
                code, lines = self.run_inv(a, against=b)
                self.assertEqual((code, lines), (1, ["COMPARE differs", "CONTENT served-state-commit-differs",
                                                     f"DIFF {jm} class-differs,served-differs"]))
                code, lines = self.run_inv(b, against=a)
                self.assertEqual((code, lines), (1, ["COMPARE differs", "CONTENT served-state-commit-differs",
                                                     f"DIFF {jm} class-differs,served-differs"]))
                again = self.backup(out)  # a second backup of the same state is the same inventory
                self.assertEqual(self.run_inv(b, against=again), (0, ["COMPARE same"]))
                self.assertEqual((tree(a), tree(b)), (snap_a, snap_b), "a comparison changed a backup")

                # a backup with history and media but no served-state input is refused, alone and in a comparison
                def no_bundle(bdir, doc):
                    self.drop(bdir, doc, "content.bundle")
                    del doc["contentCommit"]
                history_only = self.tamper_copy(b, Path(tmp) / "history-only", no_bundle)
                self.assertEqual(statebackup.verify(history_only)["result"], "ok")
                self.assertEqual(self.run_inv(history_only), (1, ["REFUSED no-served-state"]))
                self.assertEqual(self.run_inv(a, against=history_only), (1, ["REFUSED no-served-state"]))
                self.assertEqual(self.run_inv(history_only, against=a), (1, ["REFUSED no-served-state"]))

                # a backup that does not verify, is missing, is a link, or has history that cannot be read is refused
                broken = Path(tmp) / "broken"
                shutil.copytree(b, broken)
                card, = (broken / "media/npp" / jg).glob("card-*.png")
                card.write_bytes(card.read_bytes() + b"x")
                self.assertEqual(self.run_inv(broken), (1, ["REFUSED backup-not-intact"]))
                self.assertEqual(self.run_inv(Path(tmp) / "nope"), (1, ["REFUSED backup-not-intact"]))
                link = Path(tmp) / "link-to-backup"
                link.symlink_to(b, target_is_directory=True)
                self.assertEqual(self.run_inv(link), (1, ["REFUSED backup-not-intact"]))
                loose = Path(tmp) / "loose"
                shutil.copytree(b, loose)
                os.chmod(loose / "transcript.sqlite3", 0o644)
                self.assertEqual(self.run_inv(loose), (1, ["REFUSED backup-not-intact"]))

                def bad_history(bdir, doc):
                    path = Path(bdir) / "transcript.sqlite3"
                    with sqlite3.connect(path) as db:
                        db.execute("DROP TABLE events")
                    doc["files"]["transcript.sqlite3"] = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(self.run_inv(self.tamper_copy(b, Path(tmp) / "no-events", bad_history)), (1, ["REFUSED history-unreadable"]))

                # each listing piece missing from a backup that still verifies is named, not hidden
                def no_original(bdir, doc):
                    for rel in [r for r in doc["files"] if mike_sha in r and r.startswith("media/originals/")]:
                        self.drop(bdir, doc, rel)
                    doc["media"]["originals"] -= 1
                mike_sha = hashlib.sha256(mike["photo"]).hexdigest()
                gap = self.tamper_copy(a, Path(tmp) / "no-original", no_original)
                self.assertEqual(statebackup.verify(gap)["result"], "ok", statebackup.verify(gap))
                code, lines = self.run_inv(gap)
                self.assertEqual((code, f"ITEM {jm} incomplete-photo-original-missing history=1/1 originals=0 card=1 served=no" in lines), (0, True), lines)
                self.assertIn(f"ITEM {jg} waiting-for-yes history=1/1 originals=1 card=1 served=no", lines)
                self.assertEqual(self.run_inv(a, against=gap), (1, ["COMPARE differs", f"DIFF {jm} class-differs,media-differs"]))

                def no_card(bdir, doc):
                    self.drop(bdir, doc, next(r for r in doc["files"] if r.startswith(f"media/npp/{jg}/card-")))
                gap2 = self.tamper_copy(a, Path(tmp) / "no-card", no_card)
                self.assertEqual(statebackup.verify(gap2)["result"], "ok", statebackup.verify(gap2))
                self.assertIn(f"ITEM {jg} incomplete-card-file-missing history=1/1 originals=1 card=0 served=no", self.run_inv(gap2)[1])

                def no_chat_card(bdir, doc):
                    path = Path(bdir) / "transcript.sqlite3"
                    with sqlite3.connect(path) as db:
                        db.execute("DROP TRIGGER IF EXISTS events_no_delete")
                        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
                            db.execute(f'DROP TRIGGER "{name}"')
                        db.execute("DELETE FROM events WHERE direction='out'")
                    doc["files"]["transcript.sqlite3"] = hashlib.sha256(path.read_bytes()).hexdigest()
                gap3 = self.tamper_copy(a, Path(tmp) / "no-chat-card", no_chat_card)
                self.assertEqual(statebackup.verify(gap3)["result"], "ok", statebackup.verify(gap3))
                self.assertIn(f"ITEM {jg} incomplete-card-not-in-history history=1/0 originals=1 card=1 served=no", self.run_inv(gap3)[1])

                def no_chat_photo(bdir, doc):
                    path = Path(bdir) / "transcript.sqlite3"
                    with sqlite3.connect(path) as db:
                        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
                            db.execute(f'DROP TRIGGER "{name}"')
                        db.execute("DELETE FROM events WHERE direction='in'")
                    doc["files"]["transcript.sqlite3"] = hashlib.sha256(path.read_bytes()).hexdigest()
                gap4 = self.tamper_copy(a, Path(tmp) / "no-chat-photo", no_chat_photo)
                self.assertEqual(statebackup.verify(gap4)["result"], "ok", statebackup.verify(gap4))
                code, lines = self.run_inv(gap4)
                self.assertEqual(code, 0, lines)
                for j in (jm, jg):
                    self.assertIn(f"ITEM {j} incomplete-photo-not-in-history history=0/1 originals=1 card=1 served=no", lines)
                self.assertEqual(self.run_inv(a, against=gap4), (1, ["COMPARE differs", *sorted(f"DIFF {j} class-differs,history-differs" for j in (jm, jg))]))

                def ended(bdir, doc):  # G's listing was closed without ever being served
                    path = Path(bdir) / "conversation.sqlite3"
                    with sqlite3.connect(path) as db:
                        db.execute("UPDATE npp_jobs SET closed_at='2026-11-02T18:00:00+00:00' WHERE job_id=?", (jg,))
                    doc["files"]["conversation.sqlite3"] = hashlib.sha256(path.read_bytes()).hexdigest()
                closed = self.tamper_copy(a, Path(tmp) / "ended", ended)
                self.assertEqual(statebackup.verify(closed)["result"], "ok", statebackup.verify(closed))
                self.assertIn(f"ITEM {jg} ended history=1/1 originals=1 card=1 served=no", self.run_inv(closed)[1])

                # a link anywhere on the backup's path is refused, not just on its last part
                real_parent = Path(tmp) / "real-parent"
                real_parent.mkdir(mode=0o700)
                shutil.copytree(b, real_parent / "b")
                parent_link = Path(tmp) / "parent-link"
                parent_link.symlink_to(real_parent, target_is_directory=True)
                self.assertEqual(self.run_inv(real_parent / "b")[0], 0)
                self.assertEqual(self.run_inv(parent_link / "b"), (1, ["REFUSED backup-not-intact"]))

                # the served photo in the bundle is not the approved photo: caught although the name is served
                record = next(r for r in json.loads((self.repo.wt / "storefront-mockup/catalog-products.js").read_bytes()
                                                    .split(b"\n", 1)[0][len(b"const catalog="):].rstrip(b";")) if r["name"] == mike["name"])
                image = self.repo.wt / "storefront-mockup" / record["image"]
                image.write_bytes(gee["photo"])
                git(self.repo.wt, "add", "-A")
                git(self.repo.wt, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "stale photo")
                c = self.backup(out)
                self.assertIn(f"ITEM {jm} served-photo-differs history=1/1 originals=1 card=1 served=yes", self.run_inv(c)[1])
                self.assertEqual(self.run_inv(b, against=c)[1][:1], ["COMPARE differs"])

                # another owner's message with the same picture does not stand in for this listing's own history
                def other_chat(column, value, where):
                    def change(bdir, doc):
                        path = Path(bdir) / "transcript.sqlite3"
                        with sqlite3.connect(path) as db:
                            for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
                                db.execute(f'DROP TRIGGER "{name}"')
                            db.execute(f"UPDATE events SET {column}=? WHERE {where}", (value, *wherearg))
                        doc["files"]["transcript.sqlite3"] = hashlib.sha256(path.read_bytes()).hexdigest()
                    return change
                wherearg = (f"{jg}-1",)
                moved_chat = self.tamper_copy(a, Path(tmp) / "card-in-other-chat", other_chat("chat", trc.MCHAT, "draft_code=?"))
                self.assertEqual(statebackup.verify(moved_chat)["result"], "ok", statebackup.verify(moved_chat))
                self.assertIn(f"ITEM {jg} incomplete-card-not-in-history history=1/0 originals=1 card=1 served=no", self.run_inv(moved_chat)[1])
                wrong_code = self.tamper_copy(a, Path(tmp) / "card-wrong-code", other_chat("draft_code", f"{jm}-1", "draft_code=?"))
                self.assertIn(f"ITEM {jg} incomplete-card-not-in-history history=1/0 originals=1 card=1 served=no", self.run_inv(wrong_code)[1])
                wherearg = (jg,)
                photo_elsewhere = self.tamper_copy(a, Path(tmp) / "photo-in-other-chat", other_chat("chat", trc.MCHAT, "draft_code=?"))
                self.assertIn(f"ITEM {jg} incomplete-photo-not-in-history history=0/1 originals=1 card=1 served=no", self.run_inv(photo_elsewhere)[1])
                wrong_job = self.tamper_copy(a, Path(tmp) / "photo-wrong-job", other_chat("draft_code", jm, "draft_code=?"))
                self.assertIn(f"ITEM {jg} incomplete-photo-not-in-history history=0/1 originals=1 card=1 served=no", self.run_inv(wrong_job)[1])

                # a job code that is not a job code is refused, never printed
                def odd_job(bdir, doc):
                    path = Path(bdir) / "conversation.sqlite3"
                    with sqlite3.connect(path) as db:
                        db.execute("UPDATE npp_jobs SET job_id=? WHERE job_id=?", ("secret \x1b[31m text", jg))
                    doc["files"]["conversation.sqlite3"] = hashlib.sha256(path.read_bytes()).hexdigest()
                odd = self.tamper_copy(a, Path(tmp) / "odd-job", odd_job)
                self.assertEqual(statebackup.verify(odd)["result"], "ok", statebackup.verify(odd))
                self.assertEqual(self.run_inv(odd), (1, ["REFUSED bad-listing-record"]))
                self.assertEqual(self.run_inv(a, against=odd), (1, ["REFUSED bad-listing-record"]))

                # a served-state catalog that is not a list of named records is refused, not read as "nothing served"
                catalog = self.repo.wt / "storefront-mockup/catalog-products.js"
                good_catalog = catalog.read_bytes()
                for bad in (b"const catalog={};\n", b'const catalog=[3,{"name":"x"}];\n', b'const catalog=[{"id":"nameless"}];\n'):
                    catalog.write_bytes(bad + good_catalog.split(b"\n", 1)[1])
                    git(self.repo.wt, "add", "-A")
                    git(self.repo.wt, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "odd catalog")
                    self.assertEqual(self.run_inv(self.backup(out)), (1, ["REFUSED served-state-unreadable"]), bad)

                # nothing was written anywhere by any run: backups, live state, scratch folders
                self.assertEqual((tree(a), tree(b)), (snap_a, snap_b))
                self.assertEqual(sorted(p.name for p in Path(tempfile.gettempdir()).glob("restore-inventory-*")), scratch_before)

    # Only the inventory's own journey runs here; the inherited journeys belong to test_two_chat_restore.
    for name in dir(trc.TwoChatRestoreTests):
        if name.startswith("test"):
            setattr(RestoreInventoryTests, name, None)
    return RestoreInventoryTests


RestoreInventoryTests = _make()

if __name__ == "__main__":
    unittest.main()
