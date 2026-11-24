"""Offline behaviour tests for the NPP category agreement CLI."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass import content_model, npp
from hass.npp import edits


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_category_enum_agreement.py"
PASS = "PASS npp_category_enum_agreement"
FAIL = "FAIL npp_category_enum_agreement"


class NppCategoryEnumAgreementTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=15,
        )

    def run_main(self):
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "path", sys.path.copy()), redirect_stdout(stdout), redirect_stderr(stderr):
            spec.loader.exec_module(module)
            code = module.main([])
        return subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())

    def fixture_assets(self, identify, card):
        files = {}
        for name, field, enum in (
            ("hass-product-identify/identify.schema.json", "category_guess", identify),
            ("hass-gallery-style/card.schema.json", "category", card),
        ):
            schema = self.root / name
            schema.parent.mkdir(exist_ok=True)
            schema.write_text(json.dumps({"properties": {field: {"enum": enum}}}), encoding="utf-8")
            files[name] = schema.read_bytes()
        return patch.object(npp, "assets", return_value=({}, files, {}))

    def assert_result(self, result, code, trailer):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def assert_findings(self, result, *expected):
        lines = self.assert_result(result, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], list(expected))

    def test_c1_full_pass(self):
        # Reordered shelves and the identify null do not cause drift.
        with patch.object(content_model, "CATEGORIES", ["fruit", "bread"]), \
             self.fixture_assets(["bread", None, "fruit"], ["fruit", "bread"]), \
             patch.object(edits, "CATEGORIES", ["bread", "fruit"]):
            self.assert_result(self.run_main(), 0, PASS)

    def test_c2_findings_trailer(self):
        # Several findings still require a single final failure verdict.
        with patch.object(content_model, "CATEGORIES", ["fruit"]), \
             self.fixture_assets(["fruit"], ["bread"]), \
             patch.object(edits, "CATEGORIES", ["fruit"]):
            self.assert_findings(self.run_main(), "FAIL identify-null-missing", "FAIL category-drift card")

    def test_c2_1_assets_unreadable(self):
        # An unreadable pin must fail without printing exception details.
        with patch.object(npp, "assets", side_effect=ValueError("synthetic asset detail")), \
             patch.object(content_model, "CATEGORIES", ["fruit"]), \
             patch.object(edits, "CATEGORIES", ["fruit"]):
            lines = self.assert_result(self.run_main(), 1, FAIL)
        self.assertEqual(lines, ["categories content count=1", "categories edits count=1", "FAIL assets-unreadable"])

    def test_c2_2_identify_null_missing(self):
        # Matching shelf sets cannot compensate for losing the abstention value.
        with patch.object(content_model, "CATEGORIES", ["fruit"]), \
             self.fixture_assets(["fruit"], ["fruit"]), \
             patch.object(edits, "CATEGORIES", ["fruit"]):
            self.assert_findings(self.run_main(), "FAIL identify-null-missing")

    def test_c2_3_category_drift(self):
        # Equal sets can hide repeats; equal counts can hide replaced shelves.
        for identify, card, edit_values in (
            (["fruit", "fruit", None], ["bread"], ["fruit", "fruit"]),
            (["bread", None], ["fruit", "fruit"], ["bread"]),
        ):
            with self.subTest(identify=identify, card=card, edits=edit_values), \
                 patch.object(content_model, "CATEGORIES", ["fruit"]), \
                 self.fixture_assets(identify, card), \
                 patch.object(edits, "CATEGORIES", edit_values):
                self.assert_findings(
                    self.run_main(), "FAIL category-drift identify",
                    "FAIL category-drift card", "FAIL category-drift edits",
                )

    def test_c3_usage_exit_2(self):
        # No argument is admitted, including argparse's default help flag.
        for argument in ("fruit", "--unknown", "--help", "-h", "--"):
            with self.subTest(argument=argument):
                result = self.run_cli(argument)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"npp_category_enum_agreement: error: unrecognized arguments: {argument}")

    def test_c4_read_only(self):
        # Catch writes to source/asset trees as well as relative output files.
        def snapshot():
            entries = {}
            for tree in (ROOT / "hass", ROOT / "storefront-mockup", self.root):
                for path in (tree, *tree.rglob("*")):
                    stat = path.lstat()
                    entries[path] = (stat.st_size, stat.st_mtime_ns)
            return entries

        before = snapshot()
        self.assert_result(self.run_cli(), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Findings and counts are the only allowed lines, even on a failing run.
        with patch.object(content_model, "CATEGORIES", ["fruit"]), \
             self.fixture_assets(["bread"], ["fruit", "fruit"]), \
             patch.object(edits, "CATEGORIES", []):
            lines = self.assert_result(self.run_main(), 1, FAIL)
        self.assertEqual(lines, [
            "categories content count=1", "categories identify count=1",
            "categories card count=2", "categories edits count=0",
            "FAIL identify-null-missing", "FAIL category-drift identify",
            "FAIL category-drift card", "FAIL category-drift edits",
        ])

    def test_c6_fixture(self):
        # Compare the edit binding independently, not a second copy of content.
        with patch.object(edits, "CATEGORIES", list(content_model.CATEGORIES) + ["seafood"]):
            self.assert_findings(self.run_main(), "FAIL category-drift edits")

    def test_c7_live_pins(self):
        # The committed assets, not the synthetic enums, must agree today.
        lines = self.assert_result(self.run_cli(), 0, PASS)
        self.assertEqual(lines, [
            "categories content count=10", "categories identify count=10",
            "categories card count=10", "categories edits count=10",
        ])
