"""Offline contract tests for the S4 copyright-footer diagnostic."""

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
SCRIPT = ROOT / 'scripts/hass/npp_copyright_footer_shapes.py'
PASS = 'PASS npp_copyright_footer_shapes'
FAIL = 'FAIL npp_copyright_footer_shapes'
REFUSED = 'not-the-makers-own-site'
# Measured on origin/main at f07af52e; unchanged from 6ee9e685.
LIVE_REASONS = ['official'] * 6 + [REFUSED] * 9
LIVE_REFUSALS = range(6, 13)


def snapshot():
    result = {}
    for name in ('hass', 'storefront-mockup'):
        tree = ROOT / name
        for path in (tree, *tree.rglob('*')):
            stat = path.lstat()
            result[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return result


def findings(lines):
    return [line for line in lines[:-1] if line.startswith('FAIL ')]


class CopyrightFooterShapesTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('npp_copyright_footer_shapes', SCRIPT)
        if spec is None or spec.loader is None:
            self.fail('could not load copyright footer diagnostic')
        self.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(self.tool)

    def cli(self, *args):
        with TemporaryDirectory() as cwd:
            return subprocess.run(
                [sys.executable, '-B', str(SCRIPT), *args], cwd=cwd,
                capture_output=True, text=True, timeout=10,
            )

    def run_main(self, status, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            actual = self.tool.main([])
        self.assertEqual(actual, status)
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual(stderr.getvalue(), '')
        return lines

    def adjusted_ownership(self, *, refuse=None, accept_shop=None):
        parse_page = self.tool.research.parse_page
        indices = {footer: i for i, footer in enumerate(self.tool.FOOTERS)}

        def parse(url, retrieved, markup):
            page = parse_page(url, retrieved, markup)
            footer = markup.partition('<footer>')[2].partition('</footer>')[0]
            i = indices[footer]
            if i == refuse:
                page.ownership = ['© Fresh Market Co.']
            elif i < 13 or i == accept_shop:
                page.ownership = ['© Miners Orchards.']
            return page

        return patch.object(self.tool.research, 'parse_page', side_effect=parse)

    def test_c1_full_pass(self):
        # A successful classifier sweep must not inherit the baseline's failure status.
        with self.adjusted_ownership():
            lines = self.run_main(0, PASS)
        reasons = ['official'] * 13 + [REFUSED] * 2
        self.assertEqual(lines[:-1], [f'footer {i} reason={r}' for i, r in enumerate(reasons)])

    def test_c2_findings_trailer(self):
        # A stop-at-first-finding or a trailer driven by the last row loses a failure.
        with self.adjusted_ownership(refuse=3, accept_shop=13):
            lines = self.run_main(1, FAIL)
        self.assertEqual(findings(lines), ['FAIL footer-refused 3', 'FAIL shop-accepted 13'])
        self.assertEqual(lines[-2], f'footer 14 reason={REFUSED}')

    def test_c2_1_footer_refused(self):
        # A non-official maker result must produce one finding at the affected index.
        with self.adjusted_ownership(refuse=6):
            lines = self.run_main(1, FAIL)
        self.assertEqual(findings(lines), ['FAIL footer-refused 6'])
        self.assertIn(f'footer 6 reason={REFUSED}', lines)

    def test_c2_2_shop_accepted(self):
        # Treating every official result as success would miss an accepted shop control.
        with self.adjusted_ownership(accept_shop=14):
            lines = self.run_main(1, FAIL)
        self.assertEqual(findings(lines), ['FAIL shop-accepted 14'])
        self.assertIn('footer 14 reason=official', lines)

    def test_c2_3_check_error(self):
        # Each throwing repo check must set failure, without exposing exception text.
        for name in ('parse_page', '_markers', '_own_site'):
            with self.subTest(function=name):
                with self.adjusted_ownership():
                    original = getattr(self.tool.research, name)
                    error = RuntimeError('synthetic detail')
                    side_effect = [error] if name == '_markers' else self.fail_first(original, error)
                    with patch.object(self.tool.research, name, side_effect=side_effect):
                        lines = self.run_main(1, FAIL)
                self.assertEqual(findings(lines), ['FAIL check-error'])
                self.assertNotIn('synthetic detail', '\n'.join(lines))

    @staticmethod
    def fail_first(original, error):
        def call(*args):
            nonlocal error
            if error is not None:
                first, error = error, None
                raise first
            return original(*args)
        return call

    def test_c3_usage_exit_2(self):
        # Ignoring extra arguments (or argparse's default --help) violates the no-args CLI.
        for arg in ('extra', '--unknown', '-h', '--help', '--'):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout.splitlines(), [])
                self.assertEqual(result.stderr.splitlines()[-1:], [
                    f'npp_copyright_footer_shapes: error: unrecognized arguments: {arg}',
                ])

    def test_c4_read_only(self):
        # A cached asset or a saved report in either tree changes this metadata snapshot.
        before = snapshot()
        result = self.cli()
        self.assertEqual(snapshot(), before)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1:], [FAIL])

    def test_c5_output_shape(self):
        # Extra progress logs, blank lines, and unexpected finding forms break consumers.
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [FAIL])
        self.assertEqual(result.stderr, '')
        for line in lines[:-1]:
            self.assertRegex(line, r'\A(?:footer (?:[0-9]|1[0-4]) reason=[a-z-]+|'
                                   r'FAIL (?:footer-refused (?:[0-9]|1[0-2])|shop-accepted 1[34]|check-error))\Z')

    def test_c6_fixture(self):
        # Constant reason tables cannot respond to parsed ownership or the real owner predicate.
        with self.adjusted_ownership():
            self.run_main(0, PASS)
        with patch.object(self.tool.research, '_owner', return_value=False):
            lines = self.run_main(1, FAIL)
        self.assertEqual(findings(lines), [f'FAIL footer-refused {i}' for i in range(13)])

    def test_c7_live_pins(self):
        # Drift in S4 or the actual HTML fixtures changes the measured baseline, not the goal.
        lines = self.run_main(1, FAIL)
        expected = []
        for i, reason in enumerate(LIVE_REASONS):
            expected.append(f'footer {i} reason={reason}')
            if i in LIVE_REFUSALS:
                expected.append(f'FAIL footer-refused {i}')
        self.assertEqual(lines, [*expected, FAIL])
