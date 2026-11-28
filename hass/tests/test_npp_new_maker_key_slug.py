"""Exercise the offline new-maker key checker at its command boundary."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_new_maker_key_slug.py'
SPEC = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)

PASS = 'PASS npp_new_maker_key_slug'
FAIL = 'FAIL npp_new_maker_key_slug'


def snapshot():
    entries = {}
    for tree in (ROOT / 'hass', ROOT / 'storefront-mockup'):
        for path in (tree, *tree.rglob('*')):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class NewMakerKeySlugTests(unittest.TestCase):
    def run_cli(self, *args):
        with TemporaryDirectory() as cwd:
            return subprocess.run([sys.executable, '-B', str(SCRIPT), *args], cwd=cwd,
                                  capture_output=True, text=True, timeout=10)

    def assert_run(self, status, stdout, stderr, *, expected_status, trailer):
        self.assertEqual(status, expected_status)
        self.assertEqual(stderr, '')
        lines = stdout.splitlines()
        self.assertTrue(lines, 'missing output')
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def run_main(self, expected_status=1, trailer=FAIL):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = checker.main([])
        return self.assert_run(status, stdout.getvalue(), stderr.getvalue(),
                               expected_status=expected_status, trailer=trailer)

    def test_c1_full_pass(self):
        # A successful run must not report failure or suppress its observation.
        with patch.object(checker, 'NAMES', ['Etto Farm']):
            self.assertEqual(self.run_main(0, PASS), ['slug 0 accepted=yes key=etto-farm'])

    def test_c2_findings_trailer(self):
        # An early finding must survive subsequent successful checks.
        with patch.object(checker, 'NAMES', ['東京農園', 'Etto Farm']):
            self.assertEqual(self.run_main(), [
                'slug 0 accepted=yes key=-', 'FAIL key-empty 0',
                'slug 1 accepted=yes key=etto-farm',
            ])

    def test_c2_1_key_empty(self):
        # An empty key takes precedence over letter loss, but only for an accepted name.
        with patch.object(checker, 'NAMES', ['東京農園']):
            self.assertEqual(self.run_main(), ['slug 0 accepted=yes key=-', 'FAIL key-empty 0'])
            with patch.object(checker.label_reader, 'identity_text', return_value=None) as identity:
                self.assertEqual(self.run_main(0, PASS), ['slug 0 accepted=no key=-'])
            identity.assert_called_once_with('brand', '東京農園')

    def test_c2_2_key_drops_letters(self):
        # Test the folded letters, not the raw accents, apostrophe or ampersand.
        with patch.object(checker, 'NAMES', ['Ελιά Farm', 'Café Ñandú', "D'Arcy & Sons"]):
            self.assertEqual(self.run_main(), [
                'slug 0 accepted=yes key=farm', 'FAIL key-drops-letters 0',
                'slug 1 accepted=yes key=cafe-nandu', 'slug 2 accepted=yes key=d-arcy-sons',
            ])
            with patch.object(checker.label_reader, 'identity_text', return_value='changed'):
                self.assertEqual(self.run_main(0, PASS), [
                    'slug 0 accepted=no key=farm', 'slug 1 accepted=no key=cafe-nandu',
                    'slug 2 accepted=no key=d-arcy-sons',
                ])

    def test_c2_3_no_maker_op(self):
        # A product-only candidate must not reuse the previous maker op or look like an empty key.
        stage_type = checker.stages.ProductionStages
        candidate = stage_type._candidate

        def product_only_for_second(ps, context, listing, finance, makers, key, fresh, url, sha, selector):
            return candidate(ps, context, listing, finance, makers, key,
                             fresh and context.maker_name != 'Café Ñandú', url, sha, selector)

        with patch.object(checker, 'NAMES', ['Etto Farm', 'Café Ñandú']), \
                patch.object(stage_type, '_candidate', product_only_for_second):
            self.assertEqual(self.run_main(), [
                'slug 0 accepted=yes key=etto-farm',
                'slug 1 accepted=yes key=-', 'FAIL no-maker-op 1',
            ])

    def test_c2_4_check_error(self):
        # Both seams can fail: an exception must neither leak text nor abort the other checks.
        for owner, method, name_arg in (
            (checker.stages.ProductionStages, '_candidate', lambda args: args[1].maker_name),
            (checker.label_reader, 'identity_text', lambda args: args[1]),
        ):
            original = getattr(owner, method)

            def fail_first(*args):
                if name_arg(args) == 'Etto Farm':
                    raise RuntimeError('synthetic exception detail')
                return original(*args)

            with self.subTest(method=method), patch.object(checker, 'NAMES', ['Etto Farm', 'Café Ñandú']), \
                    patch.object(owner, method, fail_first):
                lines = self.run_main()
                self.assertEqual([line for line in lines if line.startswith('FAIL')], ['FAIL check-error'])
                self.assertEqual(lines[-1], 'slug 1 accepted=yes key=cafe-nandu')
                self.assertNotIn('synthetic exception detail', '\n'.join(lines))

    def test_c3_usage_exit_2(self):
        # Auto-help or accepting even one argument would bypass the no-argument contract.
        for arg in ('extra', '--unknown', '-h', '--help', '--'):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.startswith('usage: '))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f'{SCRIPT.name}: error: unrecognized arguments: {arg}')

    def test_c4_read_only(self):
        # An accidental catalog write or new local Hass artifact changes the tree snapshots.
        before = snapshot()
        result = self.run_cli()
        self.assert_run(result.returncode, result.stdout, result.stderr,
                        expected_status=1, trailer=FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Reject debug banners, names, extra fields, and tracebacks on a findings run.
        result = self.run_cli()
        lines = self.assert_run(result.returncode, result.stdout, result.stderr,
                                expected_status=1, trailer=FAIL)
        for line in lines:
            self.assertRegex(line, r'^(?:slug [0-6] accepted=(?:yes|no) key=(?:-|[a-z0-9]+(?:-[a-z0-9]+)*)'
                                   r'|FAIL (?:(?:key-empty|key-drops-letters|no-maker-op) [0-6]|check-error))$')

    def test_c6_fixture(self):
        # A repaired fold must turn the actual candidate keys and the decision green.
        transliterated = {'Etto Farm': 'etto farm', 'Café Ñandú': 'cafe nandu',
                          'Ελιά Farm': 'elia farm', '東京農園': 'tokyo noen',
                          'Øster Farm': 'oster farm', "D'Arcy & Sons": 'd arcy sons',
                          'Ferme Bœuf': 'ferme boeuf'}
        with patch.object(checker.stages.claims, 'fold', side_effect=transliterated.__getitem__) as fold:
            self.assertEqual(self.run_main(0, PASS), [
                'slug 0 accepted=yes key=etto-farm', 'slug 1 accepted=yes key=cafe-nandu',
                'slug 2 accepted=yes key=elia-farm', 'slug 3 accepted=yes key=tokyo-noen',
                'slug 4 accepted=yes key=oster-farm', 'slug 5 accepted=yes key=d-arcy-sons',
                'slug 6 accepted=yes key=ferme-boeuf',
            ])
        self.assertEqual({call.args for call in fold.call_args_list}, {(name,) for name in transliterated})

    def test_c7_live_pins(self):
        # Unpatched: detect a change in acceptance, actual slug generation, or finding order.
        self.assertEqual(self.run_main(), [
            'slug 0 accepted=yes key=etto-farm', 'slug 1 accepted=yes key=cafe-nandu',
            'slug 2 accepted=yes key=farm', 'FAIL key-drops-letters 2',
            'slug 3 accepted=yes key=-', 'FAIL key-empty 3',
            'slug 4 accepted=yes key=ster-farm', 'FAIL key-drops-letters 4',
            'slug 5 accepted=yes key=d-arcy-sons',
            'slug 6 accepted=yes key=ferme-b-uf', 'FAIL key-drops-letters 6',
        ])
