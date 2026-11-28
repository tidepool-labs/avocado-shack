"""Offline CLI contract for the NPP photo alt-text drift check."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import call, patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_photo_alt_problem.py'
PASS = 'PASS npp_photo_alt_problem'
FAIL = 'FAIL npp_photo_alt_problem'
PINS = [
    'case 0 refused=no',
    'case 1 refused=yes',
    'case 2 refused=yes',
    'case 3 refused=yes',
    'case 4 refused=yes',
    'case 5 refused=yes',
    'case 6 refused=yes',
    'case 7 refused=yes',
    'case 8 refused=yes',
    'case 9 refused=yes',
    'case 10 refused=no',
]


def invoke(*args):
    return subprocess.run(
        [sys.executable, '-B', str(SCRIPT), *args], cwd=ROOT,
        capture_output=True, text=True, timeout=10,
    )


def snapshot():
    entries = {}
    for name in ('hass', 'storefront-mockup'):
        tree = ROOT / name
        for path in (tree, *tree.rglob('*')):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class NppPhotoAltProblemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('npp_photo_alt_problem', SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError(f'Cannot load {SCRIPT.name}')
        cls.tool = importlib.util.module_from_spec(spec)
        # Restore sys.path after the standalone script's import bootstrap.
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(cls.tool)

    def run_check(self, code, trailer):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(self.tool.main([]), code)
        self.assertEqual(err.getvalue(), '')
        lines = out.getvalue().splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def test_c1_full_pass(self):
        # A short-circuited pass or wrong digest must not bypass a real call for any fixture.
        photos = self.tool.photos
        with patch.object(photos, '_alt_problem', wraps=photos._alt_problem) as check:
            self.run_check(0, PASS)
        self.assertEqual(check.call_args_list, [
            call(alt, 'c0ffee12ab34' + '0' * 52) for alt in self.tool.CASES
        ])

    def test_c2_findings_trailer(self):
        # The first finding must not stop later cases, and findings belong beside their cases.
        with patch.object(self.tool.photos, '_IMAGE_EXT', ()), patch.object(
                self.tool.photos, '_PLACEHOLDERS', set()):
            self.assertEqual(self.run_check(1, FAIL), [
                *PINS[:1], 'case 1 refused=no', 'FAIL bad-alt-kept 1', 'FAIL alt-changed 1',
                *PINS[2:9], 'case 9 refused=no', 'FAIL bad-alt-kept 9', 'FAIL alt-changed 9',
                *PINS[10:],
            ])

    def test_c2_1_bad_alt_kept(self):
        # Removing filename detection must trip both distinct findings for the filename alone.
        with patch.object(self.tool.photos, '_IMAGE_EXT', ()):
            lines = self.run_check(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL')], [
            'FAIL bad-alt-kept 1', 'FAIL alt-changed 1',
        ])

    def test_c2_2_alt_changed(self):
        # Do not let the safety finding substitute for the pin comparison.
        with patch.object(self.tool.photos, '_PLACEHOLDERS', set()):
            lines = self.run_check(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL alt-changed')], [
            'FAIL alt-changed 9',
        ])

    def test_c2_3_check_error(self):
        # A failure after one real check must not leak its text or continue checking cases.
        real_check = self.tool.photos._alt_problem

        def fail_on_second(alt, sha):
            if alt == 'crate-shot.jpg':
                raise RuntimeError('synthetic error detail')
            return real_check(alt, sha)

        with patch.object(self.tool.photos, '_alt_problem', side_effect=fail_on_second) as check:
            self.assertEqual(self.run_check(1, FAIL), ['case 0 refused=no', 'FAIL check-error'])
        self.assertEqual(check.call_count, 2)

    def test_c3_usage_exit_2(self):
        # Extra inputs must not silently run the checker or print normal output.
        for arg in ('fixture', '--unexpected', '--help', '--'):
            with self.subTest(arg=arg):
                result = invoke(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')  # No last stdout line on a usage error.
                self.assertTrue(result.stderr.startswith('usage: '))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f'{SCRIPT.name}: error: unrecognized arguments: {arg}')

    def test_c4_read_only(self):
        # Catch an accidental cache, generated report, or rewrite in either repo tree.
        before = snapshot()
        result = invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [*PINS, PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Successful CLI output must contain only the pinned lines and trailer, without debug text.
        result = invoke()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '\n'.join([*PINS, PASS]) + '\n')
        self.assertEqual(result.stderr, '')

    def test_c6_fixture(self):
        # Removing the placeholder set must expose the bare todo fixture, not the regex cases.
        with patch.object(self.tool.photos, '_PLACEHOLDERS', set()):
            lines = self.run_check(1, FAIL)
        self.assertIn('case 9 refused=no', lines)
        self.assertEqual([line for line in lines if line.startswith('FAIL')], [
            'FAIL bad-alt-kept 9', 'FAIL alt-changed 9',
        ])

    def test_c7_live_pins(self):
        # A change in any live refusal, including an over-refusal, must break the unpatched pins.
        self.assertEqual(self.run_check(0, PASS), PINS)
