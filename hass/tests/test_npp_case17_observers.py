"""NPP acceptance runner: case 17's photo-role expectations have real observers.

Case 17 sends the front and back of one jam in one message. Its contract (``picture_source``, ``label_words_from`` and
``listings``) had no observer, so a strict replay reported the case as a gap however the run went. Contracts:
* picture_source: the job's picture photo and every DELIVERED version's frozen listing photo are the named front;
  the back as picture fails; a never-delivered version is not evidence either way.
* label_words_from: every S2 reading read exactly the named photos in order, and one happened by the first delivered
  card; a front-only reading, a swapped order or a reading only after delivery fails.
* listings: distinct product records across delivered versions (two jobs -> two listings fails).
* With no delivered version (or no reading) the key stays uncovered, so the run reports a gap, never a pass.
Fixtures only: no model, network, live Hass or private recording.
"""
import importlib.util
import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_npp = _load("npp_run_case17_observers_under_test", ROOT / "hass" / "tests" / "npp" / "run_npp.py")
from hass.tests.test_conversation import T0  # noqa: E402

FRONT, BACK = "chaos:jam.jpg", "npp:jam-back.jpg"
SHA = {FRONT: "f" * 64, BACK: "b" * 64}
WANT = {"listings": 1, "picture_source": FRONT, "label_words_from": [FRONT, BACK]}


def at(seconds):
    return (T0 + timedelta(seconds=seconds)).isoformat()


def version(n, delivered_s=None, photo=SHA[FRONT], job="j1"):
    return {"job_id": job, "n": n, "delivered_at": at(delivered_s) if delivered_s is not None else None,
            "listing_json": json.dumps({"photo": photo, "name": "Raspberry Jam"})}


def keys(*rows, key="raspberry-jam"):
    return {(v["job_id"], v["n"]): [key] for v in rows}


def check(versions, *, job_photos=None, reads=((5, [SHA[FRONT], SHA[BACK]]),), product_keys=None, want=WANT):
    job_photos = {"j1": SHA[FRONT]} if job_photos is None else job_photos
    return run_npp.photo_role_findings(want, list(versions), job_photos, list(reads), SHA.__getitem__,
                                       keys(*versions) if product_keys is None else product_keys)


class PhotoRoles(unittest.TestCase):
    def test_front_picture_and_both_labels_on_delivered_versions_pass(self):
        rows = [version(1, 30), version(2, 90)]
        self.assertEqual(check(rows), ([], set(WANT)))

    def test_back_photo_as_picture_fails_on_job_and_version(self):
        bad, covered = check([version(1, 30, photo=SHA[BACK])], job_photos={"j1": SHA[BACK]})
        self.assertIn("picture_source", covered)
        self.assertEqual(len([b for b in bad if b.startswith("picture_source")]), 2)

    def test_job_photo_is_read_from_each_delivered_versions_own_job(self):
        # A newer job with no delivered version neither fails the case nor masks the delivered job's photo.
        rows = [version(1, 30), version(1, None, photo=SHA[BACK], job="j2")]
        self.assertEqual(check(rows, job_photos={"j1": SHA[FRONT], "j2": SHA[BACK]})[0], [])
        bad, _ = check(rows, job_photos={"j1": SHA[BACK], "j2": SHA[FRONT]})
        self.assertEqual(bad, [f"picture_source: job j1 photo is not {FRONT}"])
        bad, _ = check([version(1, 30)], job_photos={})
        self.assertEqual(bad, [f"picture_source: job j1 photo is not {FRONT}"])

    def test_never_delivered_version_is_not_picture_evidence(self):
        # A wrong never-delivered draft cannot fail the case, and it cannot pass it either: with no delivered
        # version every key stays uncovered (a gap).
        self.assertEqual(check([version(1, None, photo=SHA[BACK])]), ([], set()))
        bad, covered = check([version(1, 30), version(2, None, photo=SHA[BACK])])
        self.assertEqual((bad, covered), ([], set(WANT)))

    def test_delivered_later_version_with_back_picture_fails(self):
        bad, _ = check([version(1, 30), version(2, 90, photo=SHA[BACK])])
        self.assertEqual(bad, [f"picture_source: v2 pictures another photo, not {FRONT}"])

    def test_front_only_or_swapped_reading_fails(self):
        for photos in ([SHA[FRONT]], [SHA[BACK], SHA[FRONT]], [SHA[FRONT], SHA[BACK], SHA[BACK]]):
            with self.subTest(photos=len(photos)):
                bad, covered = check([version(1, 30)], reads=[(5, photos)])
                self.assertIn("label_words_from", covered)
                self.assertTrue(any(b.startswith("label_words_from: a reading") for b in bad), bad)

    def test_any_later_reading_of_one_photo_fails(self):
        bad, _ = check([version(1, 30)], reads=[(5, [SHA[FRONT], SHA[BACK]]), (70, [SHA[FRONT]])])
        self.assertEqual(len(bad), 1)

    def test_reading_only_after_first_delivery_fails(self):
        bad, _ = check([version(1, 30), version(2, 90)], reads=[(60, [SHA[FRONT], SHA[BACK]])])
        self.assertEqual(bad, ["label_words_from: no reading before the first delivered card"])

    def test_no_reading_leaves_label_words_from_uncovered(self):
        bad, covered = check([version(1, 30)], reads=())
        self.assertEqual(bad, [])
        self.assertNotIn("label_words_from", covered)

    def test_two_listings_fail(self):
        rows = [version(1, 30), version(1, 35, job="j2")]
        product_keys = {("j1", 1): ["raspberry-jam"], ("j2", 1): ["raspberry-jam-2"]}
        bad, _ = check(rows, product_keys=product_keys, job_photos={"j1": SHA[FRONT], "j2": SHA[FRONT]})
        self.assertEqual(bad, ["listings: want 1, got 2"])

    def test_never_delivered_second_listing_does_not_count(self):
        rows = [version(1, 30), version(1, None, job="j2")]
        product_keys = {("j1", 1): ["raspberry-jam"], ("j2", 1): ["raspberry-jam-2"]}
        self.assertEqual(check(rows, product_keys=product_keys)[0], [])

    def test_delivered_version_without_product_record_fails(self):
        bad, _ = check([version(1, 30)], product_keys={})
        self.assertEqual(bad, ["listings: a delivered version has no product record", "listings: want 1, got 0"])

    def test_case17_fixture_declares_exactly_these_keys(self):
        case = run_npp.load_cases()[17]
        self.assertEqual({k: case["expect"][k] for k in WANT}, WANT)


if __name__ == "__main__":
    unittest.main()
