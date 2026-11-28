"""Offline CLI and fixture tests for the S4/S5 founded-year comparison."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_founded_year_parity.py'
PASS = 'PASS npp_founded_year_parity'
FAIL = 'FAIL npp_founded_year_parity'
SPLIT = 'FAIL founded-split 2027-01-04 2027'


class FoundedYearParityTests(unittest.TestCase):
    def setUp(self):
        fixture = TemporaryDirectory(dir=ROOT)
        self.addCleanup(fixture.cleanup)
        self.fixture_root = Path(fixture.name)

    def load(self):
        spec = importlib.util.spec_from_file_location('npp_founded_year_parity', SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def run_main(self, module):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = module.main([])
        self.assertEqual(err.getvalue(), '')
        return code, out.getvalue().splitlines()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, '-B', str(SCRIPT), *args], cwd=self.fixture_root,
            capture_output=True, text=True, timeout=15,
        )

    def assert_exit(self, code, lines, expected_code, trailer):
        self.assertEqual(code, expected_code, lines)
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)

    def test_c1_full_pass(self):
        # A matrix that agrees must return success, not the live baseline's exit 1.
        module = self.load()
        with patch.object(module, 'READ_DATES', ['2026-11-21']):
            code, lines = self.run_main(module)
        self.assert_exit(code, lines, 0, PASS)
        self.assertEqual(len(lines), 6)
        self.assertTrue(all(line.startswith('founded ') for line in lines[:-1]))

    def test_c2_findings_trailer(self):
        # An early error must not suppress a later mismatch or the one aggregate trailer.
        module = self.load()
        real_check = module.research._check

        def check(row, pages, *args):
            if row['value'] == '1799' and pages[row['url']].retrieved == '2026-11-21':
                raise ValueError('fixture failure')
            return real_check(row, pages, *args)

        with patch.object(module.research, '_check', side_effect=check):
            code, lines = self.run_main(module)
        self.assert_exit(code, lines, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')],
                         ['FAIL check-error', SPLIT, FAIL])

    def test_c2_1_founded_split(self):
        # A test that checks only S4-kept/S5-dropped misses the reverse disagreement.
        module = self.load()
        real_bindings = module.copy.Writer.bindings

        def bindings(writer, context, field_name):
            result = real_bindings(writer, context, field_name)
            fact, = context.facts
            if fact.value == '1799':
                result['founded'] = (fact.value, fact.id)
            return result

        with patch.object(module.copy.Writer, 'bindings', bindings):
            code, lines = self.run_main(module)
        self.assert_exit(code, lines, 1, FAIL)
        self.assertIn('founded 2026-11-21 1799 s4=invalid-year s5=yes', lines)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], [
            'FAIL founded-split 2026-11-21 1799',
            'FAIL founded-split 2027-01-04 1799', SPLIT, FAIL,
        ])

    def test_c2_2_control_broken(self):
        # Agreement alone is not success when both sides drop the known-good control.
        module = self.load()
        real_check = module.research._check
        real_bindings = module.copy.Writer.bindings

        def check(row, *args):
            reason = real_check(row, *args)
            return 'invalid-year' if row['value'] == '1800' else reason

        def bindings(writer, context, field_name):
            result = real_bindings(writer, context, field_name)
            if context.facts[0].value == '1800':
                result.pop('founded', None)
            return result

        with (patch.object(module, 'READ_DATES', ['2026-11-21']),
              patch.object(module.research, '_check', side_effect=check),
              patch.object(module.copy.Writer, 'bindings', bindings)):
            code, lines = self.run_main(module)
        self.assert_exit(code, lines, 1, FAIL)
        self.assertIn('founded 2026-11-21 1800 s4=invalid-year s5=no', lines)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')],
                         ['FAIL control-broken', FAIL])

    def test_c2_3_check_error(self):
        # Both dependency calls can fail; neither may crash, skip silently, or leak text.
        module = self.load()
        for owner, name in ((module.research, '_check'), (module.copy.Writer, 'bindings')):
            with self.subTest(name=name), patch.object(
                owner, name, side_effect=ValueError('synthetic exception detail'),
            ) as failing_call:
                code, lines = self.run_main(module)
                self.assert_exit(code, lines, 1, FAIL)
                self.assertEqual(lines, ['FAIL check-error', 'FAIL control-broken', FAIL])
                self.assertEqual(failing_call.call_count, 10)

    def test_c3_usage_exit_2(self):
        # Even help and the option terminator are arguments to this zero-argument tool.
        for arg in ('unexpected', '--unknown', '--help', '-h', '--'):
            with self.subTest(arg=arg):
                run = self.run_cli(arg)
                self.assertEqual(run.returncode, 2)
                self.assertEqual(run.stdout, '')  # No stdout trailer on a usage error.
                self.assertTrue(run.stderr.startswith('usage: '), run.stderr)
                self.assertEqual(run.stderr.splitlines()[-1],
                                 SCRIPT.name + ': error: no arguments accepted')

    def test_c4_read_only(self):
        # Accidental reports or rewrites must not touch either source tree.
        def snapshot():
            result = {}
            for directory in ('hass', 'storefront-mockup'):
                tree = ROOT / directory
                for path in (tree, *tree.rglob('*')):
                    info = path.lstat()
                    result[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return result

        before = snapshot()
        run = self.run_cli()
        self.assert_exit(run.returncode, run.stdout.splitlines(), 1, FAIL)
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(self.fixture_root.iterdir()), [])

    def test_c5_output_shape(self):
        # The runnable CLI must not add banners, blank lines, or stderr diagnostics.
        run = self.run_cli()
        lines = run.stdout.splitlines()
        self.assert_exit(run.returncode, lines, 1, FAIL)
        self.assertEqual(run.stderr, '')
        self.assertEqual(len(lines), 12)
        for line in lines[:-2]:
            self.assertRegex(line, r'^founded \d{4}-\d{2}-\d{2} \d{4} s4=[a-z-]+ s5=(yes|no)$')
        self.assertEqual(lines[-2], SPLIT)

    def test_c6_fixture(self):
        # Advance only the fixture's S5 upper bound, using the actual parsed read date.
        module = self.load()
        real_parse = module.research.parse_page
        real_bindings = module.copy.Writer.bindings
        read_year = 0

        def parse(*args):
            nonlocal read_year
            page = real_parse(*args)
            read_year = int(page.retrieved[:4])
            return page

        def bindings(writer, context, field_name):
            result = real_bindings(writer, context, field_name)
            fact, = context.facts
            if 2026 < int(fact.value) <= read_year:
                result['founded'] = (fact.value, fact.id)
            return result

        with (patch.object(module.research, 'parse_page', side_effect=parse),
              patch.object(module.copy.Writer, 'bindings', bindings)):
            code, lines = self.run_main(module)
        self.assert_exit(code, lines, 0, PASS)
        self.assertEqual(len(lines), 11)
        self.assertIn('founded 2026-11-21 2027 s4=invalid-year s5=no', lines)
        self.assertIn('founded 2027-01-04 2027 s4=kept s5=yes', lines)
        self.assertIn('founded 2027-01-04 2028 s4=invalid-year s5=no', lines)
        self.assertFalse(any(line.startswith('FAIL ') for line in lines))

    def test_c7_live_pins(self):
        # Pin the real decision matrix so a lost pair or changed date ceiling is visible.
        code, lines = self.run_main(self.load())
        self.assert_exit(code, lines, 1, FAIL)
        self.assertEqual(lines, [
            'founded 2026-11-21 1799 s4=invalid-year s5=no',
            'founded 2026-11-21 1800 s4=kept s5=yes',
            'founded 2026-11-21 2026 s4=kept s5=yes',
            'founded 2026-11-21 2027 s4=invalid-year s5=no',
            'founded 2026-11-21 2028 s4=invalid-year s5=no',
            'founded 2027-01-04 1799 s4=invalid-year s5=no',
            'founded 2027-01-04 1800 s4=kept s5=yes',
            'founded 2027-01-04 2026 s4=kept s5=yes',
            'founded 2027-01-04 2027 s4=kept s5=no',
            'founded 2027-01-04 2028 s4=invalid-year s5=no',
            SPLIT, FAIL,
        ])
