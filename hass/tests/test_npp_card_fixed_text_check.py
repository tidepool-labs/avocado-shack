"""Exercise the fixed card text guard offline, using disposable source copies."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_card_fixed_text_check.py'
SPEC = importlib.util.spec_from_file_location('npp_card_fixed_text_check', SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
PASS = 'PASS npp_card_fixed_text_check'
FAIL = 'FAIL npp_card_fixed_text_check'


class FixedCardTextCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.shop = self.directory / 'shop.js'

    def copy_shop(self, *remove):
        text = CHECK.SHOP.read_text(encoding='utf-8')
        for snippet in remove:
            self.assertIn(snippet, text)
            text = text.replace(snippet, '')
        self.shop.write_text(text, encoding='utf-8')

    def invoke(self, *, shop=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(CHECK, 'SHOP', self.shop if shop is None else shop), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = CHECK.main([])
        self.assertEqual(stderr.getvalue(), '')
        return code, stdout.getvalue().splitlines()

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args], cwd=self.directory,
                              capture_output=True, text=True, timeout=10)

    def assert_pass(self, result):
        code, lines = result
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertFalse(any(line.startswith('FAIL ') for line in lines))

    def assert_findings(self, result, *expected):
        code, lines = result
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')],
                         [f'FAIL {reason}' for reason in expected])

    def assert_input_failure(self, reason, *, shop=None):
        # A bad input must not fall through to the validator or the row checks.
        with patch.object(CHECK.validate, '_fixed_ui') as validator:
            result = self.invoke(shop=shop)
        validator.assert_not_called()
        self.assert_findings(result, reason)
        self.assertEqual(result[1], [f'FAIL {reason}', FAIL])

    def test_c1_full_pass(self):
        # Repeated snippets are still present; the check must not require uniqueness.
        self.copy_shop()
        with self.shop.open('a', encoding='utf-8') as source:
            source.write('\n// <span>New</span>\n')
        self.assert_pass(self.invoke())

    def test_c2_findings_trailer(self):
        # A readable file with no pinned text collects all row failures, not just the first.
        self.shop.write_text('// Empty renderer fixture\n', encoding='utf-8')
        rows = ('link', 'badges', 'summary', 'visit', 'see-all', 'availability',
                'origin-unknown', 'origin-forms', 'market-brand')
        self.assert_findings(self.invoke(), *(f'js-text-missing {row}' for row in rows))

    def test_c2_1_input_unsafe(self):
        # Even a link to a valid renderer must not be followed; directories are unsafe too.
        self.copy_shop()
        alias = self.directory / 'alias.js'
        alias.symlink_to(self.shop)
        dangling = self.directory / 'dangling.js'
        dangling.symlink_to(self.directory / 'absent.js')
        for candidate in (alias, dangling, self.directory):
            with self.subTest(candidate=candidate.name):
                self.assert_input_failure('input-unsafe shop', shop=candidate)

    def test_c2_2_input_too_large(self):
        # At the byte cap the valid source passes; one byte over must stop the checks.
        self.copy_shop()
        size = self.shop.stat().st_size
        with patch.object(CHECK, 'SHOP_CAP', size):
            self.assert_pass(self.invoke())
        with patch.object(CHECK, 'SHOP_CAP', size - 1):
            self.assert_input_failure('input-too-large shop')

    def test_c2_3_input_unreadable(self):
        # Missing files, decoding, and read errors must not escape or look like JS drift.
        # SHOP is UTF-8 JS text: no JSON decoder or JSON shape check applies here.
        with self.subTest(case='missing'):
            self.assert_input_failure('input-unreadable shop')
        with self.subTest(case='invalid UTF-8'):
            self.shop.write_bytes(b'\xff')
            self.assert_input_failure('input-unreadable shop')
        with self.subTest(case='read error'):
            self.copy_shop()
            with patch.object(Path, 'open', side_effect=OSError('synthetic detail')):
                self.assert_input_failure('input-unreadable shop')

    def test_c2_4_ui_roles_changed(self):
        # A baseline-only key change must be caught even if the populated values match.
        self.copy_shop()
        fixed_ui = CHECK.validate._fixed_ui

        def changed(maker, count, organic):
            ui = fixed_ui(maker, count, organic)
            if (maker, count, organic) == (None, None, False):
                ui['.synthetic-extra-role'] = ()
            return ui

        with patch.object(CHECK.validate, '_fixed_ui', side_effect=changed):
            self.assert_findings(self.invoke(), 'ui-roles-changed')

    def test_c2_5_ui_literal_changed(self):
        # The populated check catches wording drift, a missing empty tuple and origin drift.
        self.copy_shop()
        fixed_ui = CHECK.validate._fixed_ui

        def changed(maker, count, organic):
            ui = fixed_ui(maker, count, organic)
            if (maker, count, organic) == ('MAKERX', 2, True):
                del ui['.availability']
                ui['.food-badges > span'] = ('Organic', 'New')
                ui[':scope > .card-link'] = ('Synthetic replacement',)
            return ui

        with patch.object(CHECK.validate, '_fixed_ui', side_effect=changed), \
                patch.object(CHECK.validate, 'ORIGIN_UNKNOWN', 'Synthetic origin'):
            self.assert_findings(self.invoke(), 'ui-literal-changed link',
                                 'ui-literal-changed badges', 'ui-literal-changed availability',
                                 'ui-literal-changed origin-unknown')

    def test_c2_6_js_text_missing(self):
        # Multiple missing snippets in one row must produce one finding, in row order.
        self.copy_shop("'From the market'", '<span>New</span>', '<span>Organic</span>', '>Link to this</a>')
        self.assert_findings(self.invoke(), 'js-text-missing link', 'js-text-missing badges',
                             'js-text-missing market-brand')

    def test_c2_7_check_error(self):
        # Exceptions in either call must not become a traceback or a success.
        self.copy_shop()
        fixed_ui = CHECK.validate._fixed_ui
        for prefix in ([], [fixed_ui(None, None, False)]):
            with self.subTest(successful_calls=len(prefix)), \
                    patch.object(CHECK.validate, '_fixed_ui',
                                 side_effect=[*prefix, RuntimeError('synthetic detail')]):
                self.assert_findings(self.invoke(), 'check-error')

    def test_c3_usage_exit_2(self):
        # There are no required arguments, and even help and a bare separator are rejected.
        for argument in ('--unknown', '--help', '-h', 'unused', '--', ''):
            with self.subTest(argument=argument):
                result = self.cli(argument)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertIn('error: unrecognized arguments:', result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Detect a rewrite even if it leaves the same content length, and catch new files.
        def snapshot():
            entries = {}
            for tree in ('hass', 'storefront-mockup'):
                directory = ROOT / tree
                for path in (directory, *directory.rglob('*')):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        result = self.cli()
        self.assert_pass((result.returncode, result.stdout.splitlines()))
        self.assertEqual(result.stderr, '')
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # The report must not expose input text or mismatched values as extra output.
        self.copy_shop('>Link to this</a>')
        with patch.object(CHECK.validate, 'ORIGIN_UNKNOWN', 'Synthetic detail\nextra line'):
            code, lines = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(lines, ['rows 9', 'snippets 16', 'FAIL ui-literal-changed origin-unknown',
                                 'FAIL js-text-missing link', FAIL])

    def test_c6_fixture_pass(self):
        # The same real-source copy must pass before, and fail only summary after, a change.
        self.copy_shop()
        self.assert_pass(self.invoke())
        text = self.shop.read_text(encoding='utf-8')
        self.shop.write_text(text.replace('<summary>Meet the maker', ''), encoding='utf-8')
        self.assert_findings(self.invoke(), 'js-text-missing summary')

    def test_c7_live_pins(self):
        # The unpatched CLI must resolve the actual checkout, not the working directory.
        result = self.cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.stdout, f'rows 9\nsnippets 16\n{PASS}\n')
