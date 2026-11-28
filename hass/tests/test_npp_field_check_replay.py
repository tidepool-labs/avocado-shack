"""Contract tests for the offline catalog field replay."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_field_check_replay.py'
SPEC = importlib.util.spec_from_file_location('npp_field_check_replay', SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPLAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPLAY)
PASS = 'PASS npp_field_check_replay'
FAIL = 'FAIL npp_field_check_replay'
PLUM = dict(id='fixture-plum', name='Plum Jam', status='active', category='pantry',
            description='A soft, bright jam for toast. It keeps its plum flavour.')


class NppFieldCheckReplayTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.products = self.root / 'products.json'

    def write_products(self, *rows):
        self.products.write_text(json.dumps({'products': rows}), encoding='utf-8')

    def invoke(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(REPLAY, 'PRODUCTS', self.products), redirect_stdout(out), redirect_stderr(err):
            code = REPLAY.main([])
        self.assertEqual(err.getvalue(), '')
        return code, out.getvalue().splitlines()

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=60)

    def assert_input_fail(self, reason):
        with patch.object(REPLAY.npp, 'assets') as assets:
            self.assertEqual(self.invoke(), (1, [f'FAIL {reason} products', FAIL]))
        assets.assert_not_called()

    def test_c1_full_pass(self):
        # Count all excluded rows, including those with a description and those without.
        held = dict(PLUM, status='held')
        del held['description']
        self.write_products(dict(PLUM, status='Active', name='', description=''), held)
        self.assertEqual(self.invoke(), (0, ['excluded 2', 'products 0', 'checked 0', PASS]))

    def test_c2_findings_trailer(self):
        # A refusal from the real validator must not leave the run green.
        self.write_products(dict(PLUM, description=''))
        self.assertEqual(self.invoke(), (1, ['excluded 0', 'products 1', 'checked 3',
                                            'FAIL field-refused description length 1', FAIL]))

    def test_c2_1_input_unsafe(self):
        # Opening an alias before inspecting it would accept the valid target.
        target = self.root / 'target.json'
        target.write_text('{"products": []}', encoding='utf-8')
        self.products.symlink_to(target)
        self.assert_input_fail('input-unsafe')
        self.products = self.root
        self.assert_input_fail('input-unsafe')

    def test_c2_2_input_too_large(self):
        # Cap must win over a parse error; a file exactly at the cap is allowed.
        self.products.write_bytes(b'{"products": []}')
        with patch.object(REPLAY, 'PRODUCTS_CAP', 16):
            self.assertEqual(self.invoke(), (0, ['excluded 0', 'products 0', 'checked 0', PASS]))
            self.products.write_bytes(b'!' * 17)
            self.assert_input_fail('input-too-large')

    def test_c2_3_input_unreadable(self):
        # Missing, unparseable, and malformed inputs cannot masquerade as empty.
        for label, raw in (
            ('missing', None),
            ('utf8', b'{"products": [], "note": "\xff"}'),
            ('json', b'{"products":'),
            ('constant', b'{"products": [], "note": NaN}'),
            ('root', b'[]'),
            ('list', b'{"products": {}}'),
            ('row', b'{"products": [null]}'),
            ('active-missing-description', json.dumps({'products': [
                {key: value for key, value in PLUM.items() if key != 'description'},
            ]}).encode()),
            ('inactive-non-string-description',
             json.dumps({'products': [dict(PLUM, status='held', description=None)]}).encode()),
            *[(key, json.dumps({'products': [dict(PLUM, **{key: None})]}).encode())
              for key in ('id', 'name', 'status', 'category', 'description', 'imageAlt')],
        ):
            with self.subTest(label=label):
                if raw is not None:
                    self.products.write_bytes(raw)
                self.assert_input_fail('input-unreadable')

    def test_c2_4_assets_unreadable(self):
        # Either initializer can fail; do not print exception payloads or call S7.
        self.write_products(PLUM)
        for module, name in ((REPLAY.npp, 'assets'), (REPLAY.copy, 'Writer')):
            with self.subTest(name=name), patch.object(module, name, side_effect=ValueError('fixture-marker')):
                with patch.object(REPLAY.validate, 'field_problem') as check:
                    self.assertEqual(self.invoke(), (1, ['FAIL assets-unreadable', FAIL]))
                check.assert_not_called()

    def test_c2_5_field_refused(self):
        # Equal IDs are still separate rows; preserve order and use each row's caption/fallback.
        pear = dict(PLUM, name='Pear Jam', imageAlt='Pear Jar', description='Pear prose.')
        apple = dict(PLUM, name='Apple Jam', imageAlt='', description='Apple prose.')
        self.write_products(PLUM, dict(PLUM, status='held'), pear, apple)
        verdicts = ['zeta', None, 'caption', 'alpha', 'prose', None, 'alpha', 'prose', None]
        with patch.object(REPLAY.validate, 'field_problem', side_effect=verdicts) as check:
            self.assertEqual(self.invoke(), (1, ['excluded 1', 'products 3', 'checked 9',
                                                'FAIL field-refused name alpha 2',
                                                'FAIL field-refused name zeta 1',
                                                'FAIL field-refused description prose 2',
                                                'FAIL field-refused imageAlt caption 1', FAIL]))
        self.assertEqual(check.call_count, 9)
        expected_contexts = [
            ('Plum Jam', ('Pear prose.', 'Apple prose.')),
            ('Pear Jam', ('A soft, bright jam for toast. It keeps its plum flavour.', 'Apple prose.')),
            ('Apple Jam', ('A soft, bright jam for toast. It keeps its plum flavour.', 'Pear prose.')),
        ]
        for i, (row, caption) in enumerate(((PLUM, 'Plum Jam'), (pear, 'Pear Jar'), (apple, 'Apple Jam'))):
            item, others = expected_contexts[i]
            for j, expected in enumerate((('name', row['name']), ('description', row['description']),
                                          ('imageAlt', caption))):
                writer, field, value, permits, ctx = check.call_args_list[3 * i + j].args
                self.assertIsInstance(writer, REPLAY.copy.Writer)
                self.assertEqual((field, value), expected)
                self.assertEqual(permits, ())
                self.assertEqual(ctx, REPLAY.copy.Context('food', 'pantry', '', item,
                                                          other_descriptions=others))

    def test_c2_6_reason_invalid(self):
        # Full-match, size and type checks prevent verbatim or multiline leakage.
        self.write_products(PLUM)
        for invalid in ('', 'A', 'reason\n', 'two words', 'reason2', 'a' * 42, 7):
            with self.subTest(invalid=invalid), patch.object(REPLAY.validate, 'field_problem', return_value=invalid):
                self.assertEqual(self.invoke(), (1, ['excluded 0', 'products 1', 'checked 3',
                                                    'FAIL reason-invalid', FAIL]))

    def test_c2_7_check_error(self):
        # A raising check must not hide later refusals or print the exception.
        self.write_products(PLUM)
        verdicts = [ValueError('fixture-marker'), ValueError('fixture-marker'), 'caption']
        with patch.object(REPLAY.validate, 'field_problem', side_effect=verdicts):
            self.assertEqual(self.invoke(), (1, ['excluded 0', 'products 1', 'checked 3', 'FAIL check-error',
                                                'FAIL field-refused imageAlt caption 1', FAIL]))

    def test_c3_usage_exit_2(self):
        # Even implicit help or a bare options delimiter would violate the zero-argument CLI.
        for argument in ('--unknown', 'value', '-h', '--help', '--', ''):
            with self.subTest(argument=argument):
                result = self.cli(argument)
                self.assertEqual((result.returncode, result.stdout), (2, ''))
                self.assertRegex(result.stderr.splitlines()[-1], r': error: ')

    def test_c4_read_only(self):
        # An output file or in-place catalog rewrite changes the tree snapshot.
        def snapshot():
            entries = {}
            for name in ('hass', 'storefront-mockup'):
                tree = ROOT / name
                for path in (tree, *tree.rglob('*')):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.cli()
        self.assertEqual((result.returncode, result.stdout.splitlines()[-1], result.stderr), (1, FAIL, ''))
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_c5_output_shape(self):
        # Debug output or a raw rejected product string must not escape the report.
        self.write_products(dict(PLUM, id='fixture-marker', name='', imageAlt='', description='fixture prose'))
        code, lines = self.invoke()
        self.assertEqual((code, lines[-1]), (1, FAIL))
        line_shape = re.compile(r'(?:excluded|products|checked) [0-9]+|'
                                r'FAIL field-refused (?:name|description|imageAlt) [a-z][a-z-]{0,40} [1-9][0-9]*|'
                                r'FAIL npp_field_check_replay')
        for line in lines:
            self.assertIsNotNone(line_shape.fullmatch(line), line)

    def test_c6_fixture_pass(self):
        # A solitary active product must not be compared against its own description.
        self.write_products(PLUM)
        self.assertEqual(self.invoke(), (0, ['excluded 0', 'products 1', 'checked 3', PASS]))

    def test_c7_live_pins(self):
        # A change to catalog copy or S7 policy must surface in the baseline replay.
        result = self.cli()
        self.assertEqual((result.returncode, result.stderr), (1, ''))
        self.assertEqual(result.stdout.splitlines(), [
            'excluded 2',
            'products 170',
            'checked 510',
            'FAIL field-refused name hype 1',
            'FAIL field-refused name number-unclear 1',
            'FAIL field-refused description copied-description 45',
            'FAIL field-refused description hype 1',
            'FAIL field-refused description non-food-serving 1',
            'FAIL field-refused description number-unclear 7',
            'FAIL field-refused imageAlt hype 1',
            'FAIL field-refused imageAlt number-unclear 1',
            FAIL,
        ])
