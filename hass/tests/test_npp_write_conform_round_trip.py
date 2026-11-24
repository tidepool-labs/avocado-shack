"""Offline CLI contracts for the S5 → S7 copy round trip."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import importlib.util
import io
from itertools import product
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hass import content_model
from hass.npp import copy


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_write_conform_round_trip.py'
PASS = 'PASS npp_write_conform_round_trip'
FAIL = 'FAIL npp_write_conform_round_trip'
TOTAL = 162  # Measured on the live pins and category table on origin/main.


def matrix_keys():
    return list(product(('food', 'drink', 'fresh', 'non-food'), content_model.CATEGORIES,
                        ('raw', 'house'), ('none', 'first')))


class WriteConformRoundTripTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        # The standalone CLI adds its checkout to sys.path; don't leak that into the suite.
        with patch.object(sys, 'path', list(sys.path)):
            spec.loader.exec_module(self.tool)

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args], cwd=self.work,
                              capture_output=True, text=True, timeout=15)

    def invoke(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        return code, stdout.getvalue(), stderr.getvalue()

    def assert_findings(self, expected, conform):
        code, stdout, stderr = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(stderr, '')
        self.assertEqual(stdout.splitlines(), [*expected, f'matrix writes={TOTAL} conform={conform}', FAIL])

    def test_c1_full_pass(self):
        # The standalone command must find the checkout from another cwd and return success.
        run = self.cli()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # An early refusal must not abort the later checks or leave a PASS trailer.
        write = copy.Writer.write

        def two_findings(writer, ctx, select):
            result = write(writer, ctx, select)
            if (ctx.kind, ctx.category, ctx.variant) == ('food', 'fruit', 'raw'):
                if select is None:
                    return None
                return replace(result, selections={})
            return result

        with patch.object(copy.Writer, 'write', two_findings):
            self.assert_findings(['FAIL no-copy food fruit raw none',
                                  'FAIL nonconform food fruit raw first'], TOTAL - 2)

    def test_c2_1_nonconform(self):
        # Bad selections must be rejected by the real S7 check even when story text is present.
        write = copy.Writer.write

        def broken_selection(writer, ctx, select):
            result = write(writer, ctx, select)
            return replace(result, selections={}) if ctx.facts and select else result

        with patch.object(copy.Writer, 'write', broken_selection):
            self.assert_findings(['FAIL nonconform food pantry raw first story'], TOTAL - 1)

    def test_c2_2_no_copy(self):
        # A missing result isn't a conformance rejection or a missing optional field.
        write = copy.Writer.write

        def missing_copy(writer, ctx, select):
            result = write(writer, ctx, select)
            return None if ctx.facts and select is None else result

        with patch.object(copy.Writer, 'write', missing_copy):
            self.assert_findings(['FAIL no-copy food pantry raw none story'], TOTAL - 1)

    def test_c2_3_story_missing(self):
        # S7 accepts internally consistent copy without a story; the story fixture still needs one.
        write = copy.Writer.write

        def without_story(writer, ctx, select):
            result = write(writer, ctx, select)
            if ctx.facts and select is None:
                return replace(result, text={k: v for k, v in result.text.items() if k != 'story'},
                               selections={k: v for k, v in result.selections.items() if k != 'story'})
            return result

        with patch.object(copy.Writer, 'write', without_story):
            self.assert_findings(['FAIL story-missing none'], TOTAL)

    def test_c2_4_check_error(self):
        # A writer or rebuild exception must count as a failed check without leaking its text.
        for name in ('write', 'conform'):
            with self.subTest(method=name):
                original = getattr(copy.Writer, name)

                def raise_for_raw_fruit(writer, *args):
                    ctx = args[0] if name == 'write' else args[2]
                    if (ctx.kind, ctx.category, ctx.variant) == ('food', 'fruit', 'raw'):
                        raise RuntimeError('synthetic exception detail')
                    return original(writer, *args)

                with patch.object(copy.Writer, name, raise_for_raw_fruit):
                    self.assert_findings(['FAIL check-error', 'FAIL check-error'], TOTAL - 2)

    def test_c3_usage_exit_2(self):
        # Even argparse's usual help and end-of-options tokens aren't admitted arguments.
        for arg in ('extra', '--unknown', '--help', '-h', '--'):
            with self.subTest(arg=arg):
                run = self.cli(arg)
                self.assertEqual(run.returncode, 2)
                self.assertEqual(run.stdout, '')
                self.assertTrue(run.stderr.startswith('usage:'), run.stderr)
                self.assertTrue(run.stderr.splitlines()[-1].endswith(f'unrecognized arguments: {arg}'))

    def test_c4_read_only(self):
        # Catch a later implementation that rewrites pinned data or caches results in the checkout.
        def snapshot():
            result = {}
            for tree in (ROOT / 'hass', ROOT / 'storefront-mockup'):
                for path in (tree, *tree.rglob('*')):
                    stat = path.lstat()
                    result[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
            return result

        before = snapshot()
        run = self.cli()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.splitlines()[-1], PASS)
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_c5_output_shape(self):
        # Debug output, omitted summary, or a duplicate trailer breaks the machine-readable report.
        run = self.cli()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stderr, '')
        self.assertEqual(run.stdout, f'matrix writes={TOTAL} conform={TOTAL}\n{PASS}\n')

    def test_c6_fixture(self):
        # A one-character change on every S5 result must not be accepted, even after normalization.
        write = copy.Writer.write

        def append_space(writer, ctx, select):
            result = write(writer, ctx, select)
            if result is None:
                return None
            return replace(result, text={**result.text, 'name': result.text['name'] + ' '})

        expected = ['FAIL nonconform ' + ' '.join(key) for key in matrix_keys()]
        expected += [f'FAIL nonconform food pantry raw {label} story' for label in ('none', 'first')]
        self.assertEqual(len(expected), TOTAL)
        with patch.object(copy.Writer, 'write', append_space):
            self.assert_findings(expected, 0)

    def test_c7_live_pins(self):
        # Observe the actual results unchanged; a skipped selector or an accidental fallback
        # can keep the counts green, but must not give the wrong story template.
        write = copy.Writer.write
        conform = copy.Writer.conform
        written, checked = [], []

        def observe_write(writer, ctx, select):
            result = write(writer, ctx, select)
            written.append((ctx, 'none' if select is None else 'first', result))
            return result

        def observe_conform(writer, text, selections, ctx):
            checked.append((ctx, text, selections))
            return conform(writer, text, selections, ctx)

        with patch.object(copy.Writer, 'write', observe_write), patch.object(copy.Writer, 'conform', observe_conform):
            code, stdout, stderr = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(stderr, '')
        self.assertEqual(stdout.splitlines(), [f'matrix writes={TOTAL} conform={TOTAL}', PASS])
        self.assertEqual(len(written), TOTAL)
        self.assertEqual(len(checked), TOTAL)
        self.assertEqual([(ctx.kind, ctx.category, ctx.variant, label) for ctx, label, _ in written[:-2]],
                         matrix_keys())
        for (ctx, _, result), (rebuild_ctx, text, selections) in zip(written, checked):
            self.assertIs(rebuild_ctx, ctx)
            self.assertIs(text, result.text)
            self.assertIs(selections, result.selections)
        self.assertEqual([(label, result.selections['story']['template_id']) for _, label, result in written[-2:]],
                         [('none', 'story-makes-founded'), ('first', 'story-makes-town')])


if __name__ == '__main__':
    unittest.main()
