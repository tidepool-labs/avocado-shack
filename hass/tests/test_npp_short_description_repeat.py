"""Offline CLI contract for the S5 description repeat check, not a copy fix."""
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass.npp import copy, validate


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_short_description_repeat.py'
PASS = 'PASS npp_short_description_repeat'
FAIL = 'FAIL npp_short_description_repeat'


class ShortDescriptionRepeatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(TemporaryDirectory(dir=ROOT))
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(self.tool)

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args],
                              cwd=self.tmp, text=True, capture_output=True, timeout=10)

    def run_main(self, code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            actual = self.tool.main([])
        return self.check_run(actual, stdout.getvalue(), stderr.getvalue(), code, trailer)

    def check_run(self, actual, stdout, stderr, code, trailer):
        self.assertEqual(stderr, '')
        self.assertEqual(actual, code)
        lines = stdout.splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines

    def check_cli(self, result, code, trailer):
        return self.check_run(result.returncode, result.stdout, result.stderr, code, trailer)

    def test_c1_full_pass(self):
        # A stop at round 3 after distinct listings is valid, not a failure or a skip.
        with patch.object(self.tool, 'ITEMS', ('Wildflower Honey',)):
            self.assertEqual(self.run_main(0, PASS), [
                'item 0 round 1 template=desc-food-default',
                'item 0 round 2 template=desc-default-short',
                'item 0 round 3 no-listing',
                PASS,
            ])

    def test_c2_findings_trailer(self):
        # A valid later item must not clear failures or suppress an earlier reason.
        original = copy.Writer.write

        def write(writer, ctx, select):
            if ctx.item == 'Apple Butter':
                return None
            if ctx.item == 'Wildflower Honey':
                raise ValueError('synthetic write failure')
            return original(writer, ctx, select)

        with patch.object(copy.Writer, 'write', write):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')], [
            'FAIL repeated-description 0 3', 'FAIL repeated-description 1 3',
            'FAIL check-error', 'FAIL first-round-none 3',
        ])
        self.assertEqual(lines[-2], 'item 4 round 3 no-listing')

    def test_c2_1_repeated_description(self):
        # Raw string equality misses these; emitting inside the comparison loop
        # would report round 3 twice. The raw descriptions must carry forward.
        texts = ('Take Honey home.', 'TAKE Honey home!', 'take honey home?')
        results = [copy.Copy({'description': text}, {'description': {'template_id': 'fixture'}},
                             True, ()) for text in texts]
        with patch.object(self.tool, 'ITEMS', ('Honey',)), \
                patch.object(copy.Writer, 'write', autospec=True, side_effect=results) as write:
            self.assertEqual(self.run_main(1, FAIL), [
                'item 0 round 1 template=fixture',
                'item 0 round 2 template=fixture', 'FAIL repeated-description 0 2',
                'item 0 round 3 template=fixture', 'FAIL repeated-description 0 3', FAIL,
            ])
        self.assertEqual([call.args[1:] for call in write.call_args_list], [
            (copy.Context('food', 'pantry', 'raw', 'Honey', 'add honey',
                          other_descriptions=texts[:i]), None) for i in range(3)
        ])

    def test_c2_2_first_round_none(self):
        # Without the first-round check, zero listings could be declared a pass.
        with patch.object(self.tool, 'ITEMS', ('Honey',)), \
                patch.object(copy.Writer, 'write', return_value=None) as write:
            self.assertEqual(self.run_main(1, FAIL), [
                'item 0 round 1 no-listing', 'FAIL first-round-none 0', FAIL,
            ])
        write.assert_called_once()

    def test_c2_3_check_error(self):
        # An exception is not no-listing and its text must not reach either stream.
        with patch.object(self.tool, 'ITEMS', ('Honey',)), \
                patch.object(copy.Writer, 'write', side_effect=RuntimeError('synthetic marker')):
            self.assertEqual(self.run_main(1, FAIL), ['FAIL check-error', FAIL])

    def test_c3_usage_exit_2(self):
        # Default help or ignored arguments would violate the no-arguments CLI.
        for arg in ('Honey', '--unknown', '--help', '--'):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.startswith('usage: '))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f'{SCRIPT.name}: error: unrecognized arguments: {arg}')

    @staticmethod
    def snapshot():
        entries = {}
        for tree in (ROOT / 'hass', ROOT / 'storefront-mockup'):
            for path in (tree, *tree.rglob('*')):
                stat = path.lstat()
                entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
        return entries

    def test_c4_read_only(self):
        # A cache or catalog write could leave the stdout verdict unchanged.
        before = self.snapshot()
        self.check_cli(self.cli(), 1, FAIL)
        self.assertEqual(self.snapshot(), before)

    def test_c5_output_shape(self):
        # Printing descriptions or diagnostics leaks beyond the CLI vocabulary.
        lines = self.check_cli(self.cli(), 1, FAIL)
        for line in lines[:-1]:
            self.assertRegex(line, r'^(?:item [0-4] round [1-3] (?:no-listing|template=[a-z0-9-]+)'
                                   r'|FAIL (?:repeated-description [0-4] [1-3]'
                                   r'|first-round-none [0-4]|check-error))$')

    def test_c6_fixture(self):
        # A constant failure or a bypass of the real validator cannot follow
        # the simulated exact-copy refusal through Writer's fallback ladder.
        original = validate.field_problem

        def reject_repeat(writer, key, text, permits, ctx):
            if key == 'description' and any(copy.words(text) == copy.words(previous)
                                            for previous in ctx.other_descriptions):
                return 'copied-description'
            return original(writer, key, text, permits, ctx)

        with patch.object(validate, 'field_problem', reject_repeat):
            lines = self.run_main(0, PASS)
        for i in (0, 1):
            with self.subTest(item=i):
                self.assertIn(f'item {i} round 3 no-listing', lines)
        self.assertFalse(any(line.startswith('FAIL ') for line in lines))

    def test_c7_live_pins(self):
        # Ensure the report walks the real fallback ladder, including both
        # reproductions and the longer-name controls. Measured on origin/main.
        expected = []
        for i in range(5):
            expected.extend([f'item {i} round 1 template=desc-food-default',
                             f'item {i} round 2 template=desc-default-short'])
            if i in (0, 1):
                expected.extend([f'item {i} round 3 template=desc-default-short',
                                 f'FAIL repeated-description {i} 3'])
            else:
                expected.append(f'item {i} round 3 no-listing')
        self.assertEqual(self.run_main(1, FAIL), [*expected, FAIL])
