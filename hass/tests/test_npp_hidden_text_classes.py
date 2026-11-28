"""Offline behavioral tests for the S4 hidden-text diagnostic."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass import maker_site
from hass.npp import research


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_hidden_text_classes.py'
SPEC = importlib.util.spec_from_file_location('npp_hidden_text_classes', SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
PASS = 'PASS npp_hidden_text_classes'
FAIL = 'FAIL npp_hidden_text_classes'
BASE_LEAKS = (26, 27, 28, 29)


def mark_missing_forms_hidden(parser, tag, attrs):
    values = dict(attrs)
    classes = (values.get('class') or '').split()
    style = (values.get('style') or '').replace(' ', '').lower()
    if ({'screen-reader-text', 'invisible'}.intersection(classes)
            or 'visibility:collapse' in style or 'font-size:0' in style):
        attrs = [*attrs, ('hidden', None)]
    ORIGINAL_STARTTAG(parser, tag, attrs)


ORIGINAL_STARTTAG = research._Visible.handle_starttag


def findings(lines):
    return [line for line in lines[:-1] if line.startswith('FAIL ')]


def leak_findings(indices):
    return [f'FAIL hidden-text-read {index}' for index in indices]


def snapshot():
    state = {}
    for directory in ('hass', 'storefront-mockup'):
        tree = ROOT / directory
        for path in (tree, *tree.rglob('*')):
            stat = path.lstat()
            state[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return state


class HiddenTextClassesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def invoke(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = CHECK.main([])
        self.assertEqual(stderr.getvalue(), '')
        return code, stdout.getvalue().splitlines()

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, '-B', str(SCRIPT), *args], cwd=self.tmp,
            capture_output=True, text=True, timeout=10,
        )

    def assert_result(self, code, lines, expected_code, trailer):
        self.assertEqual(code, expected_code)
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)

    def repaired(self):
        return patch.object(research._Visible, 'handle_starttag', mark_missing_forms_hidden)

    def test_c1_full_pass(self):
        # A checker that treats the informational opacity loss as a failure never passes.
        with self.repaired():
            code, lines = self.invoke()
        self.assert_result(code, lines, 0, PASS)
        self.assertEqual(findings(lines), [])
        self.assertIn('opacity-partial kept=no', lines)

    def test_c2_findings_trailer(self):
        # A CLI that reports findings but neglects to propagate main's failure exits zero.
        result = self.cli()
        lines = result.stdout.splitlines()
        self.assert_result(result.returncode, lines, 1, FAIL)
        self.assertTrue(findings(lines))

    def test_c2_1_hidden_text_read(self):
        # Body-only or whole-entry matching misses an embedded quote in another channel.
        parse = research.parse_page
        cases = (
            ('<p hidden>Hidden Founded Line</p>', 'blocks'),
            ('<p aria-hidden="true">Hidden Founded Line</p>', 'ownership'),
            ('<p aria-hidden="TRUE">Hidden Founded Line</p>', 'titles'),
        )

        def inject(url, retrieved, markup):
            page = parse(url, retrieved, markup)
            for fragment, channel in cases:
                if fragment in markup:
                    getattr(page, channel).extend(['A Hidden Founded Line here.'] * 2)
            return page

        with self.repaired(), patch.object(research, 'parse_page', side_effect=inject):
            code, lines = self.invoke()
        self.assert_result(code, lines, 1, FAIL)
        self.assertEqual(findings(lines), leak_findings((0, 1, 2)))
        for index in range(3):
            self.assertIn(f'hidden {index} leak=yes', lines)

    def test_c2_2_visible_text_lost(self):
        # Checking only hidden fragments, or accepting a title as a body block, misses this loss.
        parse = research.parse_page

        def move_to_title(url, retrieved, markup):
            if markup == '<html><body><p>Shown line</p></body></html>':
                markup = '<html><head><title>Shown line</title></head><body></body></html>'
            return parse(url, retrieved, markup)

        with self.repaired(), patch.object(research, 'parse_page', side_effect=move_to_title):
            code, lines = self.invoke()
        self.assert_result(code, lines, 1, FAIL)
        self.assertEqual(findings(lines), ['FAIL visible-text-lost 0'])
        self.assertIn('visible 0 kept=no', lines)

    def test_c2_3_check_error(self):
        # Parse errors must neither leak exception text nor stop the remaining checks.
        parse = research.parse_page

        def reject_three(url, retrieved, markup):
            if any(fragment in markup for fragment in (
                '<p hidden>Hidden Founded Line</p>', '<p>Shown line</p></body>',
                '<p style="opacity:0.5">Shown line</p>',
            )):
                raise ValueError('Synthetic diagnostic detail')
            return parse(url, retrieved, markup)

        with self.repaired(), patch.object(research, 'parse_page', side_effect=reject_three):
            code, lines = self.invoke()
        self.assert_result(code, lines, 1, FAIL)
        self.assertEqual(findings(lines), ['FAIL check-error'] * 3)
        self.assertNotIn('Synthetic diagnostic detail', '\n'.join(lines))
        self.assertIn('hidden 1 leak=no', lines)
        self.assertIn('visible 9 kept=yes', lines)

    def test_c3_usage_exit_2(self):
        # Ignoring argv or leaving argparse's default help enabled violates the no-argument CLI.
        for arg in ('fixture.html', '--unknown', '-h', '--help', '--'):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.startswith('usage: '))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f'{SCRIPT.name}: error: unrecognized arguments: {arg}')

    def test_c4_read_only(self):
        # A cached extraction or in-place fixture write would alter checkout metadata.
        before = snapshot()
        result = self.cli()
        self.assertEqual(snapshot(), before)
        self.assert_result(result.returncode, result.stdout.splitlines(), 1, FAIL)

    def test_c5_output_shape(self):
        # Stray debug lines, stderr logging or duplicate observations break the CLI protocol.
        result = self.cli()
        lines = result.stdout.splitlines()
        self.assert_result(result.returncode, lines, 1, FAIL)
        self.assertEqual(result.stderr, '')
        shape = (r'hidden \d+ leak=(?:yes|no)|visible \d+ kept=(?:yes|no)|'
                 r'opacity-partial kept=(?:yes|no)|'
                 r'FAIL (?:hidden-text-read \d+|visible-text-lost \d+|check-error)')
        for line in lines[:-1]:
            self.assertIsNotNone(re.fullmatch(shape, line), line)
        self.assertEqual([int(line.split()[1]) for line in lines if line.startswith('hidden ')],
                         list(range(31)))
        self.assertEqual([int(line.split()[1]) for line in lines if line.startswith('visible ')],
                         list(range(10)))
        self.assertEqual(sum(line.startswith('opacity-partial ') for line in lines), 1)

    def test_c6_fixture(self):
        # Hard-coded baseline outcomes ignore changes to the parser and its skip tags.
        with self.repaired():
            code, lines = self.invoke()
        self.assert_result(code, lines, 0, PASS)
        self.assertEqual([line for line in lines if line.startswith('hidden ')],
                         [f'hidden {index} leak=no' for index in range(31)])

        with patch.object(maker_site, 'SKIP_TAGS', frozenset()):
            code, lines = self.invoke()
        self.assert_result(code, lines, 1, FAIL)
        self.assertEqual(findings(lines), leak_findings((15, 16, 17, 18, 20, *BASE_LEAKS)))
        for index in (13, 14, 19, 25):
            self.assertIn(f'hidden {index} leak=no', lines)

    def test_c7_live_pins(self):
        # Detect drift in the unchanged parser's exact findings and visible controls.
        code, lines = self.invoke()
        self.assert_result(code, lines, 1, FAIL)
        expected = []
        for index in range(31):
            leak = index in BASE_LEAKS
            expected.append(f'hidden {index} leak={"yes" if leak else "no"}')
            if leak:
                expected.extend(leak_findings((index,)))
        expected.extend(f'visible {index} kept=yes' for index in range(10))
        expected.extend(('opacity-partial kept=no', FAIL))
        self.assertEqual(lines, expected)
