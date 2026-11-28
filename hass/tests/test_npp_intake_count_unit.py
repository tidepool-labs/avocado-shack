"""Offline contract tests for the intake count, sold-by and unit drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import call, patch

from hass.skills import item_intake


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_intake_count_unit.py'
SPEC = importlib.util.spec_from_file_location('npp_intake_count_unit', SCRIPT)
assert SPEC is not None and SPEC.loader is not None
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)

PASS = 'PASS npp_intake_count_unit'
FAIL = 'FAIL npp_intake_count_unit'
LIVE = [
    'case 0 count=3',
    'case 1 count=0',
    'case 2 count=3',
    'case 3 count=None',
    'case 4 count=None',
    'case 5 count=None',
    "case 6 sold='pound'",
    "case 7 sold='bag'",
    "case 8 sold='item'",
    'case 9 sold=None',
    'case 10 sold=None',
    "case 11 unit='jar'",
    'case 12 unit=None',
    'case 13 unit=None',
    'case 14 unit=None',
]


def cli(*args):
    return subprocess.run(
        [sys.executable, '-B', str(SCRIPT), *args], cwd=ROOT,
        capture_output=True, text=True, timeout=10,
    )


def run_main():
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        status = TOOL.main([])
    return status, out.getvalue().splitlines(), err.getvalue()


def run_digit_erasure():
    clean = item_intake._clean

    def erase(text):
        return ''.join(char for char in clean(text) if not char.isnumeric())

    with patch.object(item_intake, '_clean', erase):
        return run_main()


def run_empty_filler():
    with patch.object(item_intake, 'SOLD_FILLER', frozenset()):
        return run_main()


def findings(lines):
    return [line for line in lines[:-1] if line.startswith('FAIL ')]


def tree_metadata():
    snapshot = {}
    for name in ('hass', 'storefront-mockup'):
        tree = ROOT / name
        for path in (tree, *tree.rglob('*')):
            stat = path.lstat()
            snapshot[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


class IntakeCountUnitTests(unittest.TestCase):
    def test_c1_full_pass(self):
        # The real CLI must propagate a successful check and end with PASS.
        result = cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # A fail-fast loop or a separate findings section loses case adjacency.
        status, lines, err = run_digit_erasure()
        self.assertEqual(status, 1)
        self.assertEqual(lines, [
            'case 0 count=None', 'FAIL answer-changed 0',
            'case 1 count=None', 'FAIL answer-changed 1',
            *LIVE[2:9],
            "case 9 sold='pound'", 'FAIL number-erased 9', 'FAIL answer-changed 9',
            *LIVE[10:12],
            "case 12 unit='jar'", 'FAIL number-erased 12', 'FAIL answer-changed 12',
            *LIVE[13:], FAIL,
        ])
        self.assertEqual(err, '')

    def test_c2_1_number_erased(self):
        # Merely comparing answers would miss the specific safety finding.
        status, lines, _ = run_digit_erasure()
        self.assertEqual(status, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(findings(lines), [
            'FAIL answer-changed 0', 'FAIL answer-changed 1',
            'FAIL number-erased 9', 'FAIL answer-changed 9',
            'FAIL number-erased 12', 'FAIL answer-changed 12',
        ])

    def test_c2_2_answer_changed(self):
        # The refusal-only rule cannot detect drift on accepted answers.
        status, lines, _ = run_empty_filler()
        self.assertEqual(status, 1)
        self.assertEqual(lines, [
            *LIVE[:6],
            'case 6 sold=None', 'FAIL answer-changed 6',
            'case 7 sold=None', 'FAIL answer-changed 7',
            'case 8 sold=None', 'FAIL answer-changed 8',
            *LIVE[9:], FAIL,
        ])

    def test_c2_3_check_error(self):
        # A parser error must stop the run without leaking its exception text.
        with (
            patch.object(item_intake, '_parse_sold_by', side_effect=RuntimeError('synthetic detail')) as sold,
            patch.object(item_intake, '_parse_unit', wraps=item_intake._parse_unit) as unit,
        ):
            status, lines, err = run_main()
            sold.assert_called_once_with('per pound')
            unit.assert_not_called()
        self.assertEqual(status, 1)
        self.assertEqual(lines, [*LIVE[:6], 'FAIL check-error', FAIL])
        self.assertEqual(err, '')

    def test_c3_usage_exit_2(self):
        # No argument, including a help flag or separator, is admitted.
        for arg in ('unexpected', '--unknown', '--help', '-h', '--'):
            with self.subTest(arg=arg):
                result = cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.startswith('usage: '))
                self.assertIn('error: unrecognized arguments:', result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # A cache, report or updated fixture would alter the tree metadata.
        before = tree_metadata()
        result = cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(tree_metadata(), before)

    def test_c5_output_shape(self):
        # Debug prints on either stream would pollute the report protocol.
        result = cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '\n'.join([*LIVE, PASS]) + '\n')
        self.assertEqual(result.stderr, '')
        for run in (run_digit_erasure, run_empty_filler):
            with self.subTest(fixture=run.__name__):
                status, lines, err = run()
                self.assertEqual(status, 1)
                self.assertEqual(lines[-1], FAIL)
                for line in lines[:-1]:
                    self.assertRegex(
                        line, r"^(case \d+ (count|sold|unit)=(None|\d+|'[a-z]+')|"
                        r"FAIL (number-erased|answer-changed) \d+)$",
                    )
                self.assertEqual(err, '')

    def test_c6_fixture(self):
        # Empty filler must affect all three accepted sold-by phrases only.
        status, lines, _ = run_empty_filler()
        self.assertEqual(status, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(findings(lines), [
            'FAIL answer-changed 6', 'FAIL answer-changed 7', 'FAIL answer-changed 8',
        ])

    def test_c7_live_pins(self):
        # Wrap the real parsers to catch canned output or wrong fixture routing.
        with (
            patch.object(item_intake, '_parse_count', wraps=item_intake._parse_count) as count,
            patch.object(item_intake, '_parse_sold_by', wraps=item_intake._parse_sold_by) as sold,
            patch.object(item_intake, '_parse_unit', wraps=item_intake._parse_unit) as unit,
        ):
            status, lines, err = run_main()
        self.assertEqual(count.call_args_list, [
            call('3'), call('0'), call('three jars'), call('a dozen'), call('about 4'), call('2000000'),
        ])
        self.assertEqual(sold.call_args_list, [
            call('per pound'), call('by the bag'), call('each'), call('per 2 pounds'), call('pound or bag'),
        ])
        self.assertEqual(unit.call_args_list, [call('jar'), call('jar2'), call('dozen'), call('jars of honey')])
        self.assertEqual(status, 0)
        self.assertEqual(lines, [*LIVE, PASS])
        self.assertEqual(err, '')


if __name__ == '__main__':
    unittest.main()
