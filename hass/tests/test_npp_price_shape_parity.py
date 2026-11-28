"""Offline contract tests for the S3/editor price-shape check."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass import content_model
from hass.npp.missing import MissingInfo

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_price_shape_parity.py'
SPEC = importlib.util.spec_from_file_location('npp_price_shape_parity', SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)

PASS = 'PASS npp_price_shape_parity'
FAIL = 'FAIL npp_price_shape_parity'
ALIGNED = r'[0-9]{1,6}\.[0-9]{2}(?: per lb| each)?'
KEPT = {0, 1, 2, 3, 4, 5, 10}
LIVE_ACCEPTED = {0, 2, 5, 10}
LIVE_FINDINGS = ['FAIL s3-only 1', 'FAIL s3-only 3', 'FAIL s3-only 4']


def run_script(*args):
    with TemporaryDirectory() as cwd:
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args], cwd=cwd,
                              capture_output=True, text=True, timeout=10)


def snapshot():
    entries = {}
    for name in ('hass', 'storefront-mockup'):
        tree = ROOT / name
        for path in (tree, *tree.rglob('*')):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class PriceShapeParityTests(unittest.TestCase):
    def run_main(self, pattern):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (patch.object(content_model, 'SELLING_PRICE_RE', re.compile(pattern)),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            code = CHECK.main([])
        self.assertEqual(stderr.getvalue(), '')
        return code, stdout.getvalue().splitlines()

    def assert_result(self, result, code, trailer, findings=()):
        actual_code, lines = result
        self.assertEqual(actual_code, code)
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')], list(findings))
        return [line for line in lines if line.startswith('price ')]

    def test_c1_full_pass(self):
        # A clean matrix must not leave a stale failure status or trailer.
        self.assert_result(self.run_main(ALIGNED), 0, PASS)

    def test_c2_findings_trailer(self):
        # Mixed findings must still emit one final failure trailer after all rows.
        pattern = ALIGNED.replace('[0-9]{1,6}', '(?:0|[1-9][0-9]{0,5})') + '|4 per lb'
        result = self.run_main(pattern)
        self.assert_result(result, 1, FAIL, [*LIVE_FINDINGS, 'FAIL editor-only 8'])
        self.assertEqual(result[1].count(FAIL), 1)
        self.assertEqual(result[1][-2], 'price 10 s3=kept each=yes per-lb=yes')

    def test_c2_1_s3_only(self):
        # Reject a kept amount for only one unit; requiring both to fail misses it.
        pattern = r'(?!04\.00 per lb$)' + ALIGNED
        rows = self.assert_result(self.run_main(pattern), 1, FAIL, ['FAIL s3-only 1'])
        self.assertEqual(rows[1], 'price 1 s3=kept each=yes per-lb=no')

    def test_c2_2_editor_only(self):
        # Checking only kept rows or only 'each' hides a one-unit editor expansion.
        rows = self.assert_result(self.run_main(ALIGNED + '|4 per lb'), 1, FAIL,
                                  ['FAIL editor-only 8'])
        self.assertEqual(rows[8], 'price 8 s3=asked each=no per-lb=yes')

    def test_c2_3_control_broken(self):
        # Agreement on refusal is not a pass if the positive control breaks.
        decide = MissingInfo.decide

        def asks_on_control(self, **kwargs):
            decision = decide(self, **kwargs)
            if kwargs['price'].amount == '4.00':
                return replace(decision, price=replace(decision.price, amount=None))
            return decision

        for unit in ('each', 'per lb'):
            with self.subTest(unit=unit):
                self.assert_result(self.run_main(rf'(?!4\.00 {unit}$)' + ALIGNED),
                                   1, FAIL, ['FAIL s3-only 0', 'FAIL control-broken'])
        with patch.object(MissingInfo, 'decide', asks_on_control):
            self.assert_result(self.run_main(r'(?!4\.00 )' + ALIGNED),
                               1, FAIL, ['FAIL control-broken'])

    def test_c2_4_check_error(self):
        # A raised check, changed amount, wrong validator return, or unrelated
        # problem must not become a refusal. The validation fault is on an asked row.
        decide = MissingInfo.decide
        validate = content_model.validate_products
        marker = 'synthetic-check-exception'

        def decide_fault(self, **kwargs):
            decision = decide(self, **kwargs)
            if kwargs['price'].amount == '0.50':
                if fault == 'decide exception':
                    raise RuntimeError(marker)
                return replace(decision, price=replace(decision.price, amount='0.51'))
            return decision

        def validation_fault(problems, products, makers, site_dir):
            validate(problems, products, makers, site_dir)
            if products[0]['sellingPrice'] == '4 per lb':
                if fault == 'validator exception':
                    raise ValueError(marker)
                if fault == 'validator return':
                    return True
                problems.append(marker)

        for fault, target, name, hook, missing_index in (
            ('decide exception', MissingInfo, 'decide', decide_fault, 2),
            ('changed amount', MissingInfo, 'decide', decide_fault, 2),
            ('validator exception', content_model, 'validate_products', validation_fault, 8),
            ('validator return', content_model, 'validate_products', validation_fault, 8),
            ('extra problem', content_model, 'validate_products', validation_fault, 8),
        ):
            with self.subTest(fault=fault), patch.object(target, name, hook):
                result = self.run_main(ALIGNED)
                rows = self.assert_result(result, 1, FAIL, ['FAIL check-error'])
                self.assertNotIn(marker, '\n'.join(result[1]))
                self.assertEqual([int(line.split()[1]) for line in rows],
                                 [i for i in range(11) if i != missing_index])

    def test_c3_usage_exit_2(self):
        # Unknown CLI inputs must fail in argparse before running any checks.
        for arg in ('extra', '--unknown'):
            with self.subTest(arg=arg):
                result = run_script(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertIn('unrecognized arguments:', result.stderr)

    def test_c4_read_only(self):
        # A standalone run must not persist even an intermediate repo artifact.
        before = snapshot()
        result = run_script()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1:], [FAIL])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug output or raw diagnostics would break consumers of the CLI.
        result = run_script()
        self.assertEqual(result.stderr, '')
        self.assertTrue(result.stdout.endswith('\n'))
        rows = self.assert_result((result.returncode, result.stdout.splitlines()), 1, FAIL, LIVE_FINDINGS)
        for i, row in enumerate(rows):
            self.assertRegex(row, rf'\Aprice {i} s3=(kept|asked) each=(yes|no) per-lb=(yes|no)\Z')
        self.assertEqual(len(rows), 11)
        self.assertEqual(len(result.stdout.splitlines()), len(rows) + len(LIVE_FINDINGS) + 1)

    def test_c6_fixture(self):
        # A copied price rule cannot respond when the real validator's gate changes.
        rows = self.assert_result(self.run_main(ALIGNED), 0, PASS)
        self.assert_matrix(rows, KEPT)

    def test_c7_live_pins(self):
        # The unpatched entry point should report exactly the measured real gap.
        result = run_script()
        rows = self.assert_result((result.returncode, result.stdout.splitlines()), 1, FAIL, LIVE_FINDINGS)
        self.assert_matrix(rows, LIVE_ACCEPTED)

    def assert_matrix(self, rows, accepted):
        expected = []
        for i in range(11):
            s3 = 'kept' if i in KEPT else 'asked'
            editor = 'yes' if i in accepted else 'no'
            expected.append(f'price {i} s3={s3} each={editor} per-lb={editor}')
        self.assertEqual(rows, expected)


if __name__ == '__main__':
    unittest.main()
