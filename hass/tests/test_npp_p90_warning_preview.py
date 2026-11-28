"""Contract tests for the offline NPP warning preview."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_p90_warning_preview.py'
SPEC = importlib.util.spec_from_file_location('npp_p90_warning_preview', SCRIPT)
assert SPEC is not None and SPEC.loader is not None
preview = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preview)

PASS = 'PASS npp_p90_warning_preview'
FAIL = 'FAIL npp_p90_warning_preview'
LIVE_FINDING = 'FAIL fixed-line-over-p90 origin'
LIVE_COUNTS = [
    'products 170', 'warn brand 9', 'warn name 8', 'warn origin 66',
    'warn description 17', 'warn maker_name 9', 'warn maker_place 1',
    'warn maker_story 0', 'warn maker_url 14', 'warn image 0',
    'warn image_alt 3', 'warn link_to_this 0',
]


def row(chars=1000, words=1000):
    return {'chars': {'p90': chars}, 'words': {'p90': words}}


class WarningPreviewTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(dir=ROOT)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.products = self.root / 'products.json'
        self.makers = self.root / 'makers.json'
        self.write(self.products, 'products', [])
        self.write(self.makers, 'makers', {})
        self.limits = {'brand': row(), 'origin': row()}

    @staticmethod
    def write(path, key, value):
        path.write_text(json.dumps({key: value}), encoding='utf-8')

    def invoke(self, **overrides):
        stdout, stderr = io.StringIO(), io.StringIO()
        constants = {'PRODUCTS': self.products, 'MAKERS': self.makers} | overrides
        with ExitStack() as stack:
            for name, value in constants.items():
                stack.enter_context(patch.object(preview, name, value))
            stack.enter_context(patch.object(
                preview.copy.Writer, '__init__', autospec=True,
                side_effect=lambda writer, _: setattr(writer, 'limits', {'fields': self.limits}),
            ))
            stack.enter_context(redirect_stdout(stdout))
            stack.enter_context(redirect_stderr(stderr))
            code = preview.main([])
        self.assertEqual(stderr.getvalue(), '')
        return code, stdout.getvalue().splitlines()

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, '-B', str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def assert_result(self, result, code, trailer):
        actual_code, lines = result
        self.assertEqual(actual_code, code)
        self.assertEqual(lines[-1:], [trailer])
        return lines

    def assert_input_failure(self, result, reason):
        self.assertEqual(self.assert_result(result, 1, FAIL), [f'FAIL {reason}', FAIL])

    def test_c1_full_pass(self):
        # The valid path must not treat informational counts as failures.
        self.assertEqual(self.assert_result(self.invoke(), 0, PASS),
                         ['products 0', 'warn brand 0', 'warn origin 0', PASS])

    def test_c2_findings_trailer(self):
        # Multiple findings must produce one terminal marker, not one per check.
        self.limits |= {'bad field': row(), 'description': {}}
        lines = self.assert_result(self.invoke(), 1, FAIL)
        self.assertEqual(lines[-3:], ['FAIL field-invalid', 'FAIL check-error', FAIL])
        self.assertEqual(lines.count(FAIL), 1)

    def test_c2_1_input_unsafe(self):
        # Valid JSON behind either symlink must still be refused, as must a directory.
        for name, path in [('products', self.products), ('makers', self.makers)]:
            alias = self.root / f'{name}-link'
            alias.symlink_to(path)
            for unsafe in (alias, self.root):
                with self.subTest(name=name, kind=unsafe.name):
                    self.assert_input_failure(self.invoke(**{name.upper(): unsafe}),
                                              f'input-unsafe {name}')

    def test_c2_2_input_too_large(self):
        # Oversize is classified before attempting to decode the bytes.
        self.makers.write_bytes(b'\xff' * 129)
        self.assert_input_failure(self.invoke(INPUT_CAP=128), 'input-too-large makers')

    def test_c2_3_input_unreadable(self):
        # A bad input must stop the run before even consulting the assets.
        invalid = self.root / 'invalid.json'
        for name, cases in (
            ('PRODUCTS', (b'\xff', b'{', b'{"products": {}}',
                          b'{"products":[{"id":"p","name":"N","status":"active","description":null}]}')),
            ('MAKERS', (b'\xff', b'{', b'{"makers": []}',
                        b'{"makers":{"m":{"name":"N","place":false}}}')),
        ):
            for raw in (None, *cases):
                with self.subTest(name=name, raw=raw), patch.object(preview.npp, 'assets') as assets:
                    path = self.root / 'missing.json' if raw is None else invalid
                    if raw is not None:
                        path.write_bytes(raw)
                    self.assert_input_failure(self.invoke(**{name: path}),
                                              f'input-unreadable {name.lower()}')
                    assets.assert_not_called()

    def test_c2_3_producer_key_null_or_absent(self):
        # A null key must measure the same origin as an absent key, not fail
        # validation or look up a maker named 'null'. A number is not a key.
        self.limits['origin'] = row(words=6)
        self.write(self.makers, 'makers', {'null': {'name': 'Maker', 'place': 'Town'}})
        product = {'id': 'p', 'name': 'Item', 'status': 'active'}
        for key in ({}, {'producerKey': None}):
            with self.subTest(key=key):
                self.write(self.products, 'products', [{**product, **key}])
                self.assertEqual(self.assert_result(self.invoke(), 1, FAIL), [
                    'products 1', 'warn brand 0', 'warn origin 1', LIVE_FINDING, FAIL,
                ])
        self.write(self.products, 'products', [{**product, 'producerKey': 7}])
        self.assert_input_failure(self.invoke(), 'input-unreadable products')

    def test_c2_4_assets_unreadable(self):
        # An exception must not leak its message or allow a false pass.
        with patch.object(preview.npp, 'assets', side_effect=RuntimeError('synthetic detail')):
            self.assert_input_failure(self.invoke(), 'assets-unreadable')

    def test_c2_5_fixed_line_over_p90(self):
        # These are findings even with no products; report origin first, not table order.
        self.limits = {'brand': row(chars=14), 'origin': row(words=6)}
        self.assertEqual(self.assert_result(self.invoke(), 1, FAIL), [
            'products 0', 'warn brand 0', 'warn origin 0', LIVE_FINDING,
            'FAIL fixed-line-over-p90 brand', FAIL,
        ])

    def test_c2_6_field_invalid(self):
        # Neither an invalid name nor a newline it contains may reach stdout.
        self.limits['origin\nsynthetic'] = row()
        self.assertEqual(self.assert_result(self.invoke(), 1, FAIL),
                         ['products 0', 'warn brand 0', 'warn origin 0', 'FAIL field-invalid', FAIL])

    def test_c2_7_check_error(self):
        # Missing or nonnumeric p90 must not silently act like an infinite limit.
        for malformed in ({'words': {'p90': 5}}, {'chars': {'p90': 9}, 'words': {'p90': '5'}}):
            with self.subTest(row=malformed):
                self.limits['brand'] = malformed
                self.assertEqual(self.assert_result(self.invoke(), 1, FAIL),
                                 ['products 0', 'warn origin 0', 'FAIL check-error', FAIL])

    def test_c3_usage_exit_2(self):
        # Argparse defaults accept help and bare '--'; the no-argument CLI must not.
        for argument in ('unexpected', '--unknown', '-h', '--help', '--'):
            with self.subTest(argument=argument):
                result = self.cli(argument)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')  # No trailer on usage error.
                self.assertIn('error:', result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Running the CLI must not generate caches, edit the catalog, or write drafts.
        def snapshot():
            entries = {}
            for folder in ('hass', 'storefront-mockup'):
                directory = ROOT / folder
                for path in (directory, *directory.rglob('*')):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.cli()
        self.assertEqual(snapshot(), before)
        self.assert_result((result.returncode, result.stdout.splitlines()), 1, FAIL)

    def test_c5_output_shape(self):
        # Free-form catalog strings and unexpected diagnostic lines must not be emitted.
        self.write(self.products, 'products', [{'id': 'p', 'name': 'synthetic text\nextra line',
                                                'status': 'active'}])
        self.limits = {'name': row(chars=3), 'brand': row(), 'origin': row(words=6)}
        self.assertEqual(self.assert_result(self.invoke(), 1, FAIL), [
            'products 1', 'warn name 1', 'warn brand 0', 'warn origin 1', LIVE_FINDING, FAIL,
        ])

    def test_c6_fixture_pass(self):
        # Hardcoded counts or the real asset thresholds would fail this relaxed preview.
        product = {'id': 'p', 'name': 'A lengthy name for a synthetic product',
                   'description': 'word ' * 30, 'status': 'active', 'producerKey': 'm'}
        self.write(self.products, 'products', [product, {**product, 'id': 'q', 'status': 'Active'}])
        self.write(self.makers, 'makers', {'m': {'name': 'Maker', 'place': 'Town'}})
        self.limits = dict.fromkeys((line.split()[1] for line in LIVE_COUNTS[1:]), row())
        lines = self.assert_result(self.invoke(), 0, PASS)
        self.assertEqual(lines, ['products 1', *(f'warn {field} 0' for field in self.limits), PASS])

    def test_c7_live_pins(self):
        # Only this pin asserts the complete measured catalog output and table order.
        result = self.cli()
        self.assertEqual(result.stderr, '')
        lines = self.assert_result((result.returncode, result.stdout.splitlines()), 1, FAIL)
        self.assertEqual(lines, [*LIVE_COUNTS, LIVE_FINDING, FAIL])
