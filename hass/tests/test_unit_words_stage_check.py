"""Behavioral contract for the offline price-unit comparison CLI."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/unit_words_stage_check.py"
PASS = "PASS unit_words_stage_check"
FAIL = "FAIL unit_words_stage_check"


def load_checker():
    spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    return checker


def assets_with_forms(*forms):
    return ({}, {"hass-listing-edit/edit-grammar.json": json.dumps({"forms": forms})})


def snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class UnitWordsStageCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checker = load_checker()

    def assert_report(self, status, stdout, stderr, expected_status, trailer):
        self.assertEqual(status, expected_status)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def run_main(self, expected_status, trailer):
        with redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
            status = self.checker.main([])
        return self.assert_report(status, stdout.getvalue(), stderr.getvalue(), expected_status, trailer)

    def run_cli(self, *args, cwd=ROOT):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
            capture_output=True, text=True, timeout=10,
        )

    def test_c1_full_pass(self):
        # Agreement includes unanimous rejection; unsupported words alone must not fail.
        price = {"id": "price", "pattern": r"make it \$4 (?P<unit>each)"}
        with (patch.object(self.checker.npp, "assets", return_value=assets_with_forms(price)),
              patch.object(self.checker, "PHRASES", ("each", "a piece")),
              patch.object(self.checker.edits, "UNITS", {"each": "each"})):
            self.assertEqual(self.run_main(0, PASS), [
                "unit each s3=each form=each map=each",
                "unit a-piece s3=none form=none map=none",
            ])

    def test_c2_findings_trailer(self):
        # A unitless match is still a reading; a disagreement must set the overall verdict.
        price = {"id": "price", "pattern": r"make it \$4 a piece"}
        with (patch.object(self.checker.npp, "assets", return_value=assets_with_forms(price)),
              patch.object(self.checker, "PHRASES", ("a piece",))):
            self.assertEqual(self.run_main(1, FAIL), [
                "unit a-piece s3=none form=unitless map=none",
                "FAIL unit-disagree a-piece",
            ])

    def test_c2_1_assets_unreadable(self):
        # Both the loader and JSON decoding can fail; neither should leak exception text.
        for label, mock_assets in (
            ("loader", patch.object(self.checker.npp, "assets", side_effect=OSError("synthetic marker"))),
            ("json", patch.object(self.checker.npp, "assets", return_value=(
                {}, {"hass-listing-edit/edit-grammar.json": b"not JSON"}
            ))),
        ):
            with self.subTest(label=label), mock_assets:
                self.assertEqual(self.run_main(1, FAIL), ["FAIL assets-unreadable"])

    def test_c2_2_price_form_missing(self):
        # A valid unrelated form does not qualify as the price form.
        supplier = {"id": "supplier", "pattern": r"make it \$4 (?P<unit>each)"}
        with patch.object(self.checker.npp, "assets", return_value=assets_with_forms(supplier)):
            self.assertEqual(self.run_main(1, FAIL), ["FAIL price-form-missing"])

    def test_c2_3_unit_disagree(self):
        # Table-only support disagrees even when S3 and the form both reject the text.
        price = {"id": "price", "pattern": r"make it \$4 (?P<unit>each)"}
        with (patch.object(self.checker.npp, "assets", return_value=assets_with_forms(price)),
              patch.object(self.checker, "PHRASES", ("ea", "a piece")),
              patch.object(self.checker.edits, "UNITS", {"ea": "each", "a piece": "each"})):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL unit-disagree ea", "FAIL unit-disagree a-piece",
        ])

    def test_c2_4_check_error(self):
        # An interrupted check must fail once without exposing the parser exception.
        with patch.object(self.checker.private_numbers, "finance", side_effect=ValueError("synthetic marker")):
            self.assertEqual(self.run_main(1, FAIL), ["FAIL check-error"])

    def test_c3_usage_exit_2(self):
        # Reject positionals, unknown flags and argparse's usual successful help option.
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            for arg in ("unexpected", "--unknown", "--help", "--"):
                with self.subTest(arg=arg):
                    result = self.run_cli(arg, cwd=Path(temporary))
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")  # No trailer on argparse errors.
                    self.assertIn("usage:", result.stderr)
                    self.assertIn("error:", result.stderr)

    def test_c4_read_only(self):
        # Run the real CLI and detect created files or edits anywhere in the two trees.
        before = snapshot()
        result = self.run_cli()
        self.assert_report(result.returncode, result.stdout, result.stderr, 1, FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Catch incidental parser logging, raw prices, or unrecognized finding lines.
        for phrases, status, trailer in ((None, 1, FAIL), (("each",), 0, PASS)):
            with self.subTest(trailer=trailer), patch.object(
                self.checker, "PHRASES", self.checker.PHRASES if phrases is None else phrases
            ):
                lines = self.run_main(status, trailer)
                for line in lines:
                    self.assertRegex(
                        line,
                        r"\A(?:unit [a-z-]+ s3=(?:each|lb|none) form=(?:each|lb|none|unitless)"
                        r" map=(?:each|lb|none)|FAIL (?:assets-unreadable|price-form-missing|"
                        r"check-error|unit-disagree [a-z-]+))\Z",
                    )

    def test_c6_fixture_pass(self):
        # The checker must run the selected three probes, not a cached/default report.
        with patch.object(self.checker, "PHRASES", ("each", "per lb", "lb")):
            self.assertEqual(self.run_main(0, PASS), [
                "unit each s3=each form=each map=each",
                "unit per-lb s3=lb form=lb map=lb",
                "unit lb s3=none form=none map=none",
            ])

    def test_c7_live_pins(self):
        # Pin the current asset/parser comparison, including slash joining and phrase order.
        lines = self.run_main(1, FAIL)
        units = [line for line in lines if line.startswith("unit ")]
        self.assertEqual([line.split()[1] for line in units], [
            "each", "apiece", "per-item", "per-lb", "a-lb", "per-pound", "a-pound",
            "slash-lb", "lb", "ea", "per-basket", "a-piece",
        ])
        self.assertIn("unit slash-lb s3=lb form=lb map=lb", units)
        self.assertIn("unit apiece s3=none form=none map=each", units)
        self.assertIn("unit per-item s3=each form=none map=none", units)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
            "FAIL unit-disagree apiece", "FAIL unit-disagree per-item",
        ])
