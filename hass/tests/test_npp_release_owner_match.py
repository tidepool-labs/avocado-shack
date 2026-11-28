"""Contract tests for the offline release owner matcher check."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import call, patch

from hass import conversation, publish_live


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_release_owner_match.py'
PASS = 'PASS npp_release_owner_match'
FAIL = 'FAIL npp_release_owner_match'
LIVE_LINES = [
    'case 0 owner=yes',
    'case 1 owner=yes',
    'case 2 owner=yes',
    'case 3 owner=yes',
    'case 4 owner=yes',
    'case 5 owner=yes',
    'case 6 owner=no',
    'case 7 owner=no',
    'case 8 owner=no',
    'case 9 owner=yes',
]


def invoke(*args):
    return subprocess.run(
        [sys.executable, '-B', str(SCRIPT), *args], cwd=ROOT,
        capture_output=True, text=True, timeout=15,
    )


def snapshot():
    entries = {}
    for tree in (ROOT / 'hass', ROOT / 'storefront-mockup'):
        for path in (tree, *tree.rglob('*')):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class ReleaseOwnerMatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('npp_release_owner_match', SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError('could not load release owner match script')
        cls.script = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(cls.script)

    def run_main(self, status, trailer):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.script.main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(code, status)
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual(stderr.getvalue(), '')
        return lines[:-1]

    def test_c1_full_pass(self):
        # A CLI entry point that drops main's result or trailer breaks the shell contract.
        result = invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(result.stderr, '')

    def test_c2_findings_trailer(self):
        # Premature exit or batching findings at the end loses the per-case ordering.
        with patch.object(publish_live, 'DIGIT_RUN', re.compile(r'\d+')):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, [
            'case 0 owner=no', 'FAIL owner-missed 0', 'FAIL owner-changed 0',
            'case 1 owner=no', 'FAIL owner-missed 1', 'FAIL owner-changed 1',
            'case 2 owner=no', 'FAIL owner-missed 2', 'FAIL owner-changed 2',
            *LIVE_LINES[3:],
        ])

    def test_c2_1_owner_missed(self):
        # Splitting digit runs must still trigger the independent must-find guard.
        with patch.object(publish_live, 'DIGIT_RUN', re.compile(r'\d+')):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], [
            'FAIL owner-missed 0', 'FAIL owner-changed 0',
            'FAIL owner-missed 1', 'FAIL owner-changed 1',
            'FAIL owner-missed 2', 'FAIL owner-changed 2',
        ])

    def test_c2_2_owner_changed(self):
        # A tool that checks only must-find cases could omit the drift finding.
        with patch.object(conversation, 'sender_key', return_value=None):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL owner-changed ')], [
            'FAIL owner-changed 0', 'FAIL owner-changed 1', 'FAIL owner-changed 2',
            'FAIL owner-changed 3', 'FAIL owner-changed 4', 'FAIL owner-changed 9',
        ])

    def test_c2_3_check_error(self):
        # A second-case error must not leak its diagnostic or let later cases run.
        derive = publish_live.owner_needles

        def fail_on_second(forbidden):
            if needs.call_count == 2:
                raise RuntimeError('synthetic exception detail')
            return derive(forbidden)

        with patch.object(publish_live, 'owner_needles', side_effect=fail_on_second) as needs:
            with patch.object(publish_live, 'owner_found', wraps=publish_live.owner_found) as find:
                lines = self.run_main(1, FAIL)
        self.assertEqual(lines, ['case 0 owner=yes', 'FAIL check-error'])
        self.assertEqual(needs.call_count, 2)
        self.assertEqual(find.call_count, 1)

    def test_c3_usage_exit_2(self):
        # Default help, ignored extras or a lone option terminator could silently succeed.
        for arg in ('unexpected', '--unknown', '--help', '-h', '--'):
            with self.subTest(arg=arg):
                result = invoke(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.splitlines()[-1].startswith(f'{SCRIPT.name}: error: '))

    def test_c4_read_only(self):
        # A future diagnostic could save a report or touch an existing input.
        before = snapshot()
        result = invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(result.stderr, '')
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug prints (including fixture values) must not escape either stream.
        allowed = re.compile(
            r'^(?:case \d+ owner=(?:yes|no)|FAIL owner-(?:missed|changed) \d+|FAIL check-error)\Z'
        )
        for disable_keys in (False, True):
            with self.subTest(disable_keys=disable_keys):
                if disable_keys:
                    with patch.object(conversation, 'sender_key', return_value=None):
                        lines = self.run_main(1, FAIL)
                else:
                    lines = self.run_main(0, PASS)
                for line in lines:
                    self.assertRegex(line, allowed)

    def test_c6_fixture(self):
        # Removing sender normalization must miss both decorated numbers and the cased address.
        with patch.object(conversation, 'sender_key', return_value=None):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], [
            'FAIL owner-missed 0', 'FAIL owner-changed 0',
            'FAIL owner-missed 1', 'FAIL owner-changed 1',
            'FAIL owner-missed 2', 'FAIL owner-changed 2',
            'FAIL owner-missed 3', 'FAIL owner-changed 3',
            'FAIL owner-missed 4', 'FAIL owner-changed 4',
            'FAIL owner-missed 9', 'FAIL owner-changed 9',
        ])

    def test_c7_live_pins(self):
        # Literal answers could mask matcher drift; forward both calls to the real functions.
        derive = publish_live.owner_needles
        with patch.object(publish_live, 'owner_needles', wraps=derive) as needs:
            with patch.object(publish_live, 'owner_found', wraps=publish_live.owner_found) as find:
                lines = self.run_main(0, PASS)
        self.assertEqual(lines, LIVE_LINES)
        self.assertEqual(needs.call_args_list, [call(self.script.FORBIDDEN)] * len(LIVE_LINES))
        needles = derive(self.script.FORBIDDEN)
        self.assertEqual(find.call_args_list, [
            call(text.encode('latin1'), needles) for text in self.script.CASES
        ])
