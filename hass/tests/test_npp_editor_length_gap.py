"""Offline contract tests for the NPP/editor length comparison."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_editor_length_gap.py'
PASS = 'PASS npp_editor_length_gap'
FAIL = 'FAIL npp_editor_length_gap'


class NppEditorLengthGapTests(unittest.TestCase):
    def invoke(self, *args):
        with tempfile.TemporaryDirectory(dir=ROOT) as work:
            return subprocess.run(
                [sys.executable, '-B', str(SCRIPT), *args], cwd=work,
                capture_output=True, text=True, timeout=10,
            )

    def load(self):
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path[:]), patch.object(sys, 'dont_write_bytecode', True):
            spec.loader.exec_module(module)
        return module

    def run_main(self, module):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = module.main([])
        return code, stdout.getvalue().splitlines(), stderr.getvalue()

    def test_c1_full_pass(self):
        # No bindings is a completed check with no gap, not a max() error.
        module = self.load()
        with patch.object(module.copy.Writer, 'bindings', return_value={}):
            code, lines, _ = self.run_main(module)
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(lines[:-1], [
            'field brand longest-bound=0 editor=60',
            'field maker_name longest-bound=0 editor=80',
            'field town longest-bound=0 editor=60',
        ])

    def test_c2_findings_trailer(self):
        # A report with a gap must not return success or end with a PASS.
        result = self.invoke()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)

    def test_c2_1_limit_gap(self):
        # At 61 the two 60-character fields fail, but maker name must not.
        module = self.load()
        with patch.object(module, 'LENGTHS', (60, 61)):
            code, lines, _ = self.run_main(module)
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')], [
            'FAIL limit-gap brand', 'FAIL limit-gap town',
        ])

    def test_c2_2_check_error(self):
        # A failed binding probe must not silently pass, repeat, or print exception text.
        module = self.load()
        with patch.object(module.copy.Writer, 'bindings', side_effect=ValueError('synthetic detail')):
            code, lines, stderr = self.run_main(module)
        self.assertEqual(code, 1)
        self.assertEqual(lines, ['FAIL check-error', FAIL])
        self.assertEqual(stderr, '')

    def test_c3_usage_exit_2(self):
        # Default argparse help or ignored positional/option tokens would run or exit 0.
        for arg in ('extra', '--unknown', '--help', '-h', '--'):
            with self.subTest(arg=arg):
                result = self.invoke(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.startswith('usage:'))

    def test_c4_read_only(self):
        # A default artifact or catalog rewrite would change names, sizes, or mtimes.
        def snapshot():
            entries = {}
            for name in ('hass', 'storefront-mockup'):
                tree = ROOT / name
                for path in (tree, *tree.rglob('*')):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.invoke()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug chatter or raw probe text must not escape on either stream.
        result = self.invoke()
        lines = result.stdout.splitlines()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(result.stderr, '')
        for line in lines[:-1]:
            self.assertRegex(line, r'\A(?:field (?:brand|maker_name|town) longest-bound=[0-9]+ editor=[0-9]+'
                                   r'|FAIL (?:limit-gap (?:brand|maker_name|town)|check-error))\Z')

    def test_c6_fixture(self):
        # A length equal to the editor cap is allowed, and the report uses the probe lengths.
        module = self.load()
        with patch.object(module, 'LENGTHS', (40, 60)):
            code, lines, _ = self.run_main(module)
        self.assertEqual(code, 0)
        self.assertEqual(lines, [
            'field brand longest-bound=60 editor=60',
            'field maker_name longest-bound=60 editor=80',
            'field town longest-bound=60 editor=60',
            PASS,
        ])

    def test_c7_live_pins(self):
        # Actual binding or editor-limit drift must invalidate the measured baseline.
        result = self.invoke()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines(), [
            'field brand longest-bound=120 editor=60',
            'field maker_name longest-bound=120 editor=80',
            'field town longest-bound=120 editor=60',
            'FAIL limit-gap brand', 'FAIL limit-gap maker_name', 'FAIL limit-gap town',
            FAIL,
        ])
