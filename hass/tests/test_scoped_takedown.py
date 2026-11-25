"""L9: a take-down reaches only the item it names, and the neighbouring listing and photo stay exactly as they were.

Two synthetic listings are live: TARGET (the hidden-item fixture) and NEIGHBOR, each with its own photo. The take-down is the
real `product.hide` draft and apply. Checked: a wrong or unknown item id never counts as success (the target is still public and
the check says so); hiding the target changes the public catalog by that one record and nothing else (neighbor record and photo
bytes identical); the same holds after an OFF restart (state backup, isolated restore on a new worktree); the hidden item stays
hidden after the restart, putting it back returns exactly the card it was, and hiding it again leaves the neighbor untouched.
The source install is never touched by the restored copy. Fixtures only: throwaway repos, no network, no service, no live site.
"""

import copy
import hashlib
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from hass import statebackup
from hass.skills.testkit import _clocked_editor
from hass.tests.test_conversation import SETTINGS, T0
from hass.tests.test_editor import git
from hass.tests.test_npp_second_product import png
from hass.tests.test_set_photo import PhotoRepo

CATALOG = "storefront-mockup/catalog-products.js"
MAKER = {"key": "Fixture Orchard", "name": "Fixture Orchard", "place": "Test Town", "story": "Makes fixtures."}
ITEMS = {
    "target": dict(name="Fixture hidden TESTITEM", price="12.34", alt="Red jar", photo=png((200, 20, 20))),
    "neighbor": dict(name="Fixture neighbor honey", price="8.75", alt="Blue jar", photo=png((20, 20, 200))),
}
PRIVATE = ("cost", "qty", "quantity", "stock", "count", "margin", "wholesale", "supplier")


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ScopedTakedownTests(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        self.now = T0
        self._clock = lambda: self.now
        self.engine = _clocked_editor(self)(self.repo.state)
        self.ids = {}
        ops = [{"op": "maker.add", "args": MAKER}]
        for label, item in ITEMS.items():
            ops.append({"op": "product.add", "args": {
                "name": item["name"], "brand": MAKER["name"], "producerKey": MAKER["key"], "category": "pantry",
                "description": f"{label} listing.", "sellingPrice": item["price"], "photo": self.repo.store(item["photo"]),
                "imageAlt": item["alt"]}})
        self.apply(self.engine, ops)
        for label, item in ITEMS.items():
            self.ids[label] = next(p["id"] for p in self.repo.catalog() if p["name"] == item["name"])
        self.assertNotEqual(*self.ids.values())
        cfg_path = self.repo.state / "config.json"  # the photo store is part of the install: the backup carries it
        cfg = json.loads(cfg_path.read_text("utf-8"))
        cfg["settings"].update(SETTINGS, npp=True, approvalNeedsCode=True)
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        self.live = self.snapshot(self.repo.wt)

    # ---- helpers -----------------------------------------------------------------------------------------------------
    def apply(self, engine, ops):
        self.now += timedelta(seconds=1)
        out = engine.prepare(ops)
        self.assertEqual(out["result"], "ok", out)
        draft = out["draft"]
        applied = engine.apply(draft["change_id"], draft["draft_hash"])
        self.assertEqual(applied["result"], "applied", applied)
        return applied

    def public(self, wt):
        raw = (Path(wt) / CATALOG).read_bytes().split(b"\n", 1)[0][len(b"const catalog="):].rstrip(b";")
        return {p["id"]: p for p in json.loads(raw)}

    def snapshot(self, wt):
        """Public catalog records by id and the photo bytes behind each, as a visitor would be served them."""
        records = self.public(wt)
        photos = {pid: sha((Path(wt) / "storefront-mockup" / rec["image"]).read_bytes()) for pid, rec in records.items()}
        return {"records": copy.deepcopy(records), "photos": photos, "catalog": (Path(wt) / CATALOG).read_bytes()}

    def only_target_left(self, before, after, target_id):
        """True when `after` equals `before` except that target_id is gone: same other records, same other photo bytes."""
        want = {k: v for k, v in before["records"].items() if k != target_id}
        want_photos = {k: v for k, v in before["photos"].items() if k != target_id}
        return after["records"] == want and after["photos"] == want_photos

    def takedown_succeeded(self, before, after, target_id):
        """The success test a person cares about: the item is gone AND everything else is byte-identical."""
        return target_id not in after["records"] and self.only_target_left(before, after, target_id)

    def hide_ops(self, pid):
        return [{"op": "product.hide", "args": {"id": pid}}]

    # ---- the journeys ------------------------------------------------------------------------------------------------
    def test_s1_the_fixture_starts_with_two_public_cards_and_no_private_fields(self):
        self.assertLessEqual({i["name"] for i in ITEMS.values()}, {r["name"] for r in self.live["records"].values()})
        self.assertEqual(sorted(self.ids), ["neighbor", "target"])
        self.assertNotEqual(self.live["photos"][self.ids["target"]], self.live["photos"][self.ids["neighbor"]])
        for rec in self.live["records"].values():
            self.assertTrue(set(rec) <= {"id", "name", "brand", "category", "image", "description", "producerKey", "displayBrand",
                                        "imageAlt", "sellingPrice", "addedOn"}, sorted(rec))
            self.assertFalse([k for k in rec if k.lower().startswith(PRIVATE)])

    def test_s2_a_wrong_or_unknown_id_is_never_success(self):
        head, site = self.repo.head(), self.repo.read(CATALOG)
        for bad in ("no-such-item", self.ids["target"] + "x", self.ids["target"][:-1], ""):
            out = self.engine.prepare(self.hide_ops(bad))
            self.assertIn(out["result"], ("not-found", "invalid"), bad)  # refused before any draft exists
            self.assertEqual((self.repo.head(), self.repo.read(CATALOG)), (head, site), bad)
        self.assertEqual(self.snapshot(self.repo.wt), self.live)
        # a real item, but the WRONG one: the neighbor goes down, the target is still public, and the success check says no
        self.apply(self.engine, self.hide_ops(self.ids["neighbor"]))
        after = self.snapshot(self.repo.wt)
        self.assertFalse(self.takedown_succeeded(self.live, after, self.ids["target"]))
        self.assertIn(self.ids["target"], after["records"])
        self.assertEqual(after["records"][self.ids["target"]], self.live["records"][self.ids["target"]])
        self.assertTrue(self.takedown_succeeded(self.live, after, self.ids["neighbor"]))  # that WAS the neighbor's take-down
        self.apply(self.engine, [{"op": "product.restore", "args": {"id": self.ids["neighbor"]}}])  # put back
        self.assertEqual(self.snapshot(self.repo.wt), {**self.live, "catalog": self.repo.read(CATALOG)})

    def test_s3_hiding_the_target_changes_one_record_and_nothing_else(self):
        self.apply(self.engine, self.hide_ops(self.ids["target"]))
        after = self.snapshot(self.repo.wt)
        self.assertTrue(self.takedown_succeeded(self.live, after, self.ids["target"]))
        self.assertEqual(after["records"][self.ids["neighbor"]], self.live["records"][self.ids["neighbor"]])
        self.assertEqual(after["photos"][self.ids["neighbor"]], sha(ITEMS["neighbor"]["photo"]))
        self.assertEqual(self.repo.product(self.ids["target"])["status"], "hidden")
        self.assertEqual(self.repo.status(), "")
        head = self.repo.head()
        self.assertEqual(self.engine.prepare(self.hide_ops(self.ids["target"]))["result"], "refused")  # already hidden: no second draft
        self.assertEqual(self.repo.head(), head)
        self.assertTrue(self.takedown_succeeded(self.live, self.snapshot(self.repo.wt), self.ids["target"]))

    def test_s4_the_hidden_item_stays_hidden_through_an_off_restart_and_the_neighbor_never_moves(self):
        self.apply(self.engine, self.hide_ops(self.ids["target"]))
        hidden = self.snapshot(self.repo.wt)
        source = (self.repo.head(), self.repo.read(CATALOG), int(git(self.repo.wt, "rev-list", "--count", "HEAD")))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "backups"
            out.mkdir(mode=0o700)
            made = statebackup.create(self.repo.state, out)
            self.assertEqual(made["result"], "ok", made)
            backup = Path(made["backup"])
            self.assertEqual(statebackup.verify(backup)["result"], "ok")
            wt = Path(tmp) / "drill-worktree"
            git(self.repo.main, "worktree", "add", "-q", "-b", "hass/drill", str(wt), self.repo.head())
            drilled = statebackup.drill(backup, Path(tmp) / "restored", wt, media_into=Path(tmp) / "restored-media")
            self.assertEqual(drilled["result"], "ok", drilled)
            self.assertTrue(drilled["paused"], drilled)
            restarted = self.snapshot(wt)
            self.assertEqual(restarted, hidden)  # same bytes after the restart
            self.assertNotIn(self.ids["target"], restarted["records"])
            self.assertTrue(self.takedown_succeeded(self.live, restarted, self.ids["target"]))
            # putting it back in the restored copy returns exactly the card it was, photo bytes included
            state = Path(drilled["state"])
            engine = _clocked_editor(self)(state)
            self.apply(engine, [{"op": "product.restore", "args": {"id": self.ids["target"]}}])
            back = self.snapshot(wt)
            self.assertEqual(back["records"], self.live["records"])
            self.assertEqual(back["photos"], self.live["photos"])
            self.apply(engine, self.hide_ops(self.ids["target"]))  # and it can go down again
            again = self.snapshot(wt)
            self.assertTrue(self.takedown_succeeded(self.live, again, self.ids["target"]))
            self.assertEqual(again["records"][self.ids["neighbor"]], self.live["records"][self.ids["neighbor"]])
            self.assertEqual(git(wt, "status", "--porcelain"), "")
        self.assertEqual((self.repo.head(), self.repo.read(CATALOG), int(git(self.repo.wt, "rev-list", "--count", "HEAD"))), source)

    def test_s5_a_damaged_backup_never_brings_a_listing_back(self):
        self.apply(self.engine, self.hide_ops(self.ids["target"]))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "backups"
            out.mkdir(mode=0o700)
            backup = Path(statebackup.create(self.repo.state, out)["backup"])
            victim = backup / "config.json"
            victim.write_bytes(victim.read_bytes() + b" ")
            self.assertNotEqual(statebackup.verify(backup)["result"], "ok")
            wt = Path(tmp) / "drill-worktree"
            git(self.repo.main, "worktree", "add", "-q", "-b", "hass/drill", str(wt), self.repo.head())
            drilled = statebackup.drill(backup, Path(tmp) / "restored", wt, media_into=Path(tmp) / "restored-media")
            self.assertNotEqual(drilled["result"], "ok", drilled)
            self.assertFalse((Path(tmp) / "restored").exists())
        self.assertNotIn(self.ids["target"], self.snapshot(self.repo.wt)["records"])  # the live site stays down


if __name__ == "__main__":
    unittest.main()
