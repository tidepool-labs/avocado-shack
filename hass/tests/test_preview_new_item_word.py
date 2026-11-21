"""HASS-PREVIEW-2: a new item that is "in" previews and verifies (the add record does not expect "no availability word").

item.add drafts a product.add record and, for the "it's in" word, a later product record of the SAME change that sets
``available``. The add record carries no word of its own, so ``target_for`` expected "no word" while the page (generated
from the whole change) shows "Available today": ``availabilityShown`` failed in the proposal preview and again in the
result check, so every such draft said the preview check did not pass. The add record now expects nothing about the word;
the later record carries the expected word. Pure target tests always run; the browser test skips without PLAYWRIGHT_MODULE
(like test_preview). Run: python3 -B -m unittest hass.tests.test_preview_new_item_word -v
"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from hass import preview
from hass.content_model import REPO_ROOT, shop_today
from hass.skills import item_add as ia
from hass.skills import testkit
from hass.tests.test_editor import git
from hass.tests.test_skills_item_add import CONTENT, FULL

PHOTO = "reports/hass/newitem-1/synthetic/jar-white-sheet.jpg"


def products(records):
    return [r for r in records if r["collection"] == "products"]


class NewItemWordCase(unittest.TestCase):
    def setUp(self):
        self.scratch = testkit.Scratch({}, {"item.add": ia.ITEM_ADD}, photos=[PHOTO])
        self.addCleanup(self.scratch.close)
        self.scratch.now = datetime.now(timezone.utc)
        # Sample the browser's Pacific day with the draft clock, not at test discovery.
        self.today = shop_today(self.scratch.now)
        plan = ia.plan_add({**FULL, "maker": "Cal Poly", "place": None},
                           SimpleNamespace(today=self.today.isoformat(), next_product_id="photo-product-175", content=CONTENT,
                                           texts=["new honey", "skip"]))
        out = self.scratch.editor.prepare(plan)
        self.assertEqual(out["result"], "ok", out)
        self.draft = out["draft"]
        self.records = self.draft["records"]
        self.rendered = self.scratch.editor.render_draft(self.draft["change_id"])
        self.assertEqual(self.rendered["result"], "ok", self.rendered)

    def target(self, record):
        return preview.target_for(record, self.today, store=self.rendered["store"])


class TargetTests(NewItemWordCase):
    def test_the_draft_is_an_add_record_and_a_later_record_that_sets_the_word(self):
        added, later = products(self.records)[0], products(self.records)[-1]
        self.assertIsNone(added["before"])
        self.assertNotIn("available", added["after"])
        self.assertIsInstance(later["before"], dict)
        self.assertEqual(later["after"]["available"], "yes")

    def test_the_add_record_expects_nothing_about_the_word_and_the_later_record_expects_it(self):
        added, later = products(self.records)[0], products(self.records)[-1]
        self.assertNotIn("availability", self.target(added))
        self.assertEqual(self.target(later)["availability"], "Available today")
        self.assertEqual(self.target(preview.proposal_record(self.records))["kind"], "product")

    def test_an_existing_product_with_no_word_still_expects_no_word(self):
        record = {"collection": "products", "key": "p-1", "before": {"image": "a.webp"},
                  "after": {"id": "p-1", "name": "Avocados", "status": "active", "description": "Ripe.", "image": "a.webp"}}
        self.assertIn("availability", self.target(record))
        self.assertIsNone(self.target(record)["availability"])

    def test_an_add_record_that_does_carry_a_word_expects_it(self):
        record = {"collection": "products", "key": "p-1", "before": None,
                  "after": {"id": "p-1", "name": "Avocados", "status": "active", "description": "Ripe.",
                            "available": "no", "available_on": self.today.isoformat()}}
        self.assertEqual(preview.target_for(record, self.today, store={"selection_checked_on": self.today.isoformat()})["availability"], "Sold out")

    def test_a_record_without_a_before_key_keeps_todays_shape(self):
        record = {"collection": "products", "key": "p-1",
                  "after": {"id": "p-1", "name": "Avocados", "status": "active", "description": "Ripe."}}
        self.assertIn("availability", preview.target_for(record, self.today, store={"selection_checked_on": self.today.isoformat()}))


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class NewItemBrowser(NewItemWordCase):
    def setUp(self):
        super().setUp()
        wt = self.scratch.wt
        for rel in git(REPO_ROOT, "ls-files", "storefront-mockup").splitlines():
            if not rel.startswith("storefront-mockup/assets/") and not (wt / rel).exists():
                (wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, wt / rel)
        git(wt, "add", "-A")
        git(wt, "-c", "user.name=kit", "-c", "user.email=kit@example.invalid", "commit", "-q", "-m", "full site")
        self.out = Path(tempfile.mkdtemp(prefix="hass-preview2-"))
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)

    def test_the_proposal_picture_of_a_new_item_passes_its_checks_on_phone_and_desktop(self):
        record = preview.proposal_record(self.records)
        result = preview.Previewer(self.scratch.wt, os.environ).capture(
            self.rendered["files"], self.target(record), self.out / "proposal.png", assets=self.rendered["assets"])
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["error"], None)
        self.assertTrue(result["checks"]["productShown"] and result["checks"]["desktop:productShown"], result)

    def test_the_record_that_sets_the_word_is_checked_against_the_page_word(self):
        later = products(self.records)[-1]
        result = preview.Previewer(self.scratch.wt, os.environ).capture(
            self.rendered["files"], self.target(later), self.out / "word.png", assets=self.rendered["assets"])
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["checks"]["availabilityShown"] and result["checks"]["desktop:availabilityShown"], result)
        wrong = {**self.target(later), "availability": "Sold out"}
        self.assertFalse(preview.Previewer(self.scratch.wt, os.environ).capture(
            self.rendered["files"], wrong, self.out / "wrong.png", assets=self.rendered["assets"])["checks"]["availabilityShown"])


if __name__ == "__main__":
    unittest.main()
