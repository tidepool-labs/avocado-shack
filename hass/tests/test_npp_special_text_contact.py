"""Offline CLI contract for the special-text drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import DEFAULT, call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_special_text_contact.py'
PASS = 'PASS npp_special_text_contact'
FAIL = 'FAIL npp_special_text_contact'
NEVER_MATCH = re.compile(r'(?!x)x')
PINS = [
    "case 0 problem=None",
    "case 1 problem=None",
    "case 2 problem='may not contain a price; put it in the deal line'",
    "case 3 problem='may not contain a phone number'",
    "case 4 problem='may not contain a web address'",
    "case 5 problem='may not contain a web address'",
    "case 6 problem=\"contains forbidden text '<'\"",
    "case 7 problem='must be one line'",
    "case 8 problem='must not be empty or start or end with a space'",
    "case 9 problem='needs at least 3 letters'",
    "case 10 problem='contains invisible or control character U+200B'",
    "case 11 problem=None",
    "case 12 problem='must be a string'",
]


def snapshot():
    entries = {}
    for tree in (ROOT / 'hass', ROOT / 'storefront-mockup'):
        for path in (tree, *tree.rglob('*')):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class SpecialTextContactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('npp_special_text_contact', SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError('cannot load the special-text check')
        cls.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(cls.tool)
        cls.model = cls.tool.content_model

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, '-B', str(SCRIPT), *args], cwd=SCRIPT.parent,
            capture_output=True, text=True, timeout=10,
        )

    def run_main(self, status, trailer):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = self.tool.main([])
        lines = out.getvalue().splitlines()
        self.assertEqual(result, status)
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual(err.getvalue(), '')
        return lines[:-1]

    def test_c1_full_pass(self):
        # A missing repo bootstrap or a wrong __main__ exit breaks the real CLI.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # A first-finding exit or deferred reporting loses case order or findings.
        with (
            patch.object(self.model, 'SPECIAL_PHONE_RE', NEVER_MATCH),
            patch.object(self.model, 'SPECIAL_FORBIDDEN', ()),
        ):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, [
            *PINS[:3], 'case 3 problem=None',
            'FAIL contact-in-special 3', 'FAIL special-changed 3', *PINS[4:6],
            'case 6 problem=None', 'FAIL contact-in-special 6', 'FAIL special-changed 6',
            *PINS[7:],
        ])

    def test_c2_1_contact_in_special(self):
        # Dropping the phone rule must report acceptance as well as changed text.
        with patch.object(self.model, 'SPECIAL_PHONE_RE', NEVER_MATCH):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], [
            'FAIL contact-in-special 3', 'FAIL special-changed 3',
        ])

    def test_c2_2_special_changed(self):
        # The markup mutation changes the pin; drift also matters if it still refuses.
        with patch.object(self.model, 'SPECIAL_FORBIDDEN', ()):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL special-changed')], [
            'FAIL special-changed 6',
        ])
        with patch.object(self.model, 'SPECIAL_FORBIDDEN', ('<b>',)):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, [
            *PINS[:6], 'case 6 problem="contains forbidden text \'<b>\'"',
            'FAIL special-changed 6', *PINS[7:],
        ])

    def test_c2_3_check_error(self):
        # A later exception must not leak text, retry, or check another case.
        with patch.object(self.model, 'special_text_problem',
                          wraps=self.model.special_text_problem,
                          side_effect=[DEFAULT, RuntimeError('synthetic detail')]) as validate:
            self.assertEqual(self.run_main(1, FAIL), [PINS[0], 'FAIL check-error'])
        self.assertEqual(validate.call_args_list, [
            call('Honey week', deal=False), call('Two jars for $15', deal=True),
        ])

    def test_c3_usage_exit_2(self):
        # A permissive parser (including default help) accepts a forbidden argument.
        for argument in ('extra', '--unknown', '--help', '-h', '--'):
            with self.subTest(argument=argument):
                result = self.cli(argument)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertIn('error: unrecognized arguments:', result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # A report artifact or a rewrite of a source file changes the snapshot.
        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # An extra banner, warning, blank line, or malformed case line violates the protocol.
        result = self.cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, '')
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [PASS])
        self.assertEqual(len(lines[:-1]), 13)
        for i, line in enumerate(lines[:-1]):
            self.assertRegex(line, rf'''^case {i} problem=(?:None|'[^']*'|"[^"]*")$''')

    def test_c6_fixture(self):
        # Removing the markup table must affect just the markup fixture.
        with patch.object(self.model, 'SPECIAL_FORBIDDEN', ()):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, [
            *PINS[:6], 'case 6 problem=None',
            'FAIL contact-in-special 6', 'FAIL special-changed 6', *PINS[7:],
        ])

    def test_c7_live_pins(self):
        # Pin every repr in order; replaying canned output must not pass this test.
        with patch.object(self.model, 'special_text_problem',
                          wraps=self.model.special_text_problem) as validate:
            self.assertEqual(self.run_main(0, PASS), PINS)
        self.assertEqual(validate.call_args_list, [
            call(value, deal=deal) for value, deal in self.tool.CASES
        ])
