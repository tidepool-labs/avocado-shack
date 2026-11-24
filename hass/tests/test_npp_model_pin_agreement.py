"""Offline contracts for the NPP model pin agreement CLI."""

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

from hass import npp

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_model_pin_agreement.py"
RUBRIC = "hass-style-judge/rubric.json"
PASS = "PASS npp_model_pin_agreement"
FAIL = "FAIL npp_model_pin_agreement"

spec = importlib.util.spec_from_file_location("npp_model_pin_agreement", SCRIPT)
assert spec is not None and spec.loader is not None
agreement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agreement)


class NppModelPinAgreementTests(unittest.TestCase):
    def run_cli(self, *args):
        # Use a disposable cwd so subprocess coverage also checks root discovery.
        with tempfile.TemporaryDirectory() as cwd:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                capture_output=True, text=True, timeout=10,
            )

    def run_fixture(self, assets=None, error=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(npp, "assets", return_value=assets, side_effect=error):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = agreement.main([])
        return subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())

    def assert_report(self, result, code, trailer, findings=()):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], list(findings))
        return lines[:-1]

    def test_c1_full_pass(self):
        # The real command must propagate success and the exact PASS trailer.
        self.assert_report(self.run_cli(), 0, PASS)

    def test_c2_findings_trailer(self):
        # An early return on the first refusal could hide later judge drift.
        assets = npp.assets()
        assets[0]["steps"]["identify"]["model"] = None
        assets[0]["steps"]["judge"]["effort"] = "fixture-effort"
        self.assert_report(self.run_fixture(assets), 1, FAIL, (
            "FAIL step-unrecordable identify", "FAIL judge-drift effort",
        ))

    def test_c2_1_assets_unreadable(self):
        # A loader exception must not escape or echo its contents.
        result = self.run_fixture(error=ValueError("synthetic diagnostic"))
        self.assert_report(result, 1, FAIL, ("FAIL assets-unreadable",))
        self.assertEqual(result.stdout, f"FAIL assets-unreadable\n{FAIL}\n")

    def test_c2_2_step_unrecordable(self):
        # Insertion order differs from sorted order; validate keys as well as models.
        assets = npp.assets()
        steps = assets[0]["steps"]
        steps["research_verify"]["model"] = None
        steps["INVALID"] = steps["identify"].copy()
        lines = self.assert_report(self.run_fixture(assets), 1, FAIL, (
            "FAIL step-unrecordable research_verify", "FAIL step-unrecordable INVALID",
        ))
        self.assertEqual([line for line in lines if line.endswith("recordable=no")], [
            "step research_verify recordable=no", "step INVALID recordable=no",
        ])
        # Simulate the other documented refusal class at the real builder seam.
        with patch("hass.npp.evidence.Evidence.model", side_effect=TypeError):
            self.assert_report(self.run_fixture(assets), 1, FAIL, [
                f"FAIL step-unrecordable {name}" for name in steps
            ])

    def test_c2_3_judge_drift(self):
        # Each rubric field must be compared independently, with model reported first.
        for fields in (("model",), ("effort",), ("model", "effort")):
            with self.subTest(fields=fields):
                assets = npp.assets()
                rubric = json.loads(assets[1][RUBRIC])
                for field in fields:
                    rubric["judge"][field] = "fixture-different"
                assets[1][RUBRIC] = json.dumps(rubric).encode()
                self.assert_report(self.run_fixture(assets), 1, FAIL, [
                    f"FAIL judge-drift {field}" for field in fields
                ])

    def test_c2_4_judge_missing(self):
        # Missing configuration must not bypass the rubric check as a pass.
        assets = npp.assets()
        del assets[0]["steps"]["judge"]
        self.assert_report(self.run_fixture(assets), 1, FAIL, ("FAIL judge-missing",))

    def test_c3_usage_exit_2(self):
        # Accidental options, even argparse's default help flag, are usage errors.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No stdout trailer on usage errors.
                self.assertTrue(result.stderr.startswith("usage:"))
                self.assertIn("error: unrecognized arguments:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Detect generated files and in-place changes, including same-size rewrites.
        def snapshot():
            entries = {}
            for name in ("hass", "storefront-mockup"):
                tree = ROOT / name
                for path in (tree, *tree.rglob("*")):
                    stat = path.lstat()
                    entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
            return entries

        before = snapshot()
        self.assert_report(self.run_cli(), 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Findings must not leak a model value or emit other diagnostic text.
        assets = npp.assets()
        steps = assets[0]["steps"]
        steps["edit_map"]["model"] = "fixture@invalid"
        assets[1][RUBRIC] = b"not-json"
        lines = self.assert_report(self.run_fixture(assets), 1, FAIL, (
            "FAIL step-unrecordable edit_map", "FAIL assets-unreadable",
        ))
        expected = [f"step {name} recordable={'no' if name == 'edit_map' else 'yes'}"
                    for name in steps]
        expected.insert(expected.index("step edit_map recordable=no") + 1,
                        "FAIL step-unrecordable edit_map")
        self.assertEqual(lines, [*expected, "FAIL assets-unreadable"])

    def test_c6_fixture(self):
        # A provider-style plus sign may survive pin loading but not Evidence.model.
        assets = npp.assets()
        assets[0]["steps"]["edit_map"]["model"] = "gpt+6"
        lines = self.assert_report(self.run_fixture(assets), 1, FAIL, (
            "FAIL step-unrecordable edit_map",
        ))
        self.assertIn("step edit_map recordable=no", lines)

    def test_c7_live_pins(self):
        # The real asset order must survive; deriving the names from pins would hide drift.
        measured = ("identify", "research_extract", "research_verify", "copy_select",
                    "edit_map", "picture", "judge")
        lines = self.assert_report(self.run_cli(), 0, PASS)
        self.assertEqual(lines, [f"step {name} recordable=yes" for name in measured])
