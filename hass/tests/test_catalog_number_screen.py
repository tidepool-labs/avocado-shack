"""Offline CLI contract tests; every content input is a disposable fixture."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/catalog_number_screen.py"
SPEC = importlib.util.spec_from_file_location("catalog_number_screen", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
screen = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(screen)


def product(index=1, **overrides):
    product_id = f"photo-product-{index:03}"
    return {
        "id": product_id, "name": "Wildflower Honey", "brand": "Harbor Lane",
        "displayBrand": "Harbor Lane", "category": "pantry",
        "image": f"assets/products/{product_id}.webp", "description": "Fresh honey.",
        "status": "active", "producerKey": "harbor-lane", **overrides,
    }


class CatalogNumberScreenTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.content = self.root / "synthetic-input"
        self.content.mkdir()

    def write_content(self, *products):
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
            (self.content / f"{name}.json").write_text(
                json.dumps({"schemaVersion": 1, **doc}), encoding="utf-8",
            )

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def run_screen(self, path=None):
        return self.cli("--content", str(self.content if path is None else path))

    def patched_screen(self, *products):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(screen, "load_and_validate", return_value=SimpleNamespace(products=products)), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = screen.main(["--content", str(self.content)])
        return subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())

    def assert_report(self, result, code):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines, "missing report")
        self.assertEqual(lines[-1], ("PASS" if code == 0 else "FAIL") + " catalog_number_screen")
        return lines

    def assert_early_failure(self, result, reason):
        self.assertEqual(self.assert_report(result, 1), [f"FAIL {reason}", "FAIL catalog_number_screen"])

    def test_c1_full_pass(self):
        # Screening hidden copy would incorrectly turn this successful run into a finding.
        self.write_content(product(), product(2, status="hidden", description="12 oz jar"))
        lines = self.assert_report(self.run_screen(), 0)
        self.assertEqual(lines[:2], ["active 1", "screened 2"])
        self.assertFalse(any(line.startswith("FAIL ") for line in lines))

    def test_c2_findings_trailer(self):
        # A finding must not leave a successful process status or a PASS trailer.
        self.write_content(product(description="12 oz jar"))
        result = self.run_screen()
        self.assertEqual([line for line in self.assert_report(result, 1) if line.startswith("FAIL ")],
                         ["FAIL flagged 1", "FAIL catalog_number_screen"])

    def test_c2_1_unsafe_input(self):
        # Use valid content behind the link so following it cannot pass unnoticed.
        self.write_content(product())
        link = self.root / "linked-input"
        link.symlink_to(self.content, target_is_directory=True)
        for path in (link, self.content / "products.json", self.root / "absent"):
            with self.subTest(kind=path.name):
                self.assert_early_failure(self.run_screen(path), "unsafe-input")

    def test_c2_2_content_invalid(self):
        # Valid JSON with the wrong schema must be rejected, as must bad encoding or JSON.
        self.write_content(product())
        for payload in (b'{"schemaVersion": 2, "products": []}', b"\xff", b"{"):
            with self.subTest(payload=payload):
                (self.content / "products.json").write_bytes(payload)
                self.assert_early_failure(self.run_screen(), "content-invalid")

    def test_c2_3_flagged(self):
        # One product with both fields flagged must count as two texts, not one row.
        self.write_content(product(name="12 oz Honey", description="about three dozen"))
        lines = self.assert_report(self.run_screen(), 1)
        self.assertEqual([line for line in lines if line.startswith("note flagged ")], [
            "note flagged name photo-product-001", "note flagged description photo-product-001",
        ])
        self.assertEqual(lines[-2], "FAIL flagged 2")
        self.assertEqual(lines.count("FAIL flagged 2"), 1)

    def test_c3_usage_exit_2(self):
        # Missing input, unknown flags and a missing option value are usage errors, not findings.
        for args in ((), ("--content", str(self.content), "--unknown"), ("--content",)):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # Catch rewrites (even to identical bytes) and creation of reports/sidecars.
        self.write_content(product(description="12 oz jar"))

        def snapshot():
            return {path.relative_to(self.content): (path.stat().st_mtime_ns,
                                                     path.read_bytes() if path.is_file() else None)
                    for path in (self.content, *self.content.rglob("*"))}

        before = snapshot()
        self.assert_report(self.run_screen(), 1)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Exercise redaction on reports, validation failure, and argparse's argv diagnostics.
        number = "81473"
        description = f"Hushed Marigold Marker {number} oz jar."
        name = "Velvet Honeysuckle Canary"
        self.write_content(product(name=name, description=description))
        flagged = self.run_screen()
        self.assertEqual(self.assert_report(flagged, 1)[-2], "FAIL flagged 1")
        self.write_content(product(name=name, description=description, id="Unsafe " + name))
        invalid = self.run_screen()
        self.assert_early_failure(invalid, "content-invalid")
        usage = self.cli("--content", str(self.content), str(self.content))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (flagged, invalid, usage):
            for canary in (description, number, name, str(self.content)):
                self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_clean(self):
        # An empty report or a skipped field does not prove the copy was screened.
        self.write_content(product())
        lines = self.assert_report(self.run_screen(), 0)
        self.assertCountEqual(lines[:-1], ["active 1", "screened 2", "count name clean 1",
                                           "count description clean 1"])

    def test_c7_reasons(self):
        # Counting all non-None values under a generic bucket would lose the reason split.
        self.write_content(product(description="12 oz jar"), product(2, description="about three dozen"),
                           product(3))
        lines = self.assert_report(self.run_screen(), 1)
        self.assertEqual(lines[:2], ["active 3", "screened 6"])
        self.assertCountEqual([line for line in lines if line.startswith("count ")], [
            "count name clean 3", "count description unsupported-number 1",
            "count description number-unclear 1", "count description clean 1",
        ])
        self.assertEqual(lines[-2], "FAIL flagged 2")

    def test_c8_invalid_id_canary(self):
        # The report must itself check the whole ID, not rely on prior validation or prefix matching.
        self.write_content(product())
        for canary in ("valid-prefix\n", "ID CANARY", 81473):
            with self.subTest(canary=canary):
                result = self.patched_screen(product(id=canary, description="12 oz jar"))
                lines = self.assert_report(result, 1)
                self.assertEqual(lines.count("note invalid-id 1"), 1)
                self.assertFalse(any(line.startswith("note flagged ") for line in lines))
                self.assertNotIn(str(canary).strip(), result.stdout + result.stderr)
                self.assertEqual(lines[-2], "FAIL flagged 1")

    def test_money_reason_beyond_validator(self):
        # The JSON copy validator refuses '$'; prove the screen still maps the real detector's code.
        self.write_content(product())
        lines = self.assert_report(self.patched_screen(product(description="Sold for $5")), 1)
        self.assertIn("count description money 1", lines)
        self.assertEqual(lines[-2], "FAIL flagged 1")

    def test_unsafe_reason_is_not_printed_but_still_counts(self):
        # A future detector bug must not make a raw value printable or turn a finding into clean.
        self.write_content(product())
        canary = "bad-code\nReason Canary"
        with patch.object(screen, "problem", side_effect=[None, canary]):
            result = self.patched_screen(product())
        lines = self.assert_report(result, 1)
        self.assertFalse(any(line.startswith("count description ") for line in lines))
        self.assertNotIn("bad-code", result.stdout + result.stderr)
        self.assertNotIn("Reason Canary", result.stdout + result.stderr)
        self.assertIn("note flagged description photo-product-001", lines)
        self.assertEqual(lines[-2], "FAIL flagged 1")


if __name__ == "__main__":
    unittest.main()
