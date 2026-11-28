"""Contract tests for the offline source-backing drift check."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_claims_source_hit.py"
PASS = "PASS npp_claims_source_hit"
FAIL = "FAIL npp_claims_source_hit"
PINS = [
    "case 0 unbacked=no",
    "case 1 unbacked=yes",
    "case 2 unbacked=yes",
    "case 3 unbacked=yes",
    "case 4 unbacked=no",
    "case 5 unbacked=no",
    "case 6 unbacked=yes",
    "case 7 unbacked=yes",
    "case 8 unbacked=yes",
    "case 9 unbacked=no",
    "case 10 unbacked=no",
]
NEGATION_FINDINGS = [
    "FAIL unbacked-source 2",
    "FAIL source-changed 2",
    "FAIL unbacked-source 3",
    "FAIL source-changed 3",
]


def invoke(*args):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        cwd=ROOT, capture_output=True, text=True, timeout=10,
    )


def snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        tree = ROOT / name
        for path in (tree, *tree.rglob("*")):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class SourceHitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_claims_source_hit", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def assert_outcome(self, code, stdout, stderr, expected_code, trailer):
        self.assertEqual(code, expected_code, stderr)
        self.assertEqual(stderr, "")
        self.assertTrue(stdout.endswith(trailer + "\n"), stdout)
        lines = stdout.splitlines()
        self.assertEqual(lines[-1], trailer)
        return lines

    def run_main(self, expected_code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        return self.assert_outcome(code, stdout.getvalue(), stderr.getvalue(),
                                   expected_code, trailer)

    def run_cli(self):
        result = invoke()
        return self.assert_outcome(result.returncode, result.stdout, result.stderr, 0, PASS)

    def run_without_stop(self):
        with patch.object(self.tool.claims, "STOP", set()):
            return self.run_main(1, FAIL)

    def run_without_negation(self):
        with patch.object(self.tool.claims, "_affirmed", lambda rx, owner: bool(rx.search(owner))):
            return self.run_main(1, FAIL)

    def test_c1_full_pass(self):
        # An entry point that does not propagate the success trailer/status breaks the CLI.
        self.run_cli()

    def test_c2_findings_trailer(self):
        # A deferred or reordered finding, or a fail-fast mismatch exit, breaks this transcript.
        lines = self.run_without_negation()
        self.assertEqual(lines, [
            *PINS[:2],
            "case 2 unbacked=no", *NEGATION_FINDINGS[:2],
            "case 3 unbacked=no", *NEGATION_FINDINGS[2:],
            *PINS[4:], FAIL,
        ])

    def test_c2_1_unbacked_source(self):
        # Negated words must not count as backing in the required-hit cases.
        lines = self.run_without_negation()
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         NEGATION_FINDINGS)

    def test_c2_2_source_changed(self):
        # Looking only at MUST_HIT would miss a changed answer in case 10.
        lines = self.run_without_stop()
        self.assertEqual(lines[-3:], ["case 10 unbacked=yes", "FAIL source-changed 10", FAIL])

    def test_c2_3_check_error(self):
        # A repo error must not leak exception text or let the remaining checks run.
        source_hit = self.tool.claims._source_hit

        def fail_on_second(*case):
            if case == self.tool.CASES[1]:
                raise RuntimeError("synthetic exception detail")
            return source_hit(*case)

        with patch.object(self.tool.claims, "_source_hit", side_effect=fail_on_second) as check:
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, [PINS[0], "FAIL check-error", FAIL])
        self.assertEqual(check.call_args_list, [call(*case) for case in self.tool.CASES[:2]])

    def test_c3_usage_exit_2(self):
        # A zero-argument parser must refuse even its default help/terminator tokens.
        for arg in ("extra", "--unknown", "-h", "--help", "--"):
            with self.subTest(arg=arg):
                result = invoke(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No stdout last line on usage errors.
                self.assertTrue(result.stderr.startswith("usage: "), result.stderr)
                self.assertIn(": error: ", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # A report/cache write or touch in either tree would change the snapshot.
        before = snapshot()
        self.run_cli()
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug prints or stray separators must not pollute the line-oriented protocol.
        for lines in (self.run_cli(), self.run_without_negation(), self.run_without_stop()):
            for line in lines:
                self.assertRegex(line, r"^(?:case [0-9]+ unbacked=(?:yes|no)|"
                                 r"FAIL (?:unbacked-source|source-changed) [0-9]+|"
                                 r"FAIL check-error|(?:PASS|FAIL) npp_claims_source_hit)$")

    def test_c6_fixture(self):
        # If the tool bypasses the repo's stop-word filter, the mutation cannot flip case 10.
        lines = self.run_without_stop()
        self.assertEqual(lines, [*PINS[:10], "case 10 unbacked=yes", "FAIL source-changed 10", FAIL])

    def test_c7_live_pins(self):
        # A hard-coded replay can mimic the transcript but cannot exercise the repo predicate.
        source_hit = self.tool.claims._source_hit
        with patch.object(self.tool.claims, "_source_hit", wraps=source_hit) as check:
            lines = self.run_main(0, PASS)
        self.assertEqual(lines, [*PINS, PASS])
        self.assertEqual(check.call_args_list, [call(*case) for case in self.tool.CASES])
