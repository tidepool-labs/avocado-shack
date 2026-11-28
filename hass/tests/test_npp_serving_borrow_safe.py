"""Offline contract tests for the catalog serving-sentence borrow check."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import call, patch

from hass import claims, newitem


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_serving_borrow_safe.py'
PASS = 'PASS npp_serving_borrow_safe'
FAIL = 'FAIL npp_serving_borrow_safe'
LIVE = [
    'case 0 borrow=yes',
    'case 1 borrow=no',
    'case 2 borrow=no',
    'case 3 borrow=no',
    'case 4 borrow=no',
    'case 5 borrow=no',
    'case 6 borrow=yes',
    'case 7 borrow=no',
    'case 8 borrow=yes',
    'case 9 borrow=yes',
]


def run_cli(*args):
    return subprocess.run([sys.executable, '-B', str(SCRIPT), *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=10)


def snapshot():
    entries = {}
    for name in ('hass', 'storefront-mockup'):
        tree = ROOT / name
        for path in (tree, *tree.rglob('*')):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class ServingBorrowSafeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('npp_serving_borrow_safe', SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.script = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(cls.script)

    def run_main(self, code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.script.main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(status, code)
        self.assertEqual(lines[-1], trailer)
        self.assertEqual(stderr.getvalue(), '')
        return lines[:-1]

    def test_c1_full_pass(self):
        # A false failure or skipping repo checks must not report a clean run.
        with patch.object(newitem, '_serving_ok', wraps=newitem._serving_ok) as check:
            self.run_main(0, PASS)
        self.assertEqual(check.call_args_list, [call(s, '') for s in self.script.CASES])

    def test_c2_findings_trailer(self):
        # A plain drift finding must fail even without an unsafe borrow.
        claim_terms = newitem.claim_terms

        def extra_claim(text):
            return ['toast'] if text == 'Spoon it onto warm toast.' else claim_terms(text)

        with patch.object(newitem, 'claim_terms', extra_claim):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, ['case 0 borrow=no', 'FAIL borrow-changed 0', *LIVE[1:]])

    def test_c2_1_unsafe_serving_borrowed(self):
        # Losing the claim filter must flag both cases, adjacent and in order.
        with patch.object(newitem, 'claim_terms', lambda text: []):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, [
            *LIVE[:5], 'case 5 borrow=yes', 'FAIL unsafe-serving-borrowed 5',
            'FAIL borrow-changed 5', LIVE[6], 'case 7 borrow=yes',
            'FAIL unsafe-serving-borrowed 7', 'FAIL borrow-changed 7', *LIVE[8:],
        ])

    def test_c2_2_borrow_changed(self):
        # Reporting only the safety finding would miss drift in the pinned row.
        with patch.object(claims, 'TERMS', ()):
            lines = self.run_main(1, FAIL)
        index = lines.index('case 5 borrow=yes')
        self.assertEqual(lines[index + 1:index + 3], [
            'FAIL unsafe-serving-borrowed 5', 'FAIL borrow-changed 5',
        ])

    def test_c2_3_check_error(self):
        # A predicate error must stop the run without a partial case or details.
        with patch.object(newitem, '_serving_ok', side_effect=RuntimeError('fixture detail')) as check:
            self.assertEqual(self.run_main(1, FAIL), ['FAIL check-error'])
        check.assert_called_once_with('Spoon it onto warm toast.', '')

    def test_c3_usage_exit_2(self):
        # Permissive parsing (including built-in help) would admit an argument.
        for arg in ('fixture', '--unknown', '--help', '-h', '--'):
            with self.subTest(arg=arg):
                result = run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')  # No stdout trailer on usage errors.
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f'{SCRIPT.name}: error: unrecognized arguments: {arg}')

    def test_c4_read_only(self):
        # A cache, report or rewrite under either tree changes the snapshot.
        before = snapshot()
        result = run_cli()
        self.assertEqual(snapshot(), before)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c5_output_shape(self):
        # Debug output on either stream breaks the line-oriented interface.
        result = run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], PASS)
        for line in lines[:-1]:
            self.assertRegex(line, r'\Acase [0-9] borrow=(yes|no)\Z')

    def test_c6_fixture(self):
        # Removing general terms must not remove the separate health vocabulary.
        with patch.object(claims, 'TERMS', ()):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, [
            *LIVE[:5], 'case 5 borrow=yes', 'FAIL unsafe-serving-borrowed 5',
            'FAIL borrow-changed 5', *LIVE[6:],
        ])

    def test_c7_live_pins(self):
        # Any baseline answer change, missing row or stray finding breaks the pin.
        result = run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [*LIVE, PASS])
