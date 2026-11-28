"""Offline CLI contract tests for the NPP receipt value-fit diagnostic."""

import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_evidence_value_fit.py"
PASS = "PASS npp_evidence_value_fit"
FAIL = "FAIL npp_evidence_value_fit"
LIVE_COUNT = 15  # Literal occurrences, including repeated names.
FIXTURE = "problems.append('fixture-check')\n"


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class NppEvidenceValueFitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        # Loading the script inserts the checkout on sys.path; confine that change.
        with patch.object(sys, "path", sys.path[:]):
            spec = importlib.util.spec_from_file_location("npp_evidence_value_fit", SCRIPT)
            assert spec is not None and spec.loader is not None
            self.tool = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.tool)
        self.validate = self.root / "hass/npp/validate.py"
        self.validate.parent.mkdir(parents=True)
        self.validate.write_text(FIXTURE, encoding="utf-8")

    def invoke(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def run_fixture(self, *, bare_hash=True, root=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(self.tool, "ROOT", self.root if root is None else root))
            if bare_hash:
                draft_hash = self.tool.editor._draft_hash
                stack.enter_context(patch.object(self.tool.editor, "_draft_hash",
                                                 lambda draft: draft_hash(draft)[7:]))
            stack.enter_context(contextlib.redirect_stdout(stdout))
            stack.enter_context(contextlib.redirect_stderr(stderr))
            code = self.tool.main([])
        self.assertEqual(stderr.getvalue(), "")
        return code, stdout.getvalue().splitlines()

    def assert_outcome(self, code, lines, expected_code, trailer, *findings):
        self.assertEqual(code, expected_code)
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         list(findings))

    def test_c1_full_pass(self):
        # A clean source and accepted values must reach a successful trailer.
        code, lines = self.run_fixture()
        self.assert_outcome(code, lines, 0, PASS)
        self.assertIn("evidence check_names=1 refused=0", lines)

    def test_c2_findings_trailer(self):
        # Multiple failures must not short-circuit or produce multiple trailers.
        self.validate.write_text("warnings.append('BadName')\n", encoding="utf-8")
        code, lines = self.run_fixture(bare_hash=False)
        self.assert_outcome(code, lines, 1, FAIL, "FAIL draft-hash-refused",
                            "FAIL check-name-refused BadName")

    def test_c2_1_draft_hash_refused(self):
        # Checking only the stripped hash would miss the receipt mismatch.
        code, lines = self.run_fixture(bare_hash=False)
        self.assert_outcome(code, lines, 1, FAIL, "FAIL draft-hash-refused")
        self.assertEqual(lines[:2], ["evidence draft_hash=refused", "evidence draft_hash_hex=ok"])

    def test_c2_2_change_id_refused(self):
        # Change-ID refusal must be fatal even when the draft hash fits.
        with patch.dict(self.tool.evidence._APPROVAL, change_id=lambda value: False):
            code, lines = self.run_fixture()
        self.assert_outcome(code, lines, 1, FAIL, "FAIL change-id-refused")
        self.assertIn("evidence change_id=refused", lines)

    def test_c2_3_check_name_refused(self):
        # Breadth-first scanning misorders nested calls; unrelated expressions
        # and nonliteral arguments must not inflate the count.
        self.validate.write_text(
            "def listing():\n"
            "    if condition:\n"
            "        problems.append('ZProblem')\n"
            "    warnings.append('AWarning')\n"
            "    problems.append('ZProblem')\n"
            "    problems.append(variable)\n"
            "    other.append('Ignored')\n"
            "    Verdict(('Ignored', 'AlsoIgnored'), ())\n"
            "    return Verdict(('MVerdict',), ())\n",
            encoding="utf-8",
        )
        code, lines = self.run_fixture()
        self.assert_outcome(code, lines, 1, FAIL, "FAIL check-name-refused ZProblem",
                            "FAIL check-name-refused AWarning", "FAIL check-name-refused MVerdict")
        self.assertIn("evidence check_names=4 refused=4", lines)

    def test_c2_4_no_check_names(self):
        # An empty literal inventory must not pass by vacuous truth.
        self.validate.write_text("problems.append(variable)\n", encoding="utf-8")
        code, lines = self.run_fixture()
        self.assert_outcome(code, lines, 1, FAIL, "FAIL no-check-names")
        self.assertIn("evidence check_names=0 refused=0", lines)

    def test_c2_5_parse_error(self):
        # Missing input and bad syntax must be classified, not skipped or leaked.
        self.validate.write_text("invalid (", encoding="utf-8")
        for case, root in (("missing", self.root / "missing"), ("invalid", self.root)):
            with self.subTest(case=case):
                code, lines = self.run_fixture(root=root)
                self.assert_outcome(code, lines, 1, FAIL, "FAIL parse-error")

    def test_c2_6_check_error(self):
        # A rule raising on both hash probes yields one redacted finding.
        def broken_rule(value):
            raise RuntimeError("synthetic-private-marker")

        with patch.dict(self.tool.evidence._APPROVAL, draft_hash=broken_rule):
            code, lines = self.run_fixture()
        self.assert_outcome(code, lines, 1, FAIL, "FAIL check-error")
        self.assertNotIn("synthetic-private-marker", "\n".join(lines))
        self.assertIn("evidence check_names=1 refused=0", lines)

    def test_c3_usage_exit_2(self):
        # With no supported arguments, even argparse's usual help is not a pass.
        for arg in ("positional", "--unknown", "-h", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.invoke(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line.
                self.assertTrue(result.stderr.endswith("error: no arguments are accepted\n"))

    def test_c4_read_only(self):
        # Run the actual CLI; new files or rewritten files in either tree fail.
        before = snapshot()
        result = self.invoke()
        self.assert_outcome(result.returncode, result.stdout.splitlines(), 1, FAIL,
                            "FAIL draft-hash-refused")
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Even informational refusals cannot add output or fail a completed audit.
        draft_hash_rule = self.tool.evidence._APPROVAL["draft_hash"]
        with patch.dict(self.tool.evidence._APPROVAL,
                        draft_hash=lambda value: len(value) == 64 and draft_hash_rule(value)):
            with patch.dict(self.tool.evidence._PUBLISH, commit=lambda value: False):
                code, lines = self.run_fixture()
        self.assert_outcome(code, lines, 0, PASS)
        self.assertEqual(lines, ["evidence draft_hash=ok", "evidence draft_hash_hex=refused",
                                 "evidence change_id=ok", "evidence commit=refused",
                                 "evidence check_names=1 refused=0", PASS])

    def test_c6_fixture(self):
        # The real validator names still fit when only the producer prefix changes.
        code, lines = self.run_fixture(root=ROOT)
        self.assert_outcome(code, lines, 0, PASS)
        self.assertIn("evidence draft_hash=ok", lines)
        self.assertIn(f"evidence check_names={LIVE_COUNT} refused=0", lines)

    def test_c7_live_pins(self):
        # Exercise shipped inputs without a mock and pin the known incompatibility.
        result = self.invoke()
        lines = result.stdout.splitlines()
        self.assert_outcome(result.returncode, lines, 1, FAIL, "FAIL draft-hash-refused")
        self.assertEqual(result.stderr, "")
        self.assertEqual(lines, ["evidence draft_hash=refused", "evidence draft_hash_hex=ok",
                                 "evidence change_id=ok", "evidence commit=ok",
                                 f"evidence check_names={LIVE_COUNT} refused=0",
                                 "FAIL draft-hash-refused", FAIL])


if __name__ == "__main__":
    unittest.main()
