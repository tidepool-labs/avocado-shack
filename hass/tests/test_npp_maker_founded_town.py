"""Offline contract tests for the maker founding-year and town drift guard."""

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
SCRIPT = ROOT / 'scripts/hass/npp_maker_founded_town.py'
PASS = 'PASS npp_maker_founded_town'
FAIL = 'FAIL npp_maker_founded_town'


def snapshot():
    entries = {}
    for tree in (ROOT / 'hass', ROOT / 'storefront-mockup'):
        for path in (tree, *tree.rglob('*')):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class MakerFoundedTownTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        if spec is None or spec.loader is None:
            self.fail('Could not load the checker script')
        self.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(self.tool)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, '-B', str(SCRIPT), *args], cwd=ROOT,
            capture_output=True, text=True, timeout=10,
        )

    def in_process(self, code, trailer):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = self.tool.main([])
        lines = out.getvalue().splitlines()
        self.assertEqual(result, code)
        self.assertEqual(lines[-1], trailer)
        self.assertEqual(err.getvalue(), '')
        return lines

    def with_tail(self, pattern):
        with patch.object(self.tool.maker_site, '_FOUNDING_TAIL', re.compile(pattern)):
            return self.in_process(1, FAIL)

    def test_c1_full_pass(self):
        # A CLI wiring regression can lose the success exit or trailer.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # Multiple failing cases must not make the run bail early or batch findings.
        site = self.tool.maker_site
        original_based = site._based

        def wrong_town(sentence, name, town):
            return original_based(sentence, name, 'Ojai' if 'Ojai' in sentence else town)

        with patch.object(site, '_based', side_effect=wrong_town):
            lines = self.with_tail(r'.*')
        self.assertEqual(lines[6:10], [
            'case 6 since=0 based=yes', 'FAIL unstated-fact-read 6',
            'FAIL fact-changed 6', 'case 7 since=0 based=yes',
        ])
        self.assertEqual(lines[-4:], [
            'case 12 since=1998 based=no', 'FAIL unstated-fact-read 12',
            'FAIL fact-changed 12', FAIL,
        ])
        self.assertEqual([line for line in lines[:-1] if not line.startswith('case ')], [
            'FAIL unstated-fact-read 6', 'FAIL fact-changed 6',
            'FAIL unstated-fact-read 12', 'FAIL fact-changed 12',
        ])

    def test_c2_1_unstated_fact_read(self):
        # An overbroad founding suffix can incorrectly treat a purpose as a fact.
        lines = self.with_tail(r'.*')
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')], [
            'FAIL unstated-fact-read 12', 'FAIL fact-changed 12',
        ])

    def test_c2_2_fact_changed(self):
        # A lost valid founding year must be reported even without an invented fact.
        lines = self.with_tail(r'\.')
        self.assertEqual(lines[1:4], [
            'case 1 since=0 based=no', 'FAIL fact-changed 1', 'case 2 since=2019 based=no',
        ])

    def test_c2_3_check_error(self):
        # Neither helper throwing should leak exception text or allow another case.
        site = self.tool.maker_site
        for helper in ('_since', '_based'):
            with self.subTest(helper=helper):
                with patch.object(site, helper, side_effect=RuntimeError('synthetic error')) as broken:
                    self.assertEqual(self.in_process(1, FAIL), ['FAIL check-error', FAIL])
                broken.assert_called_once()

    def test_c3_usage_exit_2(self):
        # Default help or a bare separator could accidentally accept arguments.
        for arg in ('extra', '--unknown', '--help', '--'):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.startswith('usage: '))
                self.assertIn(': error: ', result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Catch an accidental cache, report file, or rewrite in either input tree.
        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # A progress/debug print could break consumers even when the exit is right.
        result = self.cli()
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(len(lines), 14)
        for i, line in enumerate(lines[:-1]):
            self.assertIsNotNone(re.fullmatch(rf'case {i} since=\d+ based=(yes|no)', line), line)

    def test_c6_fixture(self):
        # A dot-only tail must affect exactly the founder-clause fixture via _since.
        lines = self.with_tail(r'\.')
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')], ['FAIL fact-changed 1'])
        self.assertEqual(sum(line.startswith('case ') for line in lines), 13)

    def test_c7_live_pins(self):
        # Catch drift or bypass of the live helpers; do not reuse the CLI's EXPECTED.
        site = self.tool.maker_site
        with (patch.object(site, '_since', wraps=site._since) as since,
              patch.object(site, '_based', wraps=site._based) as based):
            lines = self.in_process(0, PASS)
        self.assertEqual(since.call_args_list, [call(s, n) for s, n, _ in self.tool.CASES])
        self.assertEqual(based.call_args_list, [call(*case) for case in self.tool.CASES])
        self.assertEqual(lines[:-1], [
            'case 0 since=1998 based=no',
            'case 1 since=1998 based=no',
            'case 2 since=2019 based=no',
            'case 3 since=0 based=no',
            'case 4 since=0 based=no',
            'case 5 since=0 based=yes',
            'case 6 since=0 based=no',
            'case 7 since=0 based=yes',
            'case 8 since=0 based=yes',
            'case 9 since=0 based=no',
            'case 10 since=0 based=no',
            'case 11 since=0 based=no',
            'case 12 since=0 based=no',
        ])
