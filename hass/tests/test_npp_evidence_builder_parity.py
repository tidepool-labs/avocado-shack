"""Exercise the offline receipt parity CLI against the real evidence module."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass.npp import evidence


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_evidence_builder_parity.py"
PASS = "PASS npp_evidence_builder_parity"
FAIL = "FAIL npp_evidence_builder_parity"


def snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class EvidenceBuilderParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_evidence_builder_parity", SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError("could not load the evidence parity CLI")
        cls.cli = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(cls.cli)

    def subprocess_run(self, *args):
        with TemporaryDirectory() as work:
            return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                                  cwd=work, capture_output=True, text=True, timeout=10)

    def run_main(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = self.cli.main([])
        self.assertEqual(err.getvalue(), "")
        return status, out.getvalue().splitlines()

    def assert_findings(self, result, *expected):
        status, lines = result
        self.assertEqual(status, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         list(expected))

    def test_c1_full_pass(self):
        # A broken standalone import or missing success trailer makes the normal CLI unusable.
        result = self.subprocess_run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # One builder-only regression can trigger both findings; neither should mask the other.
        record_stage = evidence.Evidence.stage

        def refuse_s13(self, stage, started_ms, ended_ms, outcome, code=None):
            if stage == "S13":
                raise ValueError("fixture refusal")
            return record_stage(self, stage, started_ms, ended_ms, outcome, code)

        with patch.object(evidence.Evidence, "stage", refuse_s13):
            self.assert_findings(self.run_main(), "FAIL parity 6", "FAIL verdict-changed 6")

    def test_c2_1_parity(self):
        # Validator-only tightening must be reported even when the builder's verdict is unchanged.
        validate = evidence.validate

        def reject_single_fallback(doc):
            problems = validate(doc)
            if doc["fallbacks"] == ["basic"] and doc["approval"] is None:
                return [*problems, "fallbacks: fixture refusal"]
            return problems

        with patch.object(evidence, "validate", reject_single_fallback):
            result = self.run_main()
        self.assert_findings(result, "FAIL parity 13")
        self.assertIn("case 13 builder=ok validate=problems", result[1])

    def test_c2_2_verdict_changed(self):
        # If both paths start accepting S14, comparing them alone gives a false pass.
        stage_rule = evidence._STAGE["stage"]
        with patch.dict(evidence._STAGE, stage=lambda value: stage_rule(value) or value == "S14"):
            result = self.run_main()
        self.assert_findings(result, "FAIL verdict-changed 7")
        self.assertIn("case 7 builder=ok validate=ok", result[1])

    def test_c2_3_doc_invalid(self):
        # Single-row checks cannot catch a validator regression on a populated receipt.
        validate = evidence.validate
        complete = {
            "evidence_version": 1,
            "stages": [dict(stage="S1", started_ms=0, ended_ms=5, outcome="ok", code=None)],
            "models": [dict(step="copy_select", pinned="m1", returned="m2", drift=True)],
            "checks": [dict(name="n", verdict="pass", private=None)],
            "fallbacks": ["basic"],
            "approval": dict(version=1, role="Mike", approved_at=0,
                             change_id="chg-1", draft_hash="abcdef1"),
            "publish": dict(change_id="chg-1", commit="abcdef1", live_verify="seen"),
        }

        def reject_complete(doc):
            problems = validate(doc)
            return [*problems, "fixture problem"] if doc == complete else problems

        with patch.object(evidence, "validate", reject_complete):
            self.assert_findings(self.run_main(), "FAIL doc-invalid")

    def test_c2_4_check_error(self):
        # An unexpected repo exception is neither a semantic refusal nor a silent skip.
        validate = evidence.validate

        def fail_on_s13(doc):
            if doc["stages"] and doc["stages"][0]["stage"] == "S13":
                raise RuntimeError("fixture exception")
            return validate(doc)

        with patch.object(evidence, "validate", fail_on_s13):
            result = self.run_main()
        self.assert_findings(result, "FAIL check-error")
        self.assertIn("case 13 builder=ok validate=ok", result[1])

    def test_c3_usage_exit_2(self):
        # Help, bare '--', and extra tokens must not be treated as a successful check.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.subprocess_run(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertIn("error: unrecognized arguments:", result.stderr)

    def test_c4_read_only(self):
        # A diagnostic must not create or refresh receipts, assets, or storefront files.
        before = snapshot()
        result = self.subprocess_run()
        self.assertEqual(snapshot(), before)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c5_output_shape(self):
        # Debug banners, warnings, or exception details would break line-oriented consumers.
        result = self.subprocess_run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], PASS)
        for index, line in enumerate(lines[:-1]):
            self.assertRegex(line, rf"^case {index} builder=(ok|refused) validate=(ok|problems)$")

    def test_c6_fixture(self):
        # Approval field problems must reach the parity comparison for every rejected time.
        validate = evidence.validate

        def omit_approval_problems(doc):
            return [problem for problem in validate(doc) if not problem.startswith("approval.")]

        with patch.object(evidence, "validate", omit_approval_problems):
            self.assert_findings(self.run_main(), "FAIL parity 2", "FAIL parity 3", "FAIL parity 5")

    def test_c7_live_pins(self):
        # Pin today's individual verdicts independently of the script's EXPECTED table.
        status, lines = self.run_main()
        self.assertEqual(status, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(lines[:-1], [
            f"case {index} " + ("builder=ok validate=ok" if index in (0, 1, 4, 6, 12, 13)
                                else "builder=refused validate=problems")
            for index in range(14)
        ])


if __name__ == "__main__":
    unittest.main()
