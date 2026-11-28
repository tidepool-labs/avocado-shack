"""Fixture-only CLI contracts for the NPP planner-to-photo label check."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass.npp.job import Plan

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts' / 'hass' / 'npp_label_digit_reach.py'
PASS = 'PASS npp_label_digit_reach'
FAIL = 'FAIL npp_label_digit_reach'


def tree_snapshot():
    snapshot = {}
    for folder in ('hass', 'storefront-mockup'):
        tree = ROOT / folder
        for path in (tree, *tree.rglob('*')):
            info = path.lstat()
            snapshot[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return snapshot


class NppLabelDigitReachTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('npp_label_digit_reach', SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)

    def run_main(self):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        self.assertEqual(stderr.getvalue(), '')
        return code, stdout.getvalue().splitlines()

    def run_cli(self, *args):
        with TemporaryDirectory() as directory:
            return subprocess.run(
                [sys.executable, '-B', str(SCRIPT), *args], cwd=directory,
                capture_output=True, text=True, timeout=15, check=False,
            )

    def assert_trailer(self, code, lines, expected_code, trailer):
        self.assertEqual(code, expected_code)
        self.assertEqual(lines[-1:], [trailer])

    def test_c1_full_pass(self):
        # A legitimately dropped private word must not turn a clean check red.
        with patch.object(self.tool, 'WORDS', ('Raw', '2 pack')):
            code, lines = self.run_main()
        self.assert_trailer(code, lines, 0, PASS)
        self.assertIn('word 02 label-ok=no kept=no', lines)
        self.assertFalse(any(line.startswith('FAIL ') for line in lines))

    def test_c2_findings_trailer(self):
        # One failed word is enough to make the CLI status and final line fail.
        with patch.object(self.tool, 'WORDS', ('12 oz',)):
            code, lines = self.run_main()
        self.assert_trailer(code, lines, 1, FAIL)
        self.assertEqual(lines, ['word 01 label-ok=yes kept=no', 'FAIL label-word-dropped 01', FAIL])

    def test_c2_1_label_word_dropped(self):
        # Findings must use fixture positions, not sorted text or a dense count.
        with patch.object(self.tool, 'WORDS', ('Since 1990', '2 pack', '12 oz')):
            code, lines = self.run_main()
        self.assert_trailer(code, lines, 1, FAIL)
        self.assertEqual(lines, [
            'word 01 label-ok=yes kept=no', 'word 02 label-ok=no kept=no',
            'word 03 label-ok=yes kept=no', 'FAIL label-word-dropped 01',
            'FAIL label-word-dropped 03', FAIL,
        ])

    def test_c2_2_no_listing(self):
        # A question-only plan must not pass or be presented as seven lost words.
        with patch.object(self.tool.stages.ProductionStages, 'start_plan', return_value=Plan()):
            code, lines = self.run_main()
        self.assert_trailer(code, lines, 1, FAIL)
        self.assertEqual(lines, ['FAIL no-listing', FAIL])

    def test_c2_3_check_error(self):
        # Planner errors are distinct from empty plans; never echo their text.
        with patch.object(self.tool.missing.MissingInfo, 'decide', side_effect=RuntimeError('fixture detail')):
            code, lines = self.run_main()
        self.assert_trailer(code, lines, 1, FAIL)
        self.assertEqual(lines, ['FAIL check-error', FAIL])

    def test_c3_usage_exit_2(self):
        # Unknown flags (including conventional help flags) and bare args are errors.
        for arg in ('extra', '--unknown', '-h', '--help', '--'):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')  # No trailer on a usage error.
                self.assertEqual(result.stderr.splitlines()[-1:], [
                    f'npp_label_digit_reach.py: error: unrecognized arguments: {arg}',
                ])

    def test_c4_read_only(self):
        # Accidentally wiring a writer must not modify either source tree.
        before = tree_snapshot()
        result = self.run_cli()
        self.assert_trailer(result.returncode, result.stdout.splitlines(), 1, FAIL)
        self.assertEqual(tree_snapshot(), before)

    def test_c5_output_shape(self):
        # Reject incidental log lines, warnings and raw label words in the CLI.
        result = self.run_cli()
        lines = result.stdout.splitlines()
        self.assert_trailer(result.returncode, lines, 1, FAIL)
        self.assertEqual(result.stderr, '')
        for line in lines[:-1]:
            self.assertRegex(line, r'\A(?:word \d{2} label-ok=(?:yes|no) kept=(?:yes|no)|'
                                   r'FAIL (?:label-word-dropped \d{2}|no-listing|check-error))\Z')

    def test_c6_fixture(self):
        # A patched WORDS fixture must reach the reader, not just the formatter.
        with patch.object(self.tool, 'WORDS', ('Wildflower', 'Honey')):
            code, lines = self.run_main()
        self.assert_trailer(code, lines, 0, PASS)
        self.assertEqual(lines, ['word 01 label-ok=yes kept=yes', 'word 02 label-ok=yes kept=yes', PASS])

    def test_c7_live_pins(self):
        # Exercise the actual catalog, assets and planner with no decision mocks.
        code, lines = self.run_main()
        self.assert_trailer(code, lines, 1, FAIL)
        self.assertEqual(lines, [
            'word 01 label-ok=yes kept=yes', 'word 02 label-ok=yes kept=yes',
            'word 03 label-ok=yes kept=no', 'word 04 label-ok=yes kept=no',
            'word 05 label-ok=yes kept=no', 'word 06 label-ok=yes kept=yes',
            'word 07 label-ok=no kept=no',
            'FAIL label-word-dropped 03', 'FAIL label-word-dropped 04',
            'FAIL label-word-dropped 05', FAIL,
        ])
