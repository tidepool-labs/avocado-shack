"""Offline CLI contract for the polish label-word drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_polish_label_words.py'
PASS = 'PASS npp_polish_label_words'
FAIL = 'FAIL npp_polish_label_words'
LIVE_LINES = [
    'case 0 changed=no',
    'case 1 changed=yes',
    'case 2 changed=no',
    'case 3 changed=no',
    'case 4 changed=no',
    'case 5 changed=yes',
    'case 6 changed=no',
    'case 7 removed=no',
    'case 8 removed=yes',
    'case 9 removed=no',
    'case 10 removed=yes',
    'case 11 removed=yes',
    'case 12 removed=no',
]


def snapshot():
    entries = {}
    for name in ('hass', 'storefront-mockup'):
        tree = ROOT / name
        for path in (tree, *tree.rglob('*')):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class PolishLabelWordsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError(f'Cannot load {SCRIPT.name}')
        cls.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(cls.tool)

    def invoke(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args],
                              cwd=ROOT.parent, capture_output=True, text=True, timeout=10)

    def run_main(self, status, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(code, status, stderr.getvalue())
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual(stderr.getvalue(), '')
        return lines[:-1]

    def test_c1_full_pass(self):
        # A CLI that forgets to exit with its result can misreport success or failure.
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # Reporting only the first finding, or batching findings at the end, loses case order.
        with patch.object(self.tool.photo_polish, 'WORD_MIN', -1.0):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, [
            LIVE_LINES[0], 'case 1 changed=no',
            'FAIL label-change-passed 1', 'FAIL label-changed 1',
            *LIVE_LINES[2:8], 'case 8 removed=no',
            'FAIL label-change-passed 8', 'FAIL label-changed 8',
            *LIVE_LINES[9:],
        ])

    def test_c2_1_label_change_passed(self):
        # A weakened blank-spot threshold must flag both safety misses, not just drift.
        with patch.object(self.tool.photo_polish, 'WORD_MIN', -1.0):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], [
            'FAIL label-change-passed 1', 'FAIL label-changed 1',
            'FAIL label-change-passed 8', 'FAIL label-changed 8',
        ])

    def test_c2_2_label_changed(self):
        # Checking only MUST_FLAG would miss a formerly tolerated OCR slip becoming a finding.
        with patch.object(self.tool.photo_polish, 'KNOWN_RATIO', 1.01):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, [*LIVE_LINES[:4], 'case 4 changed=yes',
                                 'FAIL label-changed 4', *LIVE_LINES[5:]])

    def test_c2_3_check_error(self):
        # A failing predicate must neither expose exception details nor continue to later cases.
        polish = self.tool.photo_polish
        for name, other, preceding in (('text_changed', 'text_removed', 0),
                                       ('text_removed', 'text_changed', 7)):
            with self.subTest(name=name):
                with (patch.object(polish, name, side_effect=RuntimeError('fixture detail')) as broken,
                      patch.object(polish, other, wraps=getattr(polish, other)) as working):
                    lines = self.run_main(1, FAIL)
                self.assertEqual(lines, [*LIVE_LINES[:preceding], 'FAIL check-error'])
                broken.assert_called_once()
                self.assertEqual(working.call_count, preceding)

    def test_c3_usage_exit_2(self):
        # Extra arguments (including argparse's implicit help) must not run the check.
        for arg in ('extra', '--unknown', '-h', '--help', '--'):
            with self.subTest(arg=arg):
                result = self.invoke(arg)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.startswith('usage: '), result.stderr)
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f'{SCRIPT.name}: error: unrecognized arguments: {arg}')

    def test_c4_read_only(self):
        # A cached report or a rewritten input would change names, sizes, or mtimes.
        before = snapshot()
        result = self.invoke()
        self.assertEqual(snapshot(), before)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c5_output_shape(self):
        # Debug banners or warnings must not pollute the successful CLI output.
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [PASS])
        for line in lines[:-1]:
            self.assertRegex(line, r'^case [0-9]+ (changed|removed)=(yes|no)$')

    def test_c6_fixture(self):
        # A ratio change trips only the fuzzy match, not the exact match or other cases.
        with patch.object(self.tool.photo_polish, 'KNOWN_RATIO', 1.01):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], [
            'FAIL label-changed 4',
        ])

    def test_c7_live_pins(self):
        # A copied/hardcoded rule or misrouted fixture must not stand in for the real verdicts.
        polish = self.tool.photo_polish
        with (patch.object(polish, 'text_changed', wraps=polish.text_changed) as changed,
              patch.object(polish, 'text_removed', wraps=polish.text_removed) as removed):
            self.assertEqual(self.run_main(0, PASS), LIVE_LINES)
        self.assertEqual(changed.call_args_list,
                         [call(a, b) for kind, a, b in self.tool.CASES if kind == 'changed'])
        self.assertEqual(removed.call_args_list,
                         [call(a, b) for kind, a, b in self.tool.CASES if kind == 'removed'])


if __name__ == '__main__':
    unittest.main()
