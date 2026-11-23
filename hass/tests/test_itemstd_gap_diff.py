"""Exercise the offline gap diff CLI against saved, synthetic catalogs."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/itemstd_gap_diff.py"
PRODUCT_NAME = "Canary Orchard Biscuit"
MAKER_NAME = "Canary Lantern Bakery"
MAKER_PLACE = "Canary Grove, Testland"
MAKERS = {"fixture-maker": {"name": MAKER_NAME, "place": MAKER_PLACE, "story": "Fixture story."}}
PASS = "PASS itemstd_gap_diff"
FAIL = "FAIL itemstd_gap_diff"


def product(product_id="fixture-item", **fields):
    return {"id": product_id, "status": "active", "name": PRODUCT_NAME,
            "category": "pantry", "producerKey": "fixture-maker",
            "description": "Fixture description.", **fields}


def snapshot(root):
    return {path.relative_to(root): (path.stat().st_mtime_ns, None if path.is_dir() else path.read_bytes())
            for path in (root, *root.rglob("*"))}


class ItemstdGapDiffTests(unittest.TestCase):
    def setUp(self):
        before = tempfile.TemporaryDirectory(prefix="canary-before-")
        self.addCleanup(before.cleanup)
        after = tempfile.TemporaryDirectory(prefix="canary-after-")
        self.addCleanup(after.cleanup)
        self.before, self.after = Path(before.name).resolve(), Path(after.name).resolve()
        self.write_copy(self.before, [product()])
        self.write_copy(self.after, [product()])

    @staticmethod
    def write_copy(root, products, makers=MAKERS):
        for kind, rows in (("products", products), ("makers", makers)):
            (root / f"{kind}.json").write_text(
                json.dumps({"schemaVersion": 1, kind: rows}), encoding="utf-8",
            )

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)],
                              cwd=self.before, capture_output=True, text=True, timeout=10)

    def compare(self):
        return self.run_cli("--before", self.before, "--after", self.after)

    def assert_report(self, result, status, *lines):
        self.assertEqual(result.returncode, status)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, "\n".join((*lines, PASS if status == 0 else FAIL)) + "\n")

    def test_c1_full_pass(self):
        # A new, complete item with no own photo or maker website still passes.
        self.write_copy(self.after, [product(), product("fixture-new")])
        self.assert_report(self.compare(), 0, "active before 1 after 2", "gaps before 0 after 0")

    def test_c2_1_unsafe_input(self):
        # A directory test alone accepts a symlink to otherwise valid content.
        alias = self.before / "alias"
        alias.symlink_to(self.after, target_is_directory=True)
        for bad in (alias, self.before / "makers.json", self.before / "absent"):
            for before, after in ((bad, self.after), (self.before, bad)):
                with self.subTest(kind=bad.name, side="before" if before == bad else "after"):
                    self.assert_report(self.run_cli("--before", before, "--after", after),
                                       1, "FAIL unsafe-input")

    def test_c2_2_content_invalid(self):
        # Neither malformed JSON nor a decoded non-text ID should escape the report error boundary.
        for root in (self.before, self.after):
            for raw in ('{"schemaVersion":', '{"schemaVersion": 1, "products": [{"id": 42}]}'):
                with self.subTest(side="before" if root == self.before else "after", raw=raw):
                    (root / "products.json").write_text(raw, encoding="utf-8")
                    self.assert_report(self.compare(), 1, "FAIL content-invalid")
            self.write_copy(root, [product()])

    def test_c2_3_gap_added(self):
        # Compare pairs, not summary deltas; formerly hidden rows have no active baseline.
        self.write_copy(self.before, [product("fixture-a", status="hidden", producerKey=None),
                                     product("fixture-removed", producerKey=None)])
        self.write_copy(self.after, [product("fixture-z", name="", category=None, producerKey=None),
                                    product("fixture-a", producerKey=None),
                                    product("fixture-held", status="held", producerKey=None)])
        self.assert_report(self.compare(), 1, "active before 1 after 2", "gaps before 1 after 2",
                           "gap fixture-a producer", "gap fixture-a producer_town",
                           "gap fixture-z name", "gap fixture-z shelf", "gap fixture-z producer",
                           "gap fixture-z producer_town", "FAIL gap-added 6")

    def test_c3_usage_exit_2(self):
        # Do not treat parser failures as content findings or echo unrecognized arguments.
        both = ("--before", self.before, "--after", self.after)
        for args in (both[:2], (*both, "--unknown", self.after), (*both[:2], "--after")):
            with self.subTest(argument_count=len(args)):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # There is no last stdout line for usage errors.
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertNotIn(str(self.before), result.stderr)
                self.assertNotIn(str(self.after), result.stderr)

    def test_c4_read_only(self):
        # An accidental save or report sidecar would change this recursive snapshot.
        before, after = snapshot(self.before), snapshot(self.after)
        self.assert_report(self.compare(), 0, "active before 1 after 1", "gaps before 0 after 0")
        self.assertEqual((snapshot(self.before), snapshot(self.after)), (before, after))

    def test_c5_no_private_values(self):
        # A raw row, maker question, source path, or ReportError would expose fixture canaries.
        self.write_copy(self.after, [product()], {"fixture-maker": {"name": MAKER_NAME}})
        finding = self.compare()
        self.write_copy(self.after, [product()], {MAKER_NAME: None})
        error = self.compare()
        for result in (finding, error):
            for canary in (PRODUCT_NAME, MAKER_NAME, MAKER_PLACE, str(self.before), str(self.after)):
                self.assertNotIn(canary, result.stdout + result.stderr)
        self.assert_report(finding, 1, "active before 1 after 1", "gaps before 0 after 1",
                           "gap fixture-item producer_town", "FAIL gap-added 1")
        self.assert_report(error, 1, "FAIL content-invalid")

    def test_c6_producer_lost(self):
        # Regressions on an existing active listing count, not just newly added listings.
        changed = product()
        del changed["producerKey"]
        self.write_copy(self.after, [changed])
        self.assert_report(self.compare(), 1, "active before 1 after 1", "gaps before 0 after 1",
                           "gap fixture-item producer", "gap fixture-item producer_town", "FAIL gap-added 2")

    def test_c7_same_gap_ok(self):
        # Reporting the entire AFTER gap list instead of the difference would fail this run.
        for root in (self.before, self.after):
            self.write_copy(root, [product(producerKey=None)])
        self.assert_report(self.compare(), 0, "active before 1 after 1", "gaps before 1 after 1")

    def test_c8_invalid_id_not_printed(self):
        # ID redaction is informational, independent of whether the row adds a gap.
        for key in ("fixture-maker", None):
            with self.subTest(has_producer=key is not None):
                self.write_copy(self.after, [product(), product(PRODUCT_NAME, producerKey=key)])
                result = self.compare()
                self.assertNotIn(PRODUCT_NAME, result.stdout + result.stderr)
                if key is None:
                    self.assert_report(result, 1, "active before 1 after 2", "gaps before 0 after 1",
                                       "note invalid-id 1", "FAIL gap-added 2")
                else:
                    self.assert_report(result, 0, "active before 1 after 2", "gaps before 0 after 0",
                                       "note invalid-id 1")


if __name__ == "__main__":
    unittest.main()
