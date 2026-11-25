"""L17: the demo operator's post-yes comparison (scripts/hass/demo_served_comparison.py) on a restored OFF install with two owners' cards pending.

After Mike's one real yes the command (run as the real command) says `MATCH undo` only when the shop serves Mike's approved card:
name, price, descriptor, picture text, shelf, brand and the exact photo bytes. Each way the served page can differ (a neighbor's
record, a stale or swapped photo, an edited price or descriptor, a leftover duplicate, a non-public field, a link) prints
MISMATCH with a fixed label, even though the approval history still says the listing was posted, and the command changes nothing.
Fixtures only: throwaway repos, no network, no service, no live site.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hass.tests import test_demo_pre_yes_gate as pre
from hass.tests import test_two_chat_restore as trc

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/demo_served_comparison.py"
HEAD = b"const catalog="


def _make():
    class ServedComparisonTests(pre.PreYesGateTests):
        """Reuses the pre-yes gate fixture; its own journey is run by test_demo_pre_yes_gate, not here."""

        def compare(self, state, wt, job, photo_file, version):
            cmd = [sys.executable, "-B", str(SCRIPT), "--state", str(state), "--worktree", str(wt), "--job", job,
                   "--photo", str(photo_file), "--version", str(version)]
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            self.assertEqual(done.stderr, "")
            return done.returncode, done.stdout.strip()

        def held(self, photo):
            path = Path(self._photos) / f"{pre.d12(photo)}.png"
            path.write_bytes(photo)
            return path

        def edit_catalog(self, wt, change):
            """Rewrite the served catalog's first line after `change(records)`; every other byte is kept. Returns an undo."""
            path = Path(wt) / "storefront-mockup/catalog-products.js"
            original = path.read_bytes()
            first, rest = original.split(b"\n", 1)
            records = json.loads(first[len(HEAD):].rstrip(b";"))
            change(records)
            path.write_bytes(HEAD + json.dumps(records).encode() + b";\n" + rest)
            return lambda: path.write_bytes(original)

        def must_mismatch(self, want, wt, state, conv, job, photo_file, version):
            before = self.fingerprint(wt, state, conv)
            self.assertEqual(self.compare(state, wt, job, photo_file, version), (1, f"MISMATCH {want}"))
            self.assertEqual(before, self.fingerprint(wt, state, conv), want + ": the check changed something")

        def test_served_comparison(self):
            jobs = self.two_pending()
            mike, gee = trc.LISTINGS[trc.MCHAT], trc.LISTINGS[trc.GCHAT]
            source = (self.repo.head(), self.site(), self.commits())
            with tempfile.TemporaryDirectory() as tmp:
                self._photos = Path(tmp) / "photos"
                self._photos.mkdir(mode=0o700)
                wt, state, conv, media = self.restore(tmp)
                self.conv = conv
                self.assertEqual(self.talk(trc.MCHAT, "resume changes"), "resume")
                jm, jg = jobs[trc.MCHAT], jobs[trc.GCHAT]
                mine, theirs = self.held(mike["photo"]), self.held(gee["photo"])
                catalog = Path(wt) / "storefront-mockup/catalog-products.js"

                # before any yes there is no approved card to compare, whichever listing is asked about
                self.must_mismatch("not-approved", wt, state, conv, jm, mine, 1)
                self.must_mismatch("not-approved", wt, state, conv, jg, theirs, 1)

                self.assertEqual(self.talk(trc.MCHAT, f"yes {jm}-1"), "approved")
                self.assertGreaterEqual(conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 1)
                before = self.fingerprint(wt, state, conv)
                self.assertEqual(self.compare(state, wt, jm, mine, 1), (0, "MATCH undo"))
                self.assertEqual(before, self.fingerprint(wt, state, conv), "the matching check changed something")

                # the wrong photo, version or listing; the neighbor's card is still only a card
                self.must_mismatch("photo-mismatch", wt, state, conv, jm, theirs, 1)
                self.must_mismatch("photo-mismatch", wt, state, conv, jg, mine, 1)
                self.must_mismatch("version-mismatch", wt, state, conv, jm, mine, 2)
                self.must_mismatch("not-approved", wt, state, conv, jg, theirs, 1)
                self.must_mismatch("no-such-listing", wt, state, conv, "ffff", mine, 1)
                self.must_mismatch("no-such-listing", wt, state, conv, "../x", mine, 1)
                self.assertEqual(self.compare(state, wt, jm, Path(tmp) / "nope.png", 1), (1, "MISMATCH photo-unreadable"))

                def record(records):
                    return next(r for r in records if r.get("name") == mike["name"])

                # the served record differs from the approved card (the approval history still says posted)
                def swap(key, value):
                    def change(records):
                        record(records)[key] = value
                    return change

                for key, value, want in (("sellingPrice", "99.99", "price-differs"), ("description", "Edited later.", "descriptor-differs"),
                                         ("imageAlt", "Blue jar", "picture-text-differs"), ("category", "fruit", "shelf-differs"),
                                         ("brand", "Someone Else", "brand-differs"), ("producerKey", "Someone Else", "maker-differs"),
                                         ("displayBrand", "Someone Else", "display-brand-differs")):
                    undo = self.edit_catalog(wt, swap(key, value))
                    self.must_mismatch(want, wt, state, conv, jm, mine, 1)
                    undo()
                self.assertEqual(self.compare(state, wt, jm, mine, 1), (0, "MATCH undo"))
                undo = self.edit_catalog(wt, swap("name", gee["name"]))  # the record now claims the neighbor's name
                self.must_mismatch("not-served", wt, state, conv, jm, mine, 1)
                undo()

                # public fields only
                undo = self.edit_catalog(wt, swap("cost", "1.00"))
                self.must_mismatch("non-public-field", wt, state, conv, jm, mine, 1)
                undo()
                undo = self.edit_catalog(wt, swap("description", "Fixture listing, supplier cost $2."))
                self.must_mismatch("descriptor-differs,private-word", wt, state, conv, jm, mine, 1)
                undo()

                # a duplicate record left behind
                undo = self.edit_catalog(wt, lambda records: records.append(dict(record(records))))
                self.must_mismatch("duplicate-served", wt, state, conv, jm, mine, 1)
                undo()
                undo = self.edit_catalog(wt, lambda records: records.append(dict(record(records), name="Fixture jelly twin", id="photo-twin")))
                self.must_mismatch("photo-on-another-item", wt, state, conv, jm, mine, 1)
                undo()

                # the served photo: stale bytes, a neighbor's picture, a missing file, a path out of the shop, a link
                image = Path(wt) / "storefront-mockup" / record(json.loads(catalog.read_bytes().split(b"\n", 1)[0][len(HEAD):].rstrip(b";")))["image"]
                good = image.read_bytes()
                image.write_bytes(gee["photo"])  # stale: the catalog is right, the photo is the other owner's
                self.must_mismatch("served-photo-differs", wt, state, conv, jm, mine, 1)
                image.write_bytes(good + b"x")
                self.must_mismatch("served-photo-differs", wt, state, conv, jm, mine, 1)
                image.write_bytes(good)
                neighbor = Path(wt) / "storefront-mockup/assets/products/photo-product-001.webp"
                kept = neighbor.read_bytes()
                neighbor.write_bytes(good)  # the approved bytes now also sit on another item's picture
                self.must_mismatch("photo-on-another-item", wt, state, conv, jm, mine, 1)
                neighbor.write_bytes(kept)
                # a neighbor whose picture cannot be read safely is not ignored: the site might still follow a link to the approved photo
                twin = Path(wt) / "storefront-mockup/assets/products/photo-product-016.webp"
                kept_twin = twin.read_bytes()
                twin.unlink()
                twin.symlink_to(image)
                self.must_mismatch("other-photo-unreadable", wt, state, conv, jm, mine, 1)
                twin.unlink()
                self.must_mismatch("other-photo-unreadable", wt, state, conv, jm, mine, 1)  # a missing neighbor picture too
                twin.write_bytes(kept_twin)
                self.assertEqual(self.compare(state, wt, jm, mine, 1), (0, "MATCH undo"))
                moved = image.with_name("moved.png")
                image.rename(moved)
                self.must_mismatch("served-photo-unreadable", wt, state, conv, jm, mine, 1)
                image.symlink_to(moved)
                self.must_mismatch("served-photo-unreadable", wt, state, conv, jm, mine, 1)
                image.unlink()
                moved.rename(image)
                undo = self.edit_catalog(wt, swap("image", "../../outside.png"))
                self.must_mismatch("served-photo-unreadable", wt, state, conv, jm, mine, 1)
                undo()
                self.assertEqual(self.compare(state, wt, jm, mine, 1), (0, "MATCH undo"))

                # unusable inputs: a link on the photo, state or worktree path, a catalog that is not a catalog
                leaf = Path(tmp) / "leaf.png"
                leaf.symlink_to(mine)
                self.assertEqual(self.compare(state, wt, jm, leaf, 1), (1, "MISMATCH photo-unreadable"))
                for name, which in (("state-link", "state"), ("worktree-link", "wt")):
                    link = Path(tmp) / name
                    link.symlink_to({"state": state, "wt": wt}[which], target_is_directory=True)
                    use = {"state": state, "wt": wt}
                    use[which] = link
                    code, out = self.compare(use["state"], use["wt"], jm, mine, 1)
                    self.assertEqual(code, 1, (name, out))
                    self.assertIn(out, {"MISMATCH catalog-unreadable", "MISMATCH could-not-check"})
                original = catalog.read_bytes()
                catalog.write_bytes(b"not a catalog\n")
                self.assertEqual(self.compare(state, wt, jm, mine, 1), (1, "MISMATCH catalog-unreadable"))
                catalog.write_bytes(original)
                os.chmod(Path(state) / "conversation.sqlite3", 0o644)  # a store anyone can read is not trusted
                self.assertEqual(self.compare(state, wt, jm, mine, 1), (1, "MISMATCH could-not-check"))
                os.chmod(Path(state) / "conversation.sqlite3", 0o600)
                bad = subprocess.run([sys.executable, "-B", str(SCRIPT), "--state", str(state)], capture_output=True, text=True)
                self.assertEqual((bad.returncode, bad.stdout), (2, ""))

                # after all of it the shop still serves Mike's approved card, and one take-down word removes it
                self.assertEqual(self.compare(state, wt, jm, mine, 1), (0, "MATCH undo"))
                self.assertEqual(self.talk(trc.MCHAT, "undo"), "proposed")
            self.assertEqual((self.repo.head(), self.site(), self.commits()), source)

    # Only the comparison's own journey runs here; inherited journeys belong to their own test files.
    for name in dir(pre.PreYesGateTests):
        if name.startswith("test"):
            setattr(ServedComparisonTests, name, None)
    return ServedComparisonTests


ServedComparisonTests = _make()

if __name__ == "__main__":
    unittest.main()
