"""Contract tests for the offline public-link drift guard."""

from contextlib import redirect_stderr, redirect_stdout
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch

from hass import content_model


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_public_link_check.py'
PASS = 'PASS npp_public_link_check'
FAIL = 'FAIL npp_public_link_check'


def snapshot():
    entries = {}
    for name in ('hass', 'storefront-mockup'):
        tree = ROOT / name
        for path in (tree, *tree.rglob('*')):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class PublicLinkCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = spec_from_file_location('npp_public_link_check', SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError('could not load npp_public_link_check')
        cls.check = module_from_spec(spec)
        original_path = sys.path[:]
        try:
            spec.loader.exec_module(cls.check)
        finally:
            sys.path[:] = original_path

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, '-B', str(SCRIPT.relative_to(ROOT)), *args],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )

    def check_main(self, expected_code, trailer):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.check.main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(code, expected_code)
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual(stderr.getvalue(), '')
        return lines

    def test_c1_full_pass(self):
        # A missing entry point or an unconditional failure breaks the CLI contract.
        run = self.cli()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # Drift alone must fail the run, even with no forbidden link accepted.
        validate = content_model._https

        def changed(problems, where, value):
            validate(problems, where, value)
            if value == 'https://cedarrow.com/honey':
                problems.append('synthetic finding')

        with patch.object(content_model, '_https', side_effect=changed):
            lines = self.check_main(1, FAIL)
        self.assertEqual(lines[:2], ['case 0 problems=1 why=None', 'FAIL link-changed 0'])
        self.assertEqual([line for line in lines if line.startswith('FAIL ')],
                         ['FAIL link-changed 0', FAIL])

    def test_c2_1_private_link_allowed(self):
        # Losing the numeric-host rule affects several cases, but a rejected
        # dotless host should only be reported as drift, not as accepted.
        with patch.object(content_model, 'NUMBER_LABEL_RE', re.compile(r'(?!x)x')):
            lines = self.check_main(1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')], [
            'FAIL private-link-allowed 3', 'FAIL link-changed 3',
            'FAIL link-changed 4',
            'FAIL private-link-allowed 5', 'FAIL link-changed 5',
        ])

    def test_c2_2_link_changed(self):
        # The reason can change even while validation still refuses the link.
        with patch.object(content_model, 'HOST_RE', re.compile(r'.+')):
            lines = self.check_main(1, FAIL)
        self.assertEqual(lines[-7:], [
            'case 12 problems=0 why=None',
            'FAIL private-link-allowed 12', 'FAIL link-changed 12',
            'case 13 problems=1 why=None', 'FAIL link-changed 13',
            'case 14 problems=1 why=None', FAIL,
        ])

    def test_c2_3_check_error(self):
        # A failure in either repo call must stop the run without echoing details.
        for name in ('_https', '_not_public'):
            with self.subTest(name=name):
                with patch.object(content_model, name,
                                  side_effect=RuntimeError('synthetic detail')) as call:
                    lines = self.check_main(1, FAIL)
                self.assertEqual(lines, ['FAIL check-error', FAIL])
                call.assert_called_once()

    def test_c3_usage_exit_2(self):
        # Ignoring the argument vector or enabling help would bypass this contract.
        for arg in ('extra', '--unknown', '-h', '--help', '--'):
            with self.subTest(arg=arg):
                run = self.cli(arg)
                self.assertEqual(run.returncode, 2)
                self.assertEqual(run.stdout, '')
                self.assertEqual(run.stderr.splitlines()[-1],
                                 f'{SCRIPT.name}: error: unrecognized arguments: {arg}')

    def test_c4_read_only(self):
        # A report file or a rewrite in either tree changes this snapshot.
        before = snapshot()
        run = self.cli()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug or progress output on either stream is not part of the protocol.
        run = self.cli()
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stderr, '')
        lines = run.stdout.splitlines()
        self.assertEqual(lines[-1:], [PASS])
        self.assertTrue(lines[:-1])
        for line in lines[:-1]:
            self.assertIsNotNone(re.fullmatch(r"case \d+ problems=\d+ why=(?:None|'[^']*')", line), line)

    def test_c6_fixture(self):
        # The permissive host pattern must produce findings, not a canned PASS.
        with patch.object(content_model, 'HOST_RE', re.compile(r'.+')):
            lines = self.check_main(1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')], [
            'FAIL private-link-allowed 12', 'FAIL link-changed 12', 'FAIL link-changed 13',
        ])

    def test_c7_live_pins(self):
        # A validator reason, the problem count or fixture order can drift.
        lines = self.check_main(0, PASS)
        self.assertEqual(lines[:-1], [
            "case 0 problems=0 why=None",
            "case 1 problems=0 why=None",
            "case 2 problems=1 why=None",
            "case 3 problems=1 why='IP address'",
            "case 4 problems=1 why='IP address'",
            "case 5 problems=1 why='IP address'",
            "case 6 problems=1 why='IP address'",
            "case 7 problems=1 why='port'",
            "case 8 problems=1 why='user or password'",
            "case 9 problems=1 why='private name'",
            "case 10 problems=1 why='backslash'",
            "case 11 problems=1 why='host has no dot'",
            "case 12 problems=1 why='host characters'",
            "case 13 problems=1 why='host characters'",
            "case 14 problems=1 why=None",
        ])


if __name__ == '__main__':
    unittest.main()
