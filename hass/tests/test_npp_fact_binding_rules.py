"""Offline contract tests for the NPP maker fact binding checker."""

from contextlib import chdir, redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_fact_binding_rules.py'
PASS = 'PASS npp_fact_binding_rules'
FAIL = 'FAIL npp_fact_binding_rules'
EXPECTED = {
    'ok': 'yes',
    'bad-id': 'no',
    'refutes': 'no',
    'empty-quote': 'no',
    'value-not-said': 'no',
    'hedged': 'no',
    'two-same-slot': 'no',
    'dup-id': 'no',
    'owner-not-said': 'no',
    'owner-said': 'yes',
    'http-url': 'yes',
    'bad-url': 'no',
}


def snapshot():
    entries = {}
    for tree in (ROOT / 'hass', ROOT / 'storefront-mockup'):
        for path in (tree, *tree.rglob('*')):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class FactBindingRulesTests(unittest.TestCase):
    def setUp(self):
        self.cwd = self.enterContext(TemporaryDirectory())
        spec = importlib.util.spec_from_file_location('npp_fact_binding_rules', SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        with chdir(self.cwd), patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(self.tool)
        self.writer = self.tool.copy.Writer
        self.bindings = self.writer.bindings

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args],
                              cwd=self.cwd, capture_output=True, text=True, timeout=10)

    def run_main(self):
        stdout, stderr = StringIO(), StringIO()
        with chdir(self.cwd), redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        return code, stdout.getvalue().splitlines(), stderr.getvalue()

    def assert_result(self, code, lines, stderr, status, trailer):
        self.assertEqual(code, status, (lines, stderr))
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual(stderr, '')

    def drift(self, change):
        # Change the observed result only after the real binding check runs.
        def changed(writer, ctx, field):
            result = self.bindings(writer, ctx, field)
            change(ctx, result)
            return result

        with patch.object(self.writer, 'bindings', changed):
            return self.run_main()

    def test_c1_full_pass(self):
        # A healthy check must not end with a failure status or omit its receipt.
        result = self.cli()
        self.assert_result(result.returncode, result.stdout.splitlines(), result.stderr, 0, PASS)

    def test_c2_findings_trailer(self):
        # Multiple findings must not short-circuit the remaining checks or exit 0.
        def change(ctx, result):
            if ctx.facts[0].id == '1bad':
                result['makes'] = ('honey', '1bad')
            if ctx.facts[0].url == 'http://ettofarm.example/':
                result.pop('makes')

        code, lines, stderr = self.drift(change)
        self.assert_result(code, lines, stderr, 1, FAIL)
        self.assertEqual(lines[-4:], ['fact http-url makes=no', 'FAIL fact-dropped http-url',
                                      'fact bad-url makes=no', FAIL])
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')],
                         ['FAIL fact-bound bad-id', 'FAIL fact-dropped http-url'])

    def test_c2_1_fact_bound(self):
        # Unexpected bindings must be identified by case, once per refusal.
        def change(ctx, result):
            result.setdefault('makes', ('honey', ctx.facts[0].id))

        code, lines, stderr = self.drift(change)
        self.assert_result(code, lines, stderr, 1, FAIL)
        expected = []
        for name, makes in EXPECTED.items():
            expected.append(f'fact {name} makes=yes')
            if makes == 'no':
                expected.append(f'FAIL fact-bound {name}')
        self.assertEqual(lines, [*expected, FAIL])

    def test_c2_2_fact_dropped(self):
        # Missing valid bindings must be reported, not treated as refusals that passed.
        code, lines, stderr = self.drift(lambda ctx, result: result.pop('makes', None))
        self.assert_result(code, lines, stderr, 1, FAIL)
        expected = []
        for name, makes in EXPECTED.items():
            expected.append(f'fact {name} makes=no')
            if makes == 'yes':
                expected.append(f'FAIL fact-dropped {name}')
        self.assertEqual(lines, [*expected, FAIL])

    def test_c2_3_check_error(self):
        # An incomplete check must fail without leaking the exception or losing later cases.
        def change(ctx, result):
            if ctx.facts[0].id == '1bad':
                raise RuntimeError('synthetic exception detail')

        code, lines, stderr = self.drift(change)
        self.assert_result(code, lines, stderr, 1, FAIL)
        expected = [f'fact {name} makes={makes}' if name != 'bad-id' else 'FAIL check-error'
                    for name, makes in EXPECTED.items()]
        self.assertEqual(lines, [*expected, FAIL])

    def test_c3_usage_exit_2(self):
        # Parsing must reject arguments before printing normal check output.
        for arg in ('unexpected', '--unknown', '--help', '--'):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, '')  # No stdout trailer on usage errors.
                self.assertTrue(result.stderr.startswith('usage: '))
                self.assertIn('error:', result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Catch incidental cache, report, or asset writes to either source tree.
        before = snapshot()
        result = self.cli()
        self.assert_result(result.returncode, result.stdout.splitlines(), result.stderr, 0, PASS)
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(Path(self.cwd).iterdir()), [])

    def test_c5_output_shape(self):
        # Strict consumers must see only the named lines, in order, with no diagnostics.
        result = self.cli()
        self.assert_result(result.returncode, result.stdout.splitlines(), result.stderr, 0, PASS)
        expected = ''.join(f'fact {name} makes={makes}\n' for name, makes in EXPECTED.items())
        self.assertEqual(result.stdout, expected + PASS + '\n')

    def test_c6_fixture(self):
        # Bypassing hedge detection alone must allow the hedged quote and turn the CLI red.
        _, files, _ = self.tool.npp.assets()
        markers = json.loads(files['hass-maker-research/facts.schema.json'])['negation_hedge_markers']
        claims = self.tool.copy.claims
        said = claims._said

        def ignore_hedges(phrase, text):
            return False if phrase in markers else said(phrase, text)

        with patch.object(claims, '_said', ignore_hedges):
            code, lines, stderr = self.run_main()
        self.assert_result(code, lines, stderr, 1, FAIL)
        self.assertIn('fact hedged makes=yes', lines)
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')],
                         ['FAIL fact-bound hedged'])
        code, lines, stderr = self.run_main()
        self.assert_result(code, lines, stderr, 0, PASS)
        self.assertIn('fact hedged makes=no', lines)

    def test_c7_live_pins(self):
        # Observe real bindings, not just the CLI's yes/no oracle: refusal must be selective.
        observed = []

        def observe(writer, ctx, field):
            result = self.bindings(writer, ctx, field)
            observed.append((field, result))
            return result

        with patch.object(self.writer, 'bindings', observe):
            code, lines, stderr = self.run_main()
        self.assert_result(code, lines, stderr, 0, PASS)
        self.assertEqual(len(observed), len(EXPECTED))
        for (name, makes), (field, result) in zip(EXPECTED.items(), observed):
            with self.subTest(case=name):
                self.assertEqual(field, 'story')
                expected: dict[str, tuple[str, str | None]] = {
                    'item': ('Honey', None), 'maker_name': ('Etto Farm', None),
                }
                if makes == 'yes':
                    expected['makes'] = ('honey', 'official-makes')
                self.assertEqual(result, expected)


if __name__ == '__main__':
    unittest.main()
