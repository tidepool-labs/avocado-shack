"""Fixture-only checks for the writer word-grounding drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_writer_word_ground.py'
PASS = 'PASS npp_writer_word_ground'
FAIL = 'FAIL npp_writer_word_ground'
LIVE_LINES = [
    'case 0 bad=[]',
    "case 1 bad=['raw']",
    'case 2 bad=[]',
    "case 3 bad=['assertion: It has butter.']",
    "case 4 bad=['made', 'lavender', 'made with']",
    "case 5 bad=['hills']",
    "case 6 bad=['award']",
    "case 7 bad=['keep']",
    'case 8 bad=[]',
]
FUNCTION_WORD_FINDINGS = [
    'FAIL words-changed 2',
    'FAIL words-changed 4',
    'FAIL words-changed 5',
    'FAIL words-changed 7',
]


def snapshot():
    state = {}
    for name in ('hass', 'storefront-mockup'):
        tree = ROOT / name
        for path in (tree, *tree.rglob('*')):
            info = path.lstat()
            state[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return state


class WriterWordGroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('npp_writer_word_ground', SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError(f'Cannot load {SCRIPT.name}')
        cls.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(cls.tool)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, '-B', str(SCRIPT), *args],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )

    def run_main(self, status, trailer):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.tool.main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(result, status)
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual(stderr.getvalue(), '')
        return lines[:-1]

    def test_c1_full_pass(self):
        # Pin the real CLI status (including forwarding main's return value).
        result = self.cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # Multiple findings must stay next to their case, not in an end summary.
        with patch.object(self.tool.newitem, '_stem', lambda word: ''):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, [
            'case 0 bad=[]',
            'case 1 bad=[]',
            'FAIL unsaid-word-passed 1',
            'FAIL words-changed 1',
            "case 2 bad=['assertion: Spoon it onto warm']",
            'FAIL words-changed 2',
            "case 3 bad=['assertion: It has butter.']",
            "case 4 bad=['assertion: Spoon it onto toast,']",
            'FAIL words-changed 4',
            'case 5 bad=[]',
            'FAIL unsaid-word-passed 5',
            'FAIL words-changed 5',
            'case 6 bad=[]',
            'FAIL unsaid-word-passed 6',
            'FAIL words-changed 6',
            "case 7 bad=['assertion: Keep it warm.']",
            'FAIL words-changed 7',
            'case 8 bad=[]',
        ])

    def test_c2_1_unsaid_word_passed(self):
        # Exact pins alone would catch drift but fail to identify lost flags.
        with patch.object(self.tool.newitem, '_stem', lambda word: ''):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], [
            'FAIL unsaid-word-passed 1',
            'FAIL words-changed 1',
            'FAIL words-changed 2',
            'FAIL words-changed 4',
            'FAIL unsaid-word-passed 5',
            'FAIL words-changed 5',
            'FAIL unsaid-word-passed 6',
            'FAIL words-changed 6',
            'FAIL words-changed 7',
        ])

    def test_c2_2_words_changed(self):
        # Comparing only truthiness would miss changes to already nonempty lists.
        with patch.object(self.tool.newitem, 'FUNCTION_WORDS', frozenset()):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL words-changed ')],
                         FUNCTION_WORD_FINDINGS)

    def test_c2_3_check_error(self):
        # Stop on an incomplete check without leaking exception text or skipping ahead.
        check = self.tool.newitem.ungrounded_claims

        def fail_on_raw(text, *args):
            if text == 'Raw wildflower honey from Cedar Row Apiary.':
                raise RuntimeError('synthetic check details')
            return check(text, *args)

        with patch.object(self.tool.newitem, 'ungrounded_claims', side_effect=fail_on_raw) as checked:
            lines = self.run_main(1, FAIL)
        self.assertEqual(checked.call_count, 2)
        self.assertEqual(lines, ['case 0 bad=[]', 'FAIL check-error'])

    def test_c3_usage_exit_2(self):
        # Reject arguments instead of ignoring them or printing help as success.
        for argument in ('extra', '--unknown', '--help', '--'):
            with self.subTest(argument=argument):
                result = self.cli(argument)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')  # No last stdout line on usage errors.
                self.assertEqual(result.stderr.splitlines()[-1:], [
                    f'{SCRIPT.name}: error: unrecognized arguments: {argument}',
                ])

    def test_c4_read_only(self):
        # A stray file, bytecode write or touched input changes the snapshot.
        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Additional debug output, missing cases or whitespace drift break the protocol.
        result = self.cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, '')
        lines = result.stdout.splitlines(keepends=True)
        self.assertEqual(lines[-1:], [PASS + '\n'])
        self.assertEqual(len(lines), 10)
        for index, line in enumerate(lines[:-1]):
            self.assertRegex(line, rf'\Acase {index} bad=\[[^\n]*\]\n\Z')

    def test_c6_fixture(self):
        # Removing function words must not be ignored or yield extra findings.
        with patch.object(self.tool.newitem, 'FUNCTION_WORDS', frozenset()):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')],
                         FUNCTION_WORD_FINDINGS)

    def test_c7_live_pins(self):
        # Replay the real repo function; a cached transcript must not pass.
        with patch.object(self.tool.newitem, 'ungrounded_claims',
                          wraps=self.tool.newitem.ungrounded_claims) as checked:
            lines = self.run_main(0, PASS)
        self.assertEqual(checked.call_count, 9)
        self.assertEqual(lines, LIVE_LINES)
