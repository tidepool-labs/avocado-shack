"""Behavioral tests for the offline maker name binding report."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/maker_name_binding_check.py'
PASS = 'PASS maker_name_binding_check'
FAIL = 'FAIL maker_name_binding_check'
CHECKS = ('identity', 'plain', 'idfield', 'owner')


def product(name='Plum Jam', brand='Hill Farm', status='active'):
    return {'id': 'fixture-item', 'name': name, 'brand': brand, 'status': status}


def maker(name):
    return {'name': name, 'place': 'Sample Valley'}


class MakerNameBindingCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('maker_name_binding_check', SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError('cannot load maker_name_binding_check')
        cls.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.script)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.products = self.root / 'product-fixture.json'
        self.makers = self.root / 'maker-fixture.json'
        self.patch(patch.multiple(self.script, PRODUCTS=self.products, MAKERS=self.makers))
        self.catalog([product()], {'hill': maker('Hill Farm')})

    def patch(self, patcher):
        self.addCleanup(patcher.stop)
        return patcher.start()

    def catalog(self, products, makers):
        self.products.write_text(json.dumps({'products': products}), encoding='utf-8')
        self.makers.write_text(json.dumps({'makers': makers}), encoding='utf-8')

    def invoke(self):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = self.script.main([])
        self.assertEqual(err.getvalue(), '')
        return code, out.getvalue().splitlines()

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=15)

    def assert_report(self, result, code, *body):
        status, lines = result
        self.assertEqual(status, code)
        self.assertEqual(lines, [*body, PASS if code == 0 else FAIL])

    def test_c1_full_pass(self):
        # Valid ordinary names must not inherit the checked-in catalog's findings.
        self.catalog([product(brand='Cedar Farm'), product(brand='Hill Farm')],
                     {'hill': maker('Hill Farm'), 'cedar': maker('Cedar Farm')})
        self.assert_report(self.invoke(), 0, 'makers 2', 'brands 2')

    def test_c2_findings_trailer(self):
        # Multiple findings still produce a single FAIL trailer and nonzero status.
        self.catalog([product('Jam / Jelly')], {'example': maker('Cannot Bind?')})
        code, lines = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(lines.count(FAIL), 1)
        self.assertIn('FAIL name-binding maker plain 1', lines[:-1])
        self.assertIn('FAIL product-name-plain 1', lines[:-1])

    def test_c2_1_input_unsafe(self):
        # A valid symlink target must not be opened; a directory isn't input either.
        for label, target in [('products', self.products), ('makers', self.makers)]:
            alias = self.root / f'{label}-alias'
            alias.symlink_to(target)
            for path in (alias, self.root):
                with self.subTest(label=label, path=path.name):
                    with patch.object(self.script, label.upper(), path):
                        self.assert_report(self.invoke(), 1, f'FAIL input-unsafe {label}')

    def test_c2_2_input_too_large(self):
        # Valid JSON with padding is still refused when even one byte over the cap.
        with patch.object(self.script, 'INPUT_CAP', 256):
            for label, path in [('products', self.products), ('makers', self.makers)]:
                with self.subTest(label=label):
                    original = path.read_bytes()
                    path.write_bytes(original.ljust(256, b' '))
                    self.assert_report(self.invoke(), 0, 'makers 1', 'brands 1')
                    path.write_bytes(original.ljust(257, b' '))
                    self.assert_report(self.invoke(), 1, f'FAIL input-too-large {label}')
                    path.write_bytes(original)

    def test_c2_3_input_unreadable(self):
        # Decoding and row-shape errors must not be treated as an empty catalog.
        for label, path, malformed in (
            ('products', self.products, [b'[]', b'{"products":{}}', b'{"products":[null]}',
                                        b'{"products":[{"name":"Jam"}]}']),
            ('makers', self.makers, [b'[]', b'{"makers":[]}', b'{"makers":{"x":null}}',
                                     b'{"makers":{"x":{"name":"Hill Farm","place":"Hill",'
                                     b'"story":null}}}']),
        ):
            original = path.read_bytes()
            for raw in (None, b'\xff', b'{', *malformed):
                with self.subTest(label=label, raw=raw):
                    if raw is None:
                        with patch.object(self.script, label.upper(), self.root / 'absent.json'):
                            self.assert_report(self.invoke(), 1, f'FAIL input-unreadable {label}')
                    else:
                        path.write_bytes(raw)
                        self.assert_report(self.invoke(), 1, f'FAIL input-unreadable {label}')
            path.write_bytes(original)

    def test_c2_4_name_binding(self):
        # Selective failures detect cross-wired predicates, reordering and double-counted brands.
        self.catalog([
            product(brand='Cedar Farm'), product(brand='Ash Farm'), product(brand='Cedar Farm'),
            product(brand=self.script.claims.PLACEHOLDER), product(brand='Hidden Farm', status='Active'),
        ], {'z': maker('Oak Farm'), 'a': maker('Hill Farm')})
        checks = Mock()
        checks.identity.side_effect = lambda field, name: None if name == 'Oak Farm' else name
        checks.plain.side_effect = lambda name: name not in ('Oak Farm', 'Cedar Farm')
        checks.idfield.side_effect = lambda name: name not in ('Hill Farm', 'Ash Farm', 'Cedar Farm')
        checks.owner.side_effect = lambda texts, item: None if texts == ['made by Ash Farm'] else texts[0][8:]
        for module, attr, stub in (
            (self.script.label_reader, 'identity_text', checks.identity),
            (self.script.copy, 'plain', checks.plain),
            (self.script.research, '_identity_field', checks.idfield),
            (self.script.missing, '_owner_maker', checks.owner),
        ):
            self.patch(patch.object(module, attr, stub))
        self.assert_report(self.invoke(), 1, 'makers 2', 'brands 2',
                           'FAIL name-binding maker identity 1', 'FAIL name-binding maker plain 1',
                           'FAIL name-binding maker idfield 1', 'FAIL name-binding brand plain 1',
                           'FAIL name-binding brand idfield 2', 'FAIL name-binding brand owner 1')
        expected = []
        for value in ('Oak Farm', 'Hill Farm', 'Ash Farm', 'Cedar Farm'):
            expected.extend((call.identity('brand', value), call.plain(value), call.idfield(value),
                             call.owner(['made by ' + value], 'jam')))
        self.assertEqual(checks.mock_calls, expected + [call.plain('Plum Jam')] * 4)

    def test_c2_5_product_name_plain(self):
        # Product names are a separate check, including active rows with no identified producer.
        self.catalog([product('Jam / Jelly'), product('Jam / Jelly', self.script.claims.PLACEHOLDER),
                      product('Jam / Jelly', status='Active'), product()], {'hill': maker('Hill Farm')})
        self.assert_report(self.invoke(), 1, 'makers 1', 'brands 1', 'FAIL product-name-plain 2')

    def test_c2_6_check_error(self):
        # Each validator can fail to complete; none may leak exception details or pass silently.
        for module, attr in (
            (self.script.label_reader, 'identity_text'), (self.script.copy, 'plain'),
            (self.script.research, '_identity_field'), (self.script.missing, '_owner_maker'),
        ):
            with self.subTest(attr=attr):
                with patch.object(module, attr, side_effect=RuntimeError('synthetic diagnostic')):
                    self.assert_report(self.invoke(), 1, 'makers 1', 'brands 1', 'FAIL check-error')

    def test_c3_usage_exit_2(self):
        # Even default argparse help would accept an argument, contrary to this zero-argument CLI.
        for arg in ('--unknown', 'extra', '-h', '--help', '--', '-', ''):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')  # C3 has no stdout trailer.
                self.assertIn('error: unrecognized arguments:', result.stderr)

    def test_c4_read_only(self):
        # A subprocess run must not generate caches or write back to either tree.
        def snapshot():
            entries = {}
            for tree in ('hass', 'storefront-mockup'):
                root = ROOT / tree
                for path in (root, *root.rglob('*')):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # A line break in a name must not introduce a forged or data-bearing output line.
        value = 'Sample Farm\nFAIL not-a-reason'
        self.catalog([product(value, value)], {'example': maker(value)})
        code, lines = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        for line in lines:
            self.assertRegex(line, r'\A(?:(?:makers|brands) [0-9]+|'
                             r'FAIL (?:name-binding (?:maker|brand) (?:identity|plain|idfield|owner) [0-9]+'
                             r'|product-name-plain [0-9]+|maker_name_binding_check))\Z')

    def test_c6_fixture_pass(self):
        # Locate both patched files rather than falling back to repository data.
        self.assert_report(self.invoke(), 0, 'makers 1', 'brands 1')

    def test_c7_live_pins(self):
        # Measure actual checked-in names through all four unchanged validators.
        result = self.cli()
        self.assertEqual(result.stderr, '')
        self.assert_report((result.returncode, result.stdout.splitlines()), 1, 'makers 26', 'brands 28',
                           *(f'FAIL name-binding {kind} {check} 1'
                             for kind in ('maker', 'brand') for check in CHECKS),
                           'FAIL product-name-plain 2')
