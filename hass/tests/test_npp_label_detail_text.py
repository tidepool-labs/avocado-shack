"""Offline contract tests for the NPP label-detail drift check."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_label_detail_text.py'
PASS = 'PASS npp_label_detail_text'
FAIL = 'FAIL npp_label_detail_text'
LIVE_LINES = (
    "case 0 text='Wildflower honey from the hills' claim=no",
    'case 1 text=None claim=no',
    'case 2 text=None claim=no',
    'case 3 text=None claim=no',
    'case 4 text=None claim=no',
    'case 5 text=None claim=no',
    'case 6 text=None claim=no',
    "case 7 text='Certified organic' claim=yes",
    'case 8 text=None claim=no',
    'case 9 text=None claim=no',
    'case 10 text=None claim=no',
    "case 11 text='Cold pressed' claim=yes",
)


def _cli(*args):
    return subprocess.run(
        [sys.executable, '-B', str(SCRIPT), *args], cwd=ROOT,
        capture_output=True, text=True, encoding='utf-8', timeout=10,
    )


def _snapshot():
    snapshot = {}
    for tree in ('hass', 'storefront-mockup'):
        root = ROOT / tree
        for path in (root, *root.rglob('*')):
            info = path.lstat()
            snapshot[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return snapshot


class NppLabelDetailTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('npp_label_detail_text', SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(cls.tool)

    def _main(self, code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.tool.main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(result, code)
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual(stderr.getvalue(), '')
        return lines[:-1]

    def _without_claim_terms(self):
        with patch.object(self.tool.label_reader, '_TERMS', ()):
            return self._main(1, FAIL)

    def test_c1_full_pass(self):
        # A successful CLI run can still regress by omitting the PASS trailer.
        result = _cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # An empty string is not None; truthiness must not hide an unsafe return.
        reader = self.tool.label_reader
        original = reader.detail_text
        with patch.object(reader, 'detail_text',
                          side_effect=lambda value, limit: '' if value == 12 else original(value, limit)):
            lines = self._main(1, FAIL)
        self.assertEqual(lines[10:13], [
            "case 10 text='' claim=no", 'FAIL unsafe-detail-kept 10', 'FAIL detail-changed 10',
        ])

    def test_c2_1_unsafe_detail_kept(self):
        # Whitespace normalization alone lets prohibited strings through.
        with patch.object(
            self.tool.label_reader, 'detail_text',
            lambda value, limit=400: ' '.join(value.split()) if isinstance(value, str) else None,
        ):
            lines = self._main(1, FAIL)
        unsafe_indices = (1, 2, 3, 4, 5, 6, 8, 9)
        self.assertEqual(
            [line for line in lines if line.startswith('FAIL ')],
            [finding for i in unsafe_indices for finding in (
                f'FAIL unsafe-detail-kept {i}', f'FAIL detail-changed {i}',
            )],
        )
        for i in unsafe_indices:
            position = lines.index(f'FAIL unsafe-detail-kept {i}')
            self.assertTrue(lines[position - 1].startswith(f'case {i} text='))
            self.assertEqual(lines[position + 1], f'FAIL detail-changed {i}')

    def test_c2_2_detail_changed(self):
        # Comparing text alone would miss drift in the claim suffix.
        lines = self._without_claim_terms()
        expected: list[str] = list(LIVE_LINES)
        for i in (11, 7):
            expected[i] = expected[i].removesuffix('yes') + 'no'
            expected.insert(i + 1, f'FAIL detail-changed {i}')
        self.assertEqual(lines, expected)

    def test_c2_3_check_error(self):
        # Don't disclose an exception or continue checking after one.
        reader = self.tool.label_reader
        original = reader.detail_text

        def fail_on_price(value, limit):
            if value == 'Only 4 dollars':
                raise RuntimeError('synthetic exception text')
            return original(value, limit)

        with patch.object(reader, 'detail_text', side_effect=fail_on_price) as detail_text:
            lines = self._main(1, FAIL)
        self.assertEqual(lines, [LIVE_LINES[0], 'FAIL check-error'])
        self.assertEqual(detail_text.call_count, 2)

    def test_c3_usage_exit_2(self):
        # Accidental help flags or permissive parsing violate the no-args CLI.
        for arg in ('unexpected', '--unknown', '--help', '-h', '--'):
            with self.subTest(arg=arg):
                result = _cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.startswith('usage: '))
                self.assertIn('error: unrecognized arguments:', result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # An accidental report write or a touched catalog changes the snapshot.
        before = _snapshot()
        result = _cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(_snapshot(), before)

    def test_c5_output_shape(self):
        # A debug banner, traceback, or malformed case line is not a receipt.
        result = _cli()
        lines = result.stdout.splitlines()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(lines[-1:], [PASS])
        self.assertEqual(len(lines), 13)
        for i, line in enumerate(lines[:-1]):
            self.assertRegex(line, rf"^case {i} text=(?:None|'.*') claim=(?:yes|no)$")

    def test_c6_fixture(self):
        # Removing claim terms should change only the two known claim cases.
        lines = self._without_claim_terms()
        self.assertEqual([line for line in lines if line.startswith('FAIL ')],
                         ['FAIL detail-changed 7', 'FAIL detail-changed 11'])

    def test_c7_live_pins(self):
        # A baseline parser or claim-list change breaks the independent pins.
        self.assertEqual(self._main(0, PASS), list(LIVE_LINES))


if __name__ == '__main__':
    unittest.main()
