"""L11: the OFF walkthrough script (checkout -> photo -> preview -> yes -> served site -> take-down) on fixtures only.

Checked: a good run passes all six steps in order with a total time and a private receipt that holds no photo, path, code or
chat text; a wrong checkout (wrong commit, dirty tree, wrong origin) or a missing/odd photo (missing, empty, a link, a folder,
not a picture, too big) stops at its own step and NOTHING after it runs (the fixture shop is never even built); a preview
made from a different photo than the supplied one stops before any yes is sent and nothing is saved; a take-down that leaves
the card public fails the last step. Throwaway repos, loopback only, no network, no service, no live site.
"""

import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/hidden_listing_walkthrough.py"
SPEC = importlib.util.spec_from_file_location("hidden_listing_walkthrough", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
walk = importlib.util.module_from_spec(SPEC)
sys.modules["hidden_listing_walkthrough"] = walk
SPEC.loader.exec_module(walk)

FIXTURES = Path(__file__).parent / "fixtures" / "media"
ORIGIN = "https://example.invalid/tools"
STEPS = ["checkout", "photo", "preview", "confirm", "served", "takedown"]


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                           "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                          cwd=cwd, check=True, capture_output=True, text=True).stdout


class WalkthroughTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source = self.root / "source"
        (source / "scripts/hass").mkdir(parents=True)
        (source / "scripts/hass/install_a.py").write_bytes(b"# tool\n")
        git(source, "init", "--quiet")
        git(source, "add", "--all")
        git(source, "commit", "--quiet", "--message", "fixture")
        self.repo = self.root / "tools-checkout"
        git(self.root, "clone", "--quiet", "--local", str(source), str(self.repo))
        git(self.repo, "remote", "set-url", "origin", ORIGIN + ".git/")
        self.sha = git(self.repo, "rev-parse", "HEAD").strip()
        self.out_dir = self.root / "receipts"
        self.out_dir.mkdir(mode=0o700)
        self.photo = self.root / "owner-photo.jpg"
        self.photo.write_bytes((FIXTURES / "pixel.jpg").read_bytes())

    def run_walk(self, *, sha=None, photo=None, origin=ORIGIN, out=None, **patches):
        stream = io.StringIO()
        argv = ["--repo", str(self.repo), "--sha", sha or self.sha, "--remote-url", origin,
                "--photo", str(self.photo if photo is None else photo), "--out", str(self.out_dir if out is None else out)]
        status = walk.main(argv, out=stream)
        receipts = sorted(self.out_dir.glob("walkthrough-*.json"))
        doc = json.loads(receipts[-1].read_text("utf-8")) if receipts else None
        return status, stream.getvalue(), doc

    def never_built(self):
        return mock.patch.object(walk, "run_fixture", side_effect=AssertionError("the fixture shop must not be built"))

    # ---- a good run -----------------------------------------------------------------------------------------------------
    def test_w1_a_good_run_passes_every_step_and_records_the_total_time(self):
        for name in ("pixel.jpg", "pixel.png"):
            with self.subTest(photo=name):
                photo = self.root / f"owner-{name}"
                photo.write_bytes((FIXTURES / name).read_bytes())
                for old in self.out_dir.glob("walkthrough-*.json"):
                    old.unlink()
                status, text, doc = self.run_walk(photo=photo)
                self.assertEqual(status, 0, text)
                self.assertEqual([r["step"] for r in doc["steps"]], STEPS)
                self.assertEqual({r["result"] for r in doc["steps"]}, {"PASS"})
                self.assertEqual(doc["result"], "PASS")
                self.assertGreater(doc["total_seconds"], 0)
                self.assertLessEqual(sum(r["seconds"] for r in doc["steps"]), doc["total_seconds"] + 0.05)
                self.assertIn("total", text.splitlines()[-1])
                self.assertEqual([line.split()[1] for line in text.splitlines()[:-1]], STEPS)
                self.assertEqual((doc["service_calls"], doc["network_calls"], doc["local_only"]), (0, 0, True))
                receipt, = self.out_dir.glob("walkthrough-*.json")
                self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)
                preview = next(r for r in doc["steps"] if r["step"] == "preview")
                self.assertEqual(preview["photo_sha12"], doc["photo_sha12"])
                self.assertEqual(next(r for r in doc["steps"] if r["step"] == "confirm")["commits_after_yes"], 1)

    def test_w2_nothing_private_reaches_the_screen_or_the_receipt(self):
        photo_bytes = self.photo.read_bytes()
        import hashlib
        full = hashlib.sha256(photo_bytes).hexdigest()
        status, text, doc = self.run_walk()
        self.assertEqual(status, 0, text)
        receipt = (next(self.out_dir.glob("walkthrough-*.json"))).read_text("utf-8")
        for private in (full, self.sha, str(self.root), "owner-photo", ORIGIN, "iMessage", "@"):
            self.assertNotIn(private, text + receipt, private)
        self.assertIn(full[:12], receipt)  # only the short digest prefix is recorded

    # ---- wrong checkout or missing photo: stop at once, build nothing ------------------------------------------------------
    def test_w3_a_wrong_checkout_stops_at_the_first_step(self):
        (self.repo / "untracked.txt").write_bytes(b"dirty")
        dirty = self.run_walk
        cases = {"dirty tree": lambda: dirty(),
                 "wrong commit": lambda: self.run_walk(sha="0" * 40),
                 "bad sha": lambda: self.run_walk(sha="not-a-sha")}
        for label, call in cases.items():
            with self.subTest(label), self.never_built():
                status, text, doc = call()
                self.assertEqual(status, 1, text)
                self.assertEqual([(r["step"], r["result"]) for r in doc["steps"]], [("checkout", "FAIL")])
                self.assertEqual(doc["result"], "FAIL")
                self.assertNotIn("photo", text.lower().replace("fail checkout", ""))
        (self.repo / "untracked.txt").unlink()
        with self.subTest("wrong origin"), self.never_built():
            status, text, doc = self.run_walk(origin="https://example.invalid/other")
            self.assertEqual(status, 1, text)
            self.assertEqual([(r["step"], r["result"]) for r in doc["steps"]], [("checkout", "FAIL")])
            self.assertIn("wrong-remote", doc["steps"][0]["detail"])

    def test_w4_a_missing_or_odd_photo_stops_before_any_preview(self):
        link = self.root / "link.jpg"
        link.symlink_to(self.photo)
        empty = self.root / "empty.jpg"
        empty.write_bytes(b"")
        text_file = self.root / "note.jpg"
        text_file.write_bytes(b"not a picture at all")
        folder = self.root / "folder.jpg"
        folder.mkdir()
        cases = {"missing": self.root / "nowhere.jpg", "link": link, "empty": empty, "not a picture": text_file, "folder": folder}
        for label, path in cases.items():
            with self.subTest(label), self.never_built():
                status, text, doc = self.run_walk(photo=path)
                self.assertEqual(status, 1, text)
                self.assertEqual([(r["step"], r["result"]) for r in doc["steps"]], [("checkout", "PASS"), ("photo", "FAIL")])
                self.assertNotIn(str(path), text)
        with self.subTest("too big"), self.never_built(), mock.patch.object(walk, "PHOTO_MAX", 10):
            status, text, doc = self.run_walk()
            self.assertEqual([(r["step"], r["result"]) for r in doc["steps"]], [("checkout", "PASS"), ("photo", "FAIL")])

    # ---- the gate before the owner's yes ---------------------------------------------------------------------------------
    def test_w5_a_preview_from_another_photo_stops_before_the_yes(self):
        facts = {}
        real = walk.run_fixture

        def swapped(photo, steps):
            facts.update(real(photo, steps, delivered=(FIXTURES / "pixel.png").read_bytes()))
            return facts

        with mock.patch.object(walk, "run_fixture", swapped):
            status, text, doc = self.run_walk()
        self.assertEqual(status, 1, text)
        self.assertEqual([(r["step"], r["result"]) for r in doc["steps"]],
                         [("checkout", "PASS"), ("photo", "PASS"), ("preview", "FAIL")])
        self.assertIn("not the supplied photo", doc["steps"][-1]["detail"])
        self.assertEqual(facts["yes_sent"], 0)  # the yes was never delivered, so nothing could be saved

    def test_w6_a_card_that_stays_public_after_the_takedown_fails_the_last_step(self):
        from hass.tests import test_npp_undo_journey as journey
        with mock.patch.object(journey.NppUndoJourneyTests, "confirm_hide", lambda self: None):
            status, text, doc = self.run_walk()
        self.assertEqual(status, 1, text)
        self.assertEqual([(r["step"], r["result"]) for r in doc["steps"]][-2:], [("served", "PASS"), ("takedown", "FAIL")])
        self.assertEqual(doc["result"], "FAIL")

    # ---- the receipt folder ------------------------------------------------------------------------------------------------
    def test_w7_the_receipt_folder_must_be_private_and_outside_the_repo(self):
        loose = self.root / "loose"
        loose.mkdir(mode=0o755)
        os.chmod(loose, 0o755)
        inside = walk.ROOT / "hass" / "tests" / "fixtures"
        for label, out in {"missing": self.root / "none", "world-readable": loose, "inside the repo": inside}.items():
            with self.subTest(label), self.never_built():
                stream = io.StringIO()
                status = walk.main(["--repo", str(self.repo), "--sha", self.sha, "--remote-url", ORIGIN,
                                    "--photo", str(self.photo), "--out", str(out)], out=stream)
                self.assertEqual(status, 2, stream.getvalue())
                self.assertEqual(list(out.glob("walkthrough-*")) if out.is_dir() else [], [])


if __name__ == "__main__":
    unittest.main()
