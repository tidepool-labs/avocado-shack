"""Offline behavioral tests for the intake selling-price drift check."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_intake_money_words.py'
PASS = 'PASS npp_intake_money_words'
FAIL = 'FAIL npp_intake_money_words'
# Independent fixture oracles, measured on origin/main.
PINS = [
    "case 0 money='9.57' shown='$9.57'",
    "case 1 money='9.50' shown='$9.50'",
    "case 2 money='9.00' shown='$9.00'",
    "case 3 money='9.57' shown='$9.57'",
    "case 4 money='9.00' shown='$9.00'",
    "case 5 money='0.57' shown='$0.57'",
    "case 6 money=None shown=''",
    "case 7 money=None shown=''",
    "case 8 money=None shown=''",
    "case 9 money=None shown=''",
    "case 10 money='4.00' shown='$4.00'",
    "case 11 money='4.00' shown='$4.00'",
    "case 12 money=None shown=''",
]


def cli(*args):
    return subprocess.run(
        [sys.executable, '-B', str(SCRIPT), *args], cwd=ROOT,
        text=True, capture_output=True, timeout=10,
    )


def snapshot():
    entries = {}
    for name in ('hass', 'storefront-mockup'):
        root = ROOT / name
        for path in (root, *root.rglob('*')):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


def first_digits(text):
    match = re.search(r'\d+', text)
    return '%d.00' % int(match[0]) if match else None


class IntakeMoneyWordsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('npp_intake_money_words', SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError('could not load the intake money check')
        cls.tool = importlib.util.module_from_spec(spec)
        # The script adds the repo root to sys.path; keep the import local to this fixture.
        with patch.object(sys, 'path', sys.path[:]):
            spec.loader.exec_module(cls.tool)

    def run_main(self, expected_code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(code, expected_code)
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual(stderr.getvalue(), '')
        return lines[:-1]

    def assert_cli_pass(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c1_full_pass(self):
        # A missing sys.path bootstrap or a wrong CLI exit/trailer breaks normal use.
        self.assert_cli_pass(cli())

    def test_c2_findings_trailer(self):
        # Display-only drift must report after the changed case and fail the run too.
        intake = self.tool.item_intake
        display = intake.money_text
        with patch.object(intake, 'money_text', side_effect=lambda money: (
            'USD 0.57' if money == '0.57' else display(money)
        )):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, PINS[:5] + [
            "case 5 money='0.57' shown='USD 0.57'", 'FAIL money-changed 5',
        ] + PINS[6:])

    def test_c2_1_unsure_amount_read(self):
        # Taking the first digits would read ambiguous or out-of-range amounts.
        with patch.object(self.tool.item_intake, '_parse_money', side_effect=first_digits):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], [
            'FAIL money-changed 0', 'FAIL money-changed 1', 'FAIL money-changed 3',
            'FAIL money-changed 4', 'FAIL money-changed 5',
            'FAIL unsure-amount-read 6', 'FAIL money-changed 6',
            'FAIL unsure-amount-read 7', 'FAIL money-changed 7',
            'FAIL unsure-amount-read 8', 'FAIL money-changed 8',
            'FAIL unsure-amount-read 9', 'FAIL money-changed 9',
        ])
        for i in (6, 7, 8, 9):
            case = next(index for index, line in enumerate(lines) if line.startswith(f'case {i} '))
            self.assertEqual(lines[case + 1:case + 3], [
                f'FAIL unsure-amount-read {i}', f'FAIL money-changed {i}',
            ])

    def test_c2_2_money_changed(self):
        # Losing word parsing must insert the comparison finding immediately.
        with patch.object(self.tool.item_intake, 'ONES', {}):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, PINS[:4] + [
            "case 4 money=None shown=''", 'FAIL money-changed 4',
        ] + PINS[5:])

    def test_c2_3_check_error(self):
        # A repo exception must not leak details or allow a partial pass.
        intake = self.tool.item_intake
        for name in ('_parse_money', 'money_text'):
            with self.subTest(repo_call=name):
                with patch.object(intake, name, side_effect=RuntimeError('synthetic detail')) as broken:
                    self.assertEqual(self.run_main(1, FAIL), ['FAIL check-error'])
                broken.assert_called_once()

    def test_c3_usage_exit_2(self):
        # No flag (including implicit help) or positional may bypass usage validation.
        for arg in ('extra', '--unknown', '--help', '--'):
            with self.subTest(arg=arg):
                result = cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.startswith('usage: '))
                self.assertRegex(result.stderr.splitlines()[-1], r'^npp_intake_money_words\.py: error: .+$')

    def test_c4_read_only(self):
        # A writer creating a cache or touching existing input would change metadata.
        before = snapshot()
        self.assert_cli_pass(cli())
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Extra diagnostics, blank lines, or reordered case reports break consumers.
        result = cli()
        self.assert_cli_pass(result)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.stdout, '\n'.join([*PINS, PASS, '']))

    def test_c6_fixture(self):
        # Dropping the word table affects one pinned amount, not numeric controls.
        with patch.object(self.tool.item_intake, 'ONES', {}):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], ['FAIL money-changed 4'])

    def test_c7_live_pins(self):
        # Catch parser/display drift and prevent a constant-output stub passing.
        intake = self.tool.item_intake
        with (
            patch.object(intake, '_parse_money', wraps=intake._parse_money) as parse,
            patch.object(intake, 'money_text', wraps=intake.money_text) as display,
        ):
            self.assertEqual(self.run_main(0, PASS), PINS)
        self.assertEqual(parse.call_args_list, [call(text) for text in (
            '$9.57', '9.5', '9 dollars', '9 dollars and 57 cents', 'nine dollars',
            '57 cents', '4 or 5 bucks', 'about 4', '120 cents', '$1234567',
            '4 each', '$4 a jar', '',
        )])
        self.assertEqual(display.call_args_list, [call(money) for money in (
            '9.57', '9.50', '9.00', '9.57', '9.00', '0.57', None,
            None, None, None, '4.00', '4.00', None,
        )])


if __name__ == '__main__':
    unittest.main()
