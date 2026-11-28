"""Offline contract tests for the NPP disguise-word drift guard."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import call, patch

from hass import live_policy


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_claim_disguise_words.py"
PASS = "PASS npp_claim_disguise_words"
FAIL = "FAIL npp_claim_disguise_words"
LIVE_LINES = [
    "case 0 spelled=yes superlative=no mixed=no",
    "case 1 spelled=yes superlative=no mixed=no",
    "case 2 spelled=no superlative=no mixed=no",
    "case 3 spelled=no superlative=yes mixed=no",
    "case 4 spelled=no superlative=no mixed=no",
    "case 5 spelled=no superlative=no mixed=no",
    "case 6 spelled=no superlative=yes mixed=no",
    "case 7 spelled=no superlative=no mixed=yes",
    "case 8 spelled=no superlative=no mixed=no",
    "case 9 spelled=no superlative=yes mixed=no",
]
DETECTORS = ("_spelled_number", "_superlative", "_mixed_script")


class NppClaimDisguiseWordsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("npp_claim_disguise_words", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.script = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(cls.script)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=ROOT,
                              capture_output=True, text=True, timeout=10)

    def main_lines(self, status, trailer):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.script.main([])
        self.assertEqual(code, status)
        self.assertEqual(err.getvalue(), "")
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def assert_cli_pass(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [PASS])
        return lines[:-1]

    def test_c1_full_pass(self):
        # A broken file entrypoint or successful run missing its receipt fails.
        self.assert_cli_pass(self.cli())

    def test_c2_findings_trailer(self):
        # A finding must not be deferred to the end or overwritten by later clean cases.
        with patch.object(live_policy, "_mixed_script", return_value=False):
            lines = self.main_lines(1, FAIL)
        self.assertEqual(lines, LIVE_LINES[:7] + [
            "case 7 spelled=no superlative=no mixed=no",
            "FAIL disguise-passed 7",
            "FAIL detector-changed 7",
        ] + LIVE_LINES[8:])

    def test_c2_1_disguise_passed(self):
        # Losing spelled-number detection must raise both findings, in case order.
        with patch.object(live_policy, "_spelled_number", return_value=False):
            lines = self.main_lines(1, FAIL)
        self.assertEqual(lines, [
            "case 0 spelled=no superlative=no mixed=no",
            "FAIL disguise-passed 0",
            "FAIL detector-changed 0",
            "case 1 spelled=no superlative=no mixed=no",
            "FAIL disguise-passed 1",
            "FAIL detector-changed 1",
        ] + LIVE_LINES[2:])

    def test_c2_2_detector_changed(self):
        # A new false positive on an exempt word is drift even if no disguise escapes.
        with patch.object(live_policy, "_NOT_SUPERLATIVE", frozenset()):
            lines = self.main_lines(1, FAIL)
        self.assertEqual(lines, LIVE_LINES[:5] + [
            "case 5 spelled=no superlative=yes mixed=no",
            "FAIL detector-changed 5",
        ] + LIVE_LINES[6:])

    def test_c2_3_check_error(self):
        # Every detector error must stop the run, without a partial case or a traceback.
        for name in DETECTORS:
            with self.subTest(detector=name), ExitStack() as stack:
                spies = {}
                for detector in DETECTORS:
                    real = getattr(live_policy, detector)
                    options = {"wraps": real}
                    if detector == name:
                        options["side_effect"] = [real(self.script.CASES[0]), RuntimeError("synthetic detail")]
                    spies[detector] = stack.enter_context(patch.object(live_policy, detector, **options))
                self.assertEqual(self.main_lines(1, FAIL), [LIVE_LINES[0], "FAIL check-error"])
                for i, detector in enumerate(DETECTORS):
                    checked = 2 if i <= DETECTORS.index(name) else 1
                    self.assertEqual(spies[detector].call_args_list,
                                     [call(text) for text in self.script.CASES[:checked]])

    def test_c3_usage_exit_2(self):
        # Ignore-unknown parsing or argparse's default help action would accept input.
        for arg in ("unexpected", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage:"), result.stderr)
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f"{SCRIPT.name}: error: unrecognized arguments: {arg}")

    def test_c4_read_only(self):
        # A bytecode cache, report, or touch to input files must change the snapshot.
        def snapshot():
            result = {}
            for name in ("hass", "storefront-mockup"):
                tree = ROOT / name
                for path in (tree, *tree.rglob("*")):
                    info = path.lstat()
                    result[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return result

        before = snapshot()
        self.assert_cli_pass(self.cli())
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug prints and malformed booleans are not part of the stdout protocol.
        lines = self.assert_cli_pass(self.cli())
        self.assertEqual(len(lines), 10)
        for i, line in enumerate(lines):
            self.assertRegex(line, rf"\Acase {i} spelled=(yes|no) superlative=(yes|no) mixed=(yes|no)\Z")

    def test_c6_fixture(self):
        # Clearing the exception set must yield just the measured case-5 finding.
        with patch.object(live_policy, "_NOT_SUPERLATIVE", frozenset()):
            lines = self.main_lines(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")],
                         ["FAIL detector-changed 5"])

    def test_c7_live_pins(self):
        # Static answers could match the pins yet hide future drift; wrap real calls.
        with ExitStack() as stack:
            spies = [stack.enter_context(patch.object(live_policy, name, wraps=getattr(live_policy, name)))
                     for name in DETECTORS]
            self.assertEqual(self.main_lines(0, PASS), LIVE_LINES)
        for spy in spies:
            self.assertEqual(spy.call_args_list, [call(text) for text in self.script.CASES])
