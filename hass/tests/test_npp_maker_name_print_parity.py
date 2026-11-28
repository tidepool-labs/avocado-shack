"""Offline CLI contract for the S4/S5 maker identity diagnostic."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_maker_name_print_parity.py'
PASS = 'PASS npp_maker_name_print_parity'
FAIL = 'FAIL npp_maker_name_print_parity'


class MakerNamePrintParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path[:]):
            spec.loader.exec_module(cls.tool)

    def run_main(self, exit_code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        return self.assert_report(code, stdout.getvalue(), stderr.getvalue(), exit_code, trailer)

    def run_cli(self, *args):
        with TemporaryDirectory() as cwd:
            return subprocess.run([sys.executable, '-B', str(SCRIPT), *args], cwd=cwd,
                                  capture_output=True, text=True, timeout=15)

    def assert_report(self, code, stdout, stderr, exit_code, trailer):
        self.assertEqual(code, exit_code, stderr)
        self.assertEqual(stderr, '')
        lines = stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines

    def test_c1_full_pass(self):
        # An unconditional failure trailer or bypassing Writer.bindings breaks this.
        bindings = self.tool.copy.Writer.bindings

        def bind_all(writer, ctx, field_name):
            bound = bindings(writer, ctx, field_name)
            for key in ('maker_name', 'town'):
                if value := getattr(ctx, key):
                    bound.setdefault(key, (value, None))
            return bound

        with patch.object(self.tool.copy.Writer, 'bindings', bind_all):
            lines = self.run_main(0, PASS)
        self.assertEqual(lines[:-1], [
            f'{label} {i} s4=yes s5=yes' for label, count in (('name', 4), ('town', 3))
            for i in range(count)
        ])

    def test_c2_findings_trailer(self):
        # A finding on the very last row must still change exit and trailer.
        identity = self.tool.research._identity_field
        with patch.object(self.tool.research, '_identity_field',
                          side_effect=lambda value: value == 'Mt. Shasta' and identity(value)):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines[-3:], ['town 2 s4=yes s5=no', 'FAIL s5-cannot-print town 2', FAIL])
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')],
                         ['FAIL s5-cannot-print town 2'])

    def test_c2_1_s5_cannot_print(self):
        # Neither S5-only acceptance nor rejection by both stages is a finding.
        identity = self.tool.research._identity_field
        with patch.object(self.tool.research, '_identity_field',
                          side_effect=lambda value: value not in ('Watsonville', 'Smith & Sons')
                          and identity(value)):
            lines = self.run_main(1, FAIL)
        self.assertIn('name 1 s4=no s5=no', lines)
        self.assertIn('town 0 s4=no s5=yes', lines)
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')], [
            'FAIL s5-cannot-print name 2', 'FAIL s5-cannot-print name 3',
            'FAIL s5-cannot-print town 1', 'FAIL s5-cannot-print town 2',
        ])

    def test_c2_2_check_error(self):
        # A missing asset must not leak an exception or silently report success.
        with patch.object(self.tool.hass.npp, 'assets', side_effect=RuntimeError('fixture detail')):
            self.assertEqual(self.run_main(1, FAIL), ['FAIL check-error', FAIL])

        # A failure in one row must be recorded without losing the later checks.
        identity = self.tool.research._identity_field

        def fail_first(value):
            if value == 'Miners Orchards':
                raise RuntimeError('fixture detail')
            return identity(value)

        with patch.object(self.tool.research, '_identity_field', fail_first):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines[0], 'FAIL check-error')
        self.assertEqual(lines.count('FAIL check-error'), 1)
        self.assertNotIn('name 0 s4=yes s5=yes', lines)
        self.assertIn('town 2 s4=yes s5=no', lines)
        self.assertNotIn('fixture detail', '\n'.join(lines))

    def test_c3_usage_exit_2(self):
        # parse_known_args or default --help would accept prohibited arguments.
        for arg in ('unexpected', '--unknown', '--help', '-h', '--', ''):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, '')  # No stdout trailer on usage errors.
                self.assertIn('error: unrecognized arguments:', result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Catch a repo-local report, cache, or update to a pinned input.
        def snapshot():
            entries = {}
            for subtree in ('hass', 'storefront-mockup'):
                tree = ROOT / subtree
                for path in (tree, *tree.rglob('*')):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.run_cli()
        self.assert_report(result.returncode, result.stdout, result.stderr, 1, FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Reject debug lines, fixture text, or an accidental stderr report.
        result = self.run_cli()
        lines = self.assert_report(result.returncode, result.stdout, result.stderr, 1, FAIL)
        row = r'(?:name [0-3]|town [0-2]) s4=(?:yes|no) s5=(?:yes|no)'
        finding = r'FAIL (?:s5-cannot-print (?:name [0-3]|town [0-2])|check-error)'
        for line in lines[:-1]:
            self.assertIsNotNone(re.fullmatch(f'(?:{row}|{finding})', line), line)

    def test_c6_fixture(self):
        # Widening plain must clear ampersands without bypassing the owner-word check.
        plain = self.tool.copy.plain

        def widened(value, maximum=12):
            return plain(value, maximum) or (
                self.tool.research._identity_field(value)
                and len(self.tool.copy.words(value)) <= maximum
            )

        with patch.object(self.tool.copy, 'plain', widened):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')], [
            'FAIL s5-cannot-print name 2', 'FAIL s5-cannot-print town 1',
            'FAIL s5-cannot-print town 2',
        ])

    def test_c7_live_pins(self):
        # Pin the observed gap, including clean controls and findings in check order.
        self.assertEqual(self.run_main(1, FAIL), [
            'name 0 s4=yes s5=yes',
            'name 1 s4=yes s5=no',
            'FAIL s5-cannot-print name 1',
            'name 2 s4=yes s5=no',
            'FAIL s5-cannot-print name 2',
            'name 3 s4=yes s5=no',
            'FAIL s5-cannot-print name 3',
            'town 0 s4=yes s5=yes',
            'town 1 s4=yes s5=no',
            'FAIL s5-cannot-print town 1',
            'town 2 s4=yes s5=no',
            'FAIL s5-cannot-print town 2',
            FAIL,
        ])
