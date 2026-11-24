"""Contract: the catalog number screen refuses a catalog with no active product.

Protects: "no claim without something examined". Believable bug: an empty or
all-held products list (wrong --content folder, damaged file) prints zero counts
and `PASS catalog_number_screen`, which reads as a clean screen. Inputs are
synthetic disposable fixtures; the healthy control reads the real content copy.
"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/catalog_number_screen.py"
REFUSAL = "FAIL no-active-products\nFAIL catalog_number_screen\n"


def product(index, status):
    product_id = f"photo-product-{index:03}"
    record = {
        "id": product_id, "name": "Wildflower Honey", "brand": "Harbor Lane",
        "displayBrand": "Harbor Lane", "category": "pantry",
        "image": f"assets/products/{product_id}.webp", "description": "Fresh honey.",
        "status": status, "producerKey": "harbor-lane",
    }
    if status == "held":
        record["hold"] = {"reason": "Synthetic hold", "source": "https://example.com/hold"}
    return record


def run_screen(content):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), "--content", str(content)],
                          capture_output=True, text=True, timeout=30)


class NoActiveProductsTests(unittest.TestCase):
    def write_content(self, products):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        content = Path(temporary.name) / "synthetic-input"
        content.mkdir()
        documents = {
            "products": {"products": products},
            "makers": {"makers": {"harbor-lane": {
                "name": "Harbor Lane", "place": "Testville, California", "story": "Small orchard.",
            }}},
            "store": {
                "name": "Fixture Store", "streetAddress": "Example Lane", "town": "Testville",
                "hours": ["Monday-Friday 9am-5pm", "Closed Saturday-Sunday"],
            },
            "community": {"club": {
                "clubName": "Fixture Club", "organizer": "Example Lead",
                "intendedSender": "club@example.com", "emailConnected": False,
            }, "events": [], "routeIdeas": []},
        }
        for name, doc in documents.items():
            (content / f"{name}.json").write_text(
                json.dumps({"schemaVersion": 1, **doc}), encoding="utf-8")
        return content

    def assert_refused(self, result):
        self.assertEqual((result.returncode, result.stdout, result.stderr), (1, REFUSAL, ""))

    def test_empty_products_list_fails(self):
        self.assert_refused(run_screen(self.write_content([])))

    def test_only_held_products_fails(self):
        self.assert_refused(run_screen(self.write_content([product(1, "held"), product(2, "held")])))

    def test_one_active_product_is_still_examined(self):
        result = run_screen(self.write_content([product(1, "held"), product(2, "active")]))
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertEqual(result.stdout.splitlines()[:2], ["active 1", "screened 2"])
        self.assertEqual(result.stdout.splitlines()[-1], "PASS catalog_number_screen")

    def test_real_content_output_unchanged(self):
        # Healthy control: the real copy has active products, so the refusal never applies and
        # the report keeps its pre-change shape (counts first, FAIL/PASS trailer matching the code).
        result = run_screen(ROOT / "hass/content")
        lines = result.stdout.splitlines()
        self.assertEqual(result.stderr, "")
        self.assertNotIn("FAIL no-active-products", lines)
        self.assertRegex(lines[0], r"^active [1-9][0-9]*$")
        self.assertRegex(lines[1], r"^screened [1-9][0-9]*$")
        self.assertEqual(lines[-1], ("PASS" if result.returncode == 0 else "FAIL") + " catalog_number_screen")
        self.assertIn(result.returncode, (0, 1))


if __name__ == "__main__":
    unittest.main()
