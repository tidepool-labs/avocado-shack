"""Behavioural checks for the offline '?' retry guard."""

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
SCRIPT = ROOT / 'scripts/hass/npp_retry_question_mark.py'
PASS = 'PASS npp_retry_question_mark'
FAIL = 'FAIL npp_retry_question_mark'


def snapshot():
    entries = {}
    for tree in (ROOT / 'hass', ROOT / 'storefront-mockup'):
        for path in (tree, *tree.rglob('*')):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class RetryQuestionMarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('npp_retry_question_mark', SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def cli(self, *args):
        with TemporaryDirectory() as cwd:
            return subprocess.run(
                [sys.executable, '-B', str(SCRIPT), *args], cwd=cwd,
                capture_output=True, text=True, timeout=10,
            )

    def run_main(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        self.assertEqual(stderr.getvalue(), '')
        return code, stdout.getvalue().splitlines()

    def override_retries(self, overrides):
        jobs = self.tool.job.Jobs
        real_retry = jobs.needs_retry

        def needs_retry(instance, row):
            observed = real_retry(instance, row)
            return overrides.get(row['job_id'], observed)

        with patch.object(jobs, 'needs_retry', needs_retry):
            return self.run_main()

    def assert_findings(self, result, expected):
        code, lines = result
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1:], [FAIL])
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')], expected)

    def test_c1_full_pass(self):
        # The entry point must report success to both the operator and shell.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # Returning the last case's verdict would hide earlier failures.
        self.assert_findings(self.override_retries({'job0001': True, 'job0006': True}), [
            'FAIL retry-changed 1', 'FAIL retry-changed 6',
        ])

    def test_c2_1_retry_on_delivered(self):
        # A generic mismatch alone would hide the delivered-card risk.
        self.assert_findings(self.override_retries({'job0003': True}), [
            'FAIL retry-on-delivered 3', 'FAIL retry-changed 3',
        ])

    def test_c2_2_no_retry_after_render_failed(self):
        # A latest render failure must still be distinguished from ordinary drift.
        self.assert_findings(self.override_retries({'job0000': False, 'job0005': False}), [
            'FAIL no-retry-after-render-failed 0', 'FAIL retry-changed 0',
            'FAIL no-retry-after-render-failed 5', 'FAIL retry-changed 5',
        ])

    def test_c2_3_retry_changed(self):
        # Losing queued retries would evade both specialized findings.
        self.assert_findings(self.override_retries({'job0007': False}), ['FAIL retry-changed 7'])

    def test_c2_4_check_error(self):
        # A broken pin loader must not pass or leak the exception's contents.
        with patch.object(self.tool.hass.npp, 'assets', side_effect=RuntimeError('fixture detail')):
            code, lines = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(lines, ['FAIL check-error', FAIL])

    def test_c3_usage_exit_2(self):
        # Ignoring input or retaining argparse's implicit help bypasses the no-args rule.
        for arg in ('extra', '--unknown', '-h', '--help'):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')  # No last line for usage errors.
                self.assertTrue(result.stderr.startswith('usage: '))

    def test_c4_read_only(self):
        # Opening a disk database or writing media under either tree would leave a trace.
        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Keep debug chatter out of both the normal and findings output.
        result = self.cli()
        self.assertEqual(result.stderr, '')
        for code, lines, expected_code, trailer in (
            (result.returncode, result.stdout.splitlines(), 0, PASS),
            (*self.override_retries({'job0000': False, 'job0003': True}), 1, FAIL),
        ):
            with self.subTest(trailer=trailer):
                self.assertEqual(code, expected_code)
                self.assertEqual(lines[-1:], [trailer])
                for line in lines[:-1]:
                    self.assertRegex(line, r'^(?:case [0-9] retry=(?:yes|no)|FAIL (?:'
                                     r'retry-on-delivered [0-9]|no-retry-after-render-failed [0-9]|'
                                     r'retry-changed [0-9]|check-error))$')

    def test_c6_fixture(self):
        # Always retrying must expose every negative fixture, in case order.
        with patch.object(self.tool.job.Jobs, 'needs_retry', lambda _jobs, _row: True):
            result = self.run_main()
        self.assert_findings(result, [
            'FAIL retry-changed 1', 'FAIL retry-on-delivered 3', 'FAIL retry-changed 3',
            'FAIL retry-changed 4', 'FAIL retry-changed 6', 'FAIL retry-changed 8',
            'FAIL retry-changed 9',
        ])

    def test_c7_live_pins(self):
        # The real predicate must distinguish the latest segment and the current version.
        code, lines = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(lines, [
            'case 0 retry=yes', 'case 1 retry=no', 'case 2 retry=yes', 'case 3 retry=no',
            'case 4 retry=no', 'case 5 retry=yes', 'case 6 retry=no', 'case 7 retry=yes',
            'case 8 retry=no', 'case 9 retry=no', PASS,
        ])
