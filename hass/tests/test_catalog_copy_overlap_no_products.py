"""A catalog copy-overlap run that examined no active product must not print a PASS."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/catalog_copy_overlap.py"
REAL = ["span-words 8", "descriptions 170", "pairs 139", "products 46", "largest 10"]
TRAILER = "FAIL catalog_copy_overlap"


class NoActiveProductsTests(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
                              capture_output=True, text=True, timeout=30)

    def refused(self, products):
        # Believable bug: zero counts and PASS although nothing was examined.
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            content = Path(tmp) / "content"
            shutil.copytree(ROOT / "hass/content", content)
            path = content / "products.json"
            document = json.loads(path.read_bytes())
            document["products"] = products(document["products"])
            path.write_text(json.dumps(document), encoding="utf-8")
            result = self.run_script("--content", content)
        self.assertEqual((result.returncode, result.stderr), (1, ""))
        self.assertEqual(result.stdout.splitlines(), ["FAIL no-active-products", TRAILER])

    def test_empty_products_list_fails(self):
        self.refused(lambda products: [])

    def test_only_held_products_fails(self):
        self.refused(lambda products: [dict(p, status="held") for p in products])

    def test_real_content_output_unchanged(self):
        # Healthy control: output and exit code recorded from the script before the change.
        result = self.run_script()
        self.assertEqual((result.returncode, result.stderr), (1, ""))
        self.assertEqual(result.stdout.splitlines(), [*REAL, "FAIL shared-pairs 139 0", TRAILER])

    def test_max_pairs_refuses_non_ascii_digits(self):
        # Believable bug: int() reads Arabic-Indic digits as a threshold.
        for value in ("\u0663", "\u0660"):
            with self.subTest(value=value):
                result = self.run_script("--max-pairs", value)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertTrue(result.stderr.endswith("error: invalid arguments\n"))

    def test_max_pairs_ascii_unchanged(self):
        for value in ("0", "3"):
            with self.subTest(value=value):
                result = self.run_script("--max-pairs", value)
                self.assertEqual((result.returncode, result.stderr), (1, ""))
                self.assertEqual(result.stdout.splitlines(),
                                 [*REAL, f"FAIL shared-pairs 139 {value}", TRAILER])
