"""Offline contract tests for the storefront → S7 maker-count check."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_dom_maker_count_rule.py'
SPEC = importlib.util.spec_from_file_location('npp_dom_maker_count_rule', SCRIPT)
assert SPEC is not None and SPEC.loader is not None
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)
PASS = 'PASS npp_dom_maker_count_rule'
FAIL = 'FAIL npp_dom_maker_count_rule'
LIVE_COUNTS = [
    'count 0 verdict=card-copy',
    'count 1 verdict=card-copy',
    'count 2 verdict=ok',
    'count 3 verdict=ok',
    'count 4 verdict=card-copy',
    'count 5 verdict=card-copy',
    'count 6 verdict=card-copy',
    'count 7 verdict=card-copy',
]


class MakerCountRuleTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args], cwd=self.work,
                              capture_output=True, text=True, timeout=25)

    def run_main(self, code=1, trailer=FAIL):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = check.main([])
        self.assertEqual(result, code, stdout.getvalue())
        self.assertEqual(stderr.getvalue(), '')
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines

    def assert_findings(self, lines, *expected):
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')], list(expected))

    @contextmanager
    def storefront_edit(self, old, new):
        # Mutate a scratch copy, then run it through the same real Node boundary.
        site = ROOT / 'storefront-mockup'
        (self.work / 'script.js').write_bytes((site / 'script.js').read_bytes())
        source = (site / 'shop.js').read_text(encoding='utf-8')
        self.assertEqual(source.count(old), 1, old)
        (self.work / 'shop.js').write_text(source.replace(old, new), encoding='utf-8')
        with patch.object(check, 'SITE', self.work):
            yield

    def truthy_count_gate(self):
        original = check.validate._fixed_ui

        def allow_truthy(maker, count, organic):
            result = original(maker, count, organic)
            if maker and count:
                result[check.ROLE] = (f'See all {count} from {maker}',)
            return result

        return patch.object(check.validate, '_fixed_ui', allow_truthy)

    def assert_threshold_drift(self):
        with self.storefront_edit('makerCounts.get(p.producerKey)>=2?',
                                  'makerCounts.get(p.producerKey)>=3?'):
            lines = self.run_main()
        self.assert_findings(lines, 'FAIL storefront-drift 2')
        self.assertIn('storefront 2 buttons=0 verdict=ok', lines)
        self.assertEqual([line for line in lines if line.startswith('count ')], LIVE_COUNTS)

    def test_c1_full_pass(self):
        # A successful probe set must produce the CLI success trailer and exit 0.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # Multiple independent failures must not overwrite one another or the trailer.
        with self.truthy_count_gate(), self.storefront_edit('makerCounts.get(p.producerKey)>=2?',
                                                           'makerCounts.get(p.producerKey)>=3?'):
            self.assert_findings(self.run_main(), 'FAIL storefront-drift 2', 'FAIL count-allowed 1',
                                 'FAIL count-allowed 4', 'FAIL count-allowed 5', 'FAIL count-allowed 7')

    def test_c2_1_count_allowed(self):
        # Letting the string count through must be detected at its index, not its value.
        original = check.validate._fixed_ui

        def allow_string(maker, count, organic):
            result = original(maker, count, organic)
            if count == '2':
                result[check.ROLE] = ('See all 2 from Fixture Farm',)
            return result

        with patch.object(check.validate, '_fixed_ui', allow_string):
            self.assert_findings(self.run_main(), 'FAIL count-allowed 5')

    def test_c2_2_count_refused(self):
        # A stricter S7 rejects the real row and the independent synthetic row.
        original = check.validate._fixed_ui

        def refuse_two(maker, count, organic):
            result = original(maker, count, organic)
            if type(count) is int and count == 2:
                result[check.ROLE] = ()
            return result

        with patch.object(check.validate, '_fixed_ui', refuse_two):
            lines = self.run_main()
        self.assert_findings(lines, 'FAIL storefront-drift 2', 'FAIL count-refused 2')
        self.assertIn('storefront 2 buttons=1 verdict=card-copy', lines)

    def test_c2_3_control_broken(self):
        # Kill each control independently: licensing a nameless maker, or
        # requiring count metadata where no button was rendered.
        fixed_ui = check.validate._fixed_ui

        def assume_maker(maker, count, organic):
            return fixed_ui(maker or 'Fixture Farm', count, organic)

        with patch.object(check.validate, '_fixed_ui', assume_maker):
            self.assert_findings(self.run_main(), 'FAIL control-broken')

        dom_problem = check.validate.dom_problem

        def require_count(nodes, *args, **kwargs):
            verdict = dom_problem(nodes, *args, **kwargs)
            if verdict is None and kwargs['maker_count'] is None and len(nodes) == 2:
                return 'card-copy'
            return verdict

        with patch.object(check.validate, 'dom_problem', require_count):
            self.assert_findings(self.run_main(), 'FAIL storefront-drift 0', 'FAIL control-broken')

    def test_c2_4_check_error(self):
        # Unavailable/broken boundaries must fail closed without printing raw errors.
        for boundary in (
            patch.object(check.validate, 'dom_problem', side_effect=RuntimeError('fixture error detail')),
            patch.object(check.subprocess, 'run', return_value=subprocess.CompletedProcess(
                ['node'], 0, stdout='fixture invalid JSON', stderr='')),
            patch.object(check.subprocess, 'run', return_value=subprocess.CompletedProcess(
                ['node'], 0, stdout='["row", "row", "row"]', stderr='')),
            patch.object(check.subprocess, 'run', side_effect=FileNotFoundError('fixture absent node')),
            patch.object(check.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['node'], 15)),
            self.storefront_edit('<h3>${esc(p.name)}</h3>', '<h4>${esc(p.name)}</h4>'),
            self.storefront_edit('class="product-meta product-price"', 'class="product-meta"'),
        ):
            with boundary:
                self.assertEqual(self.run_main(), ['FAIL check-error', FAIL])

    def test_c2_5_storefront_drift(self):
        # The real renderer can break without changing any synthetic S7 verdict.
        self.assert_threshold_drift()
        for old, new in (
            ('type="button" class="text-link" data-from', 'type="submit" class="text-link" data-from'),
            ('type="button" class="text-link" data-from', 'type="button" class="other" data-from'),
            ('data-from="${esc(p.producerKey)}"', 'data-from="fixture-other"'),
            ('>See all ${makerCounts', '>Browse all ${makerCounts'),
            ('class="maker-story-content">${story?', 'class="other-content">${story?'),
        ):
            with self.subTest(drift=new), self.storefront_edit(old, new):
                self.assert_findings(self.run_main(), 'FAIL storefront-drift 2', 'FAIL storefront-drift 3')

    def test_c3_usage_exit_2(self):
        # argparse, not the probe runner, owns rejected arguments.
        for arg in ('extra', '--not-an-option'):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertIn('usage:', result.stderr)

    def test_c4_read_only(self):
        # A runner or bytecode cache written in the input trees changes this snapshot.
        def snapshot():
            result = {}
            for root in (ROOT / 'hass', ROOT / 'storefront-mockup'):
                for path in (root, *root.rglob('*')):
                    stat = path.lstat()
                    result[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
            return result

        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_c5_output_shape(self):
        # Failures must not print raw HTML, count inputs, or child diagnostics.
        with self.truthy_count_gate():
            lines = self.run_main()
        verdict = r'(?:ok|card-(?:text|price|contact|copy|number))'
        shape = (r'\A(?:storefront [0-3] buttons=[0-9]+ verdict=' + verdict
                 + r'|count [0-7] verdict=' + verdict
                 + r'|FAIL (?:count-(?:allowed|refused) [0-7]|control-broken|check-error'
                   r'|storefront-drift [0-3])|(?:PASS|FAIL) npp_dom_maker_count_rule)\Z')
        for line in lines:
            self.assertRegex(line, shape)

    def test_c6_fixture(self):
        # Break the two production boundaries separately and verify recovery after each.
        with self.truthy_count_gate():
            self.assert_findings(self.run_main(), 'FAIL count-allowed 1', 'FAIL count-allowed 4',
                                 'FAIL count-allowed 5', 'FAIL count-allowed 7')
        self.run_main(0, PASS)
        self.assert_threshold_drift()
        self.run_main(0, PASS)

    def test_c7_live_pins(self):
        # Pin the measured baseline; a hard-coded result misses the mutations above.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.stdout, '\n'.join([
            'storefront 0 buttons=0 verdict=ok',
            'storefront 1 buttons=0 verdict=ok',
            'storefront 2 buttons=1 verdict=ok',
            'storefront 3 buttons=1 verdict=ok',
            *LIVE_COUNTS, PASS, '',
        ]))
