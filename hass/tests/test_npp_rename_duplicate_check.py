"""Offline contracts for the positional S10/S3 duplicate report."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_rename_duplicate_check.py'
PASS = 'PASS npp_rename_duplicate_check'
FAIL = 'FAIL npp_rename_duplicate_check'


class RenameDuplicateCheckTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.scratch = Path(temp.name)
        spec = importlib.util.spec_from_file_location('npp_rename_duplicate_check', SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(self.tool)

    def fixture(self, positions=(1,)):
        content = self.scratch / 'hass' / 'content'
        content.mkdir(parents=True)
        for name, payload in (
            ('products', {'products': [{'name': title, 'status': 'active'} for title in
                                        ('Fixture Plum', 'Fixture Pear')]}),
            ('makers', {'makers': {}}), ('community', {}), ('store', {}),
        ):
            (content / f'{name}.json').write_text(json.dumps({'schemaVersion': 1, **payload}), encoding='utf-8')
        self.enterContext(patch.object(self.tool, 'ROOT', self.scratch))
        self.enterContext(patch.object(self.tool, 'POSITIONS', positions))

    def run_main(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        self.assertEqual(stderr.getvalue(), '')
        return code, stdout.getvalue().splitlines()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args], cwd=self.scratch,
                              capture_output=True, text=True, timeout=10, check=False)

    def test_c1_full_pass(self):
        # A real duplicate with the duplicate question must not be counted as unasked.
        self.fixture()
        edit = self.tool.Stages.edit

        def ask(st, work):
            plan = edit(st, work)
            if (plan.listing or {}).get('name') == 'Fixture Plum':
                return replace(plan, questions=(('duplicate', 'Fixture question'),))
            return plan

        with patch.object(self.tool.Stages, 'edit', ask):
            code, lines = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(lines, ['rename 01 renamed=yes duplicate=yes asked=yes',
                                 'rename 02 renamed=yes duplicate=no asked=no', PASS])

    def test_c2_findings_trailer(self):
        # A clean final row must not wipe out an earlier failure or replace the trailer.
        self.fixture()
        code, lines = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-2:], ['rename 02 renamed=yes duplicate=no asked=no', FAIL])

    def test_c2_1_rename_unasked(self):
        # Findings must use report row numbers, not catalog positions, and follow each offending row.
        self.fixture((2, 1))
        code, lines = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(lines, ['rename 01 renamed=yes duplicate=yes asked=no', 'FAIL rename-unasked 01',
                                 'rename 02 renamed=yes duplicate=yes asked=no', 'FAIL rename-unasked 02',
                                 'rename 03 renamed=yes duplicate=no asked=no', FAIL])

    def test_c2_2_position_missing(self):
        # A valid position must not yield a partial report, and zero must not wrap to the last item.
        self.fixture()
        for invalid in (0, 3):
            with self.subTest(invalid=invalid), patch.object(self.tool, 'POSITIONS', (1, invalid)):
                code, lines = self.run_main()
                self.assertEqual(code, 1)
                self.assertEqual(lines, ['FAIL position-missing', FAIL])

    def test_c2_3_check_error(self):
        # Exceptions are named, redacted findings; a later clean check still runs.
        self.fixture()
        original = self.tool.missing._duplicates

        def duplicates(name, *inputs):
            if name == 'Fixture Plum':
                raise ValueError('synthetic exception detail')
            return original(name, *inputs)

        with patch.object(self.tool.missing, '_duplicates', duplicates):
            code, lines = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(lines, ['FAIL check-error', 'rename 02 renamed=yes duplicate=no asked=no', FAIL])

    def test_c3_usage_exit_2(self):
        # Neither normal work nor the default help action may run when arguments are supplied.
        for arg in ('fixture', '--unknown', '--help', '--'):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertIn('usage:', result.stderr)
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f'{SCRIPT.name}: error: unrecognized arguments: {arg}')

    def test_c4_read_only(self):
        # A future write-back or bytecode side effect changes a path, size, or mtime.
        def snapshot():
            paths = []
            for tree in (ROOT / 'hass', ROOT / 'storefront-mockup'):
                paths.extend([tree, *tree.rglob('*')])
            result = {}
            for path in paths:
                stat = path.lstat()
                result[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
            return result

        before = snapshot()
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Raw names, unexpected diagnostics, or extra tokens must not escape the CLI.
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, '')
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        for line in lines[:-1]:
            self.assertRegex(line, r'^(rename [0-9]{2} renamed=(yes|no) duplicate=(yes|no) asked=(yes|no)'
                                   r'|FAIL (rename-unasked [0-9]{2}|position-missing|check-error))$')

    def test_c6_fixture(self):
        # No selected catalog positions must still exercise and report the synthetic extra name.
        with patch.object(self.tool, 'POSITIONS', ()):
            code, lines = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(lines, ['rename 01 renamed=yes duplicate=no asked=no', PASS])

    def test_c7_live_pins(self):
        # Offline base-catalog pin: catches a change in sampled coverage or S10/S3 behavior.
        code, lines = self.run_main()
        self.assertEqual(code, 1)
        expected = []
        for pos in ('01', '02', '03', '04'):
            expected.extend([f'rename {pos} renamed=yes duplicate=yes asked=no', f'FAIL rename-unasked {pos}'])
        self.assertEqual(lines, expected + ['rename 05 renamed=yes duplicate=no asked=no', FAIL])


if __name__ == '__main__':
    unittest.main()
