"""L10: an interrupted or half-copied backup is refused before anything is restored, and the owner recovers the previous intact one.

The source install has two backups. The OLDER one (A) was taken after listing 1 was posted. The NEWER one (B) was taken while
listing 2 was only a card waiting for a yes. Then B is damaged the way a stopped copy, a full disk or a pulled cable does it: a
file cut short (the saved conversation, a picture, the saved site), a file gone, the last step of the backup never written, or the
backup's own list cut short. Nothing here is a real chat, a real listing or a live service.

Checked, for every kind of damage: the check says "corrupt" and names a problem; a restore drill from it is refused and leaves
NEITHER the state folder NOR the picture folder behind; the source install does not move. Then the installer's own recovery
steps (list, take the newest backup that verifies, restore it paused) land on A: listing 1 is on the site with its approved
picture, listing 2 is not (it was never posted), the old yes for listing 1 posts nothing a second time, and a yes for listing 2
posts nothing because the restored copy never saw it. Restoring into a folder that already exists is refused and leaves it as it
was, and a half-copied state folder is reported by the health check instead of being started on.
"""

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from hass import health, statebackup
from hass.npp.job import Card, Plan
from hass.skills.testkit import _clocked_editor
from hass.tests import test_npp_edits as edits_tests
from hass.tests import test_npp_undo_journey as journey
from hass.tests import test_two_chat_restore as two
from hass.tests.test_editor import git
from hass.tests.test_npp_second_product import png

FIRST = dict(price="12.34", name="Fixture quince jelly", alt="Red jar", photo=png((200, 20, 20)), card=png((250, 120, 120)))
SECOND = dict(price="8.75", name="Fixture orchard honey", alt="Gold jar", photo=png((20, 20, 200)), card=png((120, 120, 250)))
BY_PRICE = {v["price"]: v for v in (FIRST, SECOND)}
CHAT = two.MCHAT


def sha(data):
    return hashlib.sha256(data).hexdigest()


class IncompleteBackupTests(two.TwoChatRestoreTests):
    # ---- fixtures: the two-chat helpers, with this module's own two listings -----------------------------------------
    def render_stage(self, work, listing):
        mine = BY_PRICE[listing["sellingPrice"]]
        ops = [{"op": "maker.add", "args": {**journey.MAKER, "key": mine["name"] + " Farm", "name": mine["name"] + " Farm"}},
               {"op": "product.add", "args": {
                   "name": mine["name"], "brand": mine["name"] + " Farm", "producerKey": mine["name"] + " Farm",
                   "category": "pantry", "description": "Fixture listing.", "sellingPrice": listing["sellingPrice"],
                   "photo": work.request["attachments"][0], "imageAlt": mine["alt"]}}]
        out = self.live.prepare(ops)
        assert out["result"] == "ok", out
        path, digest = next(iter(out["draft"]["assets"].items()))
        return Card(out["draft"], mine["card"], "raw", path, digest.removeprefix("sha256:"), "picture: your own photo")

    def start_stage(self, work):
        price = work.request["slots"]["intake"].get("price")
        return Plan(listing={"name": BY_PRICE[price]["name"], "sellingPrice": price})

    def listing(self, mine):
        """One owner message with a photo; the card is made and delivered. Returns the job id."""
        before = {r[0] for r in self.conv.db.execute("SELECT job_id FROM npp_jobs")}
        self.assertEqual(self.talk(CHAT, f"sell ${mine['price']}", photo=mine["photo"]), "npp-working")
        self.pump(self.conv)
        job, = {r[0] for r in self.conv.db.execute("SELECT job_id FROM npp_jobs")} - before
        self.deliver(job)
        return job

    def source(self, tmp):
        """Listing 1 posted -> backup A; listing 2 waiting for its yes -> backup B. Returns (out dir, A, B, jobs)."""
        cfg_path = self.repo.state / "config.json"
        cfg = json.loads(cfg_path.read_text("utf-8"))
        cfg["settings"].update(two.TWO, npp=True, approvalNeedsCode=True)
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        self.live = self.engine
        self.conv = self.open_conv(self.repo.state, self.engine)
        self.base_site = self.site()
        out = Path(tmp) / "backups"
        out.mkdir(mode=0o700)
        job1 = self.listing(FIRST)
        self.assertEqual(self.talk(CHAT, f"yes {job1}-1"), "approved")
        self.posted = (self.repo.head(), self.commits(), self.site())
        made_a = statebackup.create(self.repo.state, out, now=self.now)
        self.assertEqual(made_a["result"], "ok", made_a)
        self.now += journey.timedelta(hours=1)
        job2 = self.listing(SECOND)
        self.assertEqual((self.repo.head(), self.commits(), self.site()), self.posted)  # a card waiting posts nothing
        made_b = statebackup.create(self.repo.state, out, now=self.now)
        self.assertEqual(made_b["result"], "ok", made_b)
        a, b = Path(made_a["backup"]), Path(made_b["backup"])
        self.assertLess(a.name, b.name)
        self.assertEqual((statebackup.verify(a)["result"], statebackup.verify(b)["result"]), ("ok", "ok"))
        return out, a, b, (job1, job2)

    def damaged_copy(self, backup, out, how):
        """A copy of B, hurt the way an interrupted copy hurts it. The listing's other entries stay as they were."""
        copy = out / "hass-state-20990101T000000Z"  # the newest name: a recovery that only sorts by name would pick it
        shutil.copytree(backup, copy)
        files = sorted(json.loads((copy / statebackup.MANIFEST).read_text("utf-8"))["files"])
        stores = [f for f in files if f in ("conversation.sqlite3", "transcript.sqlite3")]
        photos = [f for f in files if f.startswith("media/originals/") and not f.endswith(".json")]
        bundle = statebackup.BUNDLE
        victim = {"conversation": stores[0] if stores else None, "photo": photos[0] if photos else None,
                  "site": bundle if bundle in files else None, "config": statebackup.CONFIG}.get(how)
        if how in ("conversation", "photo", "site"):
            self.assertIsNotNone(victim, (how, files))
            path = copy / victim
            data = path.read_bytes()
            self.assertGreater(len(data), 40)
            path.write_bytes(data[: len(data) // 2])  # a copy that stopped half way
        elif how == "config":
            (copy / victim).write_bytes(b"")
        elif how == "listed-file-gone":
            gone = next(f for f in files if f not in (statebackup.CONFIG, statebackup.MANIFEST))
            (copy / gone).unlink()
        elif how == "last-step-never-written":  # create() writes the manifest last: stopped before it
            (copy / statebackup.MANIFEST).unlink()
        elif how == "list-cut-short":
            path = copy / statebackup.MANIFEST
            path.write_bytes(path.read_bytes()[:60])
        else:
            raise AssertionError(how)
        return copy

    def recover_newest_good(self, out):
        """The installer's steps, written out: list newest first, verify each, take the first that verifies."""
        skipped = []
        for row in statebackup.list_backups(str(out)):
            candidate = out / row["backup"]
            if row["complete"] and statebackup.verify(candidate)["result"] == "ok":
                return candidate, skipped
            skipped.append(row["backup"])
        return None, skipped

    def drill_from(self, backup, tmp, name="restored"):
        wt = Path(tmp) / f"{name}-worktree"
        git(self.repo.main, "worktree", "add", "-q", "-b", f"hass/{name}", str(wt), self.repo.head())
        return wt, statebackup.drill(backup, Path(tmp) / name, wt, media_into=Path(tmp) / f"{name}-media")

    def untouched(self):
        return (self.repo.head(), self.commits(), self.site(), self.repo.status())

    # ---- every kind of damage is refused, restores nothing, and moves nothing -------------------------------------------
    def check_damage(self, how):
        with tempfile.TemporaryDirectory() as tmp:
            out, a, b, _jobs = self.source(tmp)
            source = self.untouched()
            bad = self.damaged_copy(b, out, how)
            checked = statebackup.verify(bad)
            self.assertEqual(checked["result"], "corrupt", checked)
            self.assertTrue(checked["problems"], checked)
            wt, drilled = self.drill_from(bad, tmp, "refused")
            self.assertEqual(drilled["result"], "corrupt", drilled)
            self.assertEqual(drilled["step"], "verify", drilled)
            self.assertFalse((Path(tmp) / "refused").exists())
            self.assertFalse((Path(tmp) / "refused-media").exists())
            self.assertEqual(git(wt, "status", "--porcelain"), "")
            self.assertEqual(self.untouched(), source)
            # the check never repairs or deletes: the damaged copy and the good ones are still there
            self.assertTrue(bad.is_dir() and a.is_dir() and b.is_dir())
            self.assertEqual(statebackup.verify(b)["result"], "ok")  # the undamaged original: a real control

    def test_i2_the_list_flags_an_unfinished_backup_and_ignores_a_partial_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, a, b, _jobs = self.source(tmp)
            bad = self.damaged_copy(b, out, "last-step-never-written")
            partial = out / ".hass-state-20990202T000000Z.partial-424242"  # what a stopped create() leaves while it builds
            partial.mkdir(mode=0o700)
            (partial / "state.db").write_bytes(b"half a file")
            rows = {row["backup"]: row for row in statebackup.list_backups(str(out))}
            self.assertEqual(set(rows), {a.name, b.name, bad.name})  # the partial folder is not offered at all
            self.assertTrue(rows[a.name]["complete"] and rows[b.name]["complete"])
            self.assertFalse(rows[bad.name]["complete"])
            self.assertEqual(rows[bad.name]["problem"], "no manifest (interrupted)")
            self.assertEqual(statebackup.verify(partial)["result"], "corrupt")
            self.assertEqual(sorted(rows, reverse=True)[0], bad.name)  # newest by name, yet not the one to use
            chosen, skipped = self.recover_newest_good(out)
            self.assertEqual((chosen, skipped), (b, [bad.name]))  # the newest that verifies is the intact B

    # ---- recovery: the previous intact backup, no yes replayed -----------------------------------------------------------
    def test_i3_the_previous_intact_backup_brings_back_listing_one_and_replays_no_yes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, a, b, (job1, job2) = self.source(tmp)
            source = self.untouched()
            for how in ("conversation", "photo"):  # B is cut short; so is its newer copy
                self.damaged_copy(b, out, how).rename(out / f"hass-state-2099010{1 if how == 'photo' else 2}T000000Z")
            shutil.rmtree(b)
            chosen, skipped = self.recover_newest_good(out)
            self.assertEqual(chosen, a)
            self.assertEqual(len(skipped), 2)
            wt, drilled = self.drill_from(chosen, tmp)
            self.assertEqual(drilled["result"], "ok", drilled)
            self.assertTrue(drilled["paused"], drilled)
            state = Path(drilled["state"])
            self.live = _clocked_editor(self)(state)
            self.conv = self.open_conv(state, self.live)
            count, catalog = self.commits_in(wt), self.catalog_in(wt)
            # the restored site has listing 1, with the picture that was approved, and not listing 2
            records = self.names_in(wt)
            self.assertEqual(set(records) & {FIRST["name"], SECOND["name"]}, {FIRST["name"]})
            card = records[FIRST["name"]]
            self.assertEqual((card["sellingPrice"], card["imageAlt"]), (FIRST["price"], FIRST["alt"]))
            self.assertEqual(sha((wt / "storefront-mockup" / card["image"]).read_bytes()), sha(FIRST["photo"]))
            # the restored conversation knows listing 1 only; the saved chat still names its code
            self.assertEqual({r[0] for r in self.conv.db.execute("SELECT job_id FROM npp_jobs")}, {job1})
            for _ in range(3):  # a restart: the chat keeps running, nothing is posted by itself
                self.pump(self.conv)
            self.assertEqual((self.commits_in(wt), self.catalog_in(wt)), (count, catalog))
            # while paused, no yes saves anything; after resume, the old yes for listing 1 and the missing code for listing 2 post nothing
            self.assertEqual(self.talk(CHAT, f"yes {job1}-1"), "no-target")
            self.assertEqual(self.talk(CHAT, "resume changes"), "resume")
            for old in (f"yes {job1}-1", f"yes {job2}-1", f"yes {job2}", "yes"):
                self.assertIn(self.talk(CHAT, old), two.REFUSED, old)  # a code this copy never issued is answered, not posted
                self.assertEqual((self.commits_in(wt), self.catalog_in(wt)), (count, catalog), old)
            self.assertEqual(git(wt, "status", "--porcelain"), "")
            self.assertEqual(self.untouched(), source)  # the source install never saw the drill

    def test_i4_an_intact_newest_backup_is_the_one_chosen_and_still_posts_nothing(self):
        # Control: the undamaged newest backup restores listing 2's waiting card, paused, and posts nothing.
        with tempfile.TemporaryDirectory() as tmp:
            out, a, b, (job1, job2) = self.source(tmp)
            chosen, skipped = self.recover_newest_good(out)
            self.assertEqual((chosen, skipped), (b, []))
            wt, drilled = self.drill_from(chosen, tmp)
            self.assertEqual(drilled["result"], "ok", drilled)
            state = Path(drilled["state"])
            self.live = _clocked_editor(self)(state)
            self.conv = self.open_conv(state, self.live)
            count, catalog = self.commits_in(wt), self.catalog_in(wt)
            self.assertEqual({r[0] for r in self.conv.db.execute("SELECT job_id FROM npp_jobs")}, {job1, job2})
            self.assertEqual(self.talk(CHAT, f"yes {job2}-1"), "no-target")  # paused: nothing saved yet
            self.assertEqual((self.commits_in(wt), self.catalog_in(wt)), (count, catalog))
            self.assertEqual(set(self.names_in(wt)) & {FIRST["name"], SECOND["name"]}, {FIRST["name"]})

    # ---- never start on, or write into, an incomplete or existing folder ---------------------------------------------------
    def test_i5_restoring_into_a_folder_that_exists_is_refused_and_leaves_it_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, a, b, _jobs = self.source(tmp)
            wt = Path(tmp) / "wt"
            git(self.repo.main, "worktree", "add", "-q", "-b", "hass/again", str(wt), self.repo.head())
            into = Path(tmp) / "half-restored"
            into.mkdir(mode=0o700)
            (into / "leftover.txt").write_bytes(b"from an earlier, stopped restore")
            before = sorted((p.name, sha(p.read_bytes())) for p in into.iterdir())
            refused = statebackup.restore(a, into, wt, paused=True)
            self.assertEqual(refused["result"], "refused", refused)
            self.assertIn("already exists", refused["problems"][0])
            self.assertEqual(sorted((p.name, sha(p.read_bytes())) for p in into.iterdir()), before)
            self.assertEqual(git(wt, "status", "--porcelain"), "")

    def test_i6_a_half_copied_state_folder_is_reported_not_started_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, a, b, _jobs = self.source(tmp)
            wt, drilled = self.drill_from(a, tmp)
            self.assertEqual(drilled["result"], "ok", drilled)
            state = Path(drilled["state"])
            self.assertEqual(health.check(state)[0], [])  # control: the whole folder is healthy
            copy = Path(tmp) / "hand-copied"
            shutil.copytree(state, copy)
            stores = [copy / "conversation.sqlite3"]
            self.assertTrue(stores)
            for store in stores:
                data = store.read_bytes()
                store.write_bytes(data[: len(data) // 2])  # copied half way
            problems, _info, unsafe = health.check(copy)
            self.assertTrue(problems or unsafe, (problems, unsafe))
            self.assertTrue({p["check"] for p in problems} & set(statebackup.STRUCTURAL) or unsafe, problems)


def _damage_test(how):
    def test(self):  # one fresh install per kind of damage
        self.check_damage(how)
    return test


for _how in ("conversation", "photo", "site", "config", "listed-file-gone", "last-step-never-written", "list-cut-short"):
    setattr(IncompleteBackupTests, "test_i1_" + _how.replace("-", "_") + "_damage_is_refused_and_leaves_nothing_behind",
            _damage_test(_how))


# Run only this module's own journeys, not the inherited two-chat or HRM-04 ones (those have their own modules).
for _name in dir(two.TwoChatRestoreTests):
    if _name.startswith(("test_t", "test_c")):
        setattr(IncompleteBackupTests, _name, None)


if __name__ == "__main__":
    unittest.main()
