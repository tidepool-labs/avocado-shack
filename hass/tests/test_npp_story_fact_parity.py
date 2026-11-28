"""Offline CLI contract tests for the S4/S5 maker-fact comparison."""

import importlib.util
import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_story_fact_parity.py'
PASS = 'PASS npp_story_fact_parity'
FAIL = 'FAIL npp_story_fact_parity'
FOUNDING_FIXTURE = (('founded', '1990', '2026-11-21'),)


def snapshot():
    files = {}
    for name in ('hass', 'storefront-mockup'):
        tree = ROOT / name
        for path in (tree, *tree.rglob('*')):
            info = path.lstat()
            files[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return files


class StoryFactParityTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.cwd = temporary.name

    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args], cwd=self.cwd,
                              capture_output=True, text=True, timeout=10)

    def load_script(self):
        spec = importlib.util.spec_from_file_location('npp_story_fact_parity', SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(module)
        return module

    def run_main(self, module):
        with redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
            code = module.main([])
        self.assertEqual(stderr.getvalue(), '')
        return code, stdout.getvalue().splitlines()

    def test_c1_full_pass(self):
        # An unconditional FAIL trailer would break a mismatch-free run.
        module = self.load_script()
        with patch.object(module, 'FACTS', (('makes', 'jam', '2026-11-21'),)):
            code, lines = self.run_main(module)
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertFalse(any(line.startswith('FAIL ') for line in lines))

    def test_c2_findings_trailer(self):
        # An informational-only report would return success despite a finding.
        result = self.run_cli()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual(result.stdout.splitlines().count(FAIL), 1)

    def test_c2_1_kept_unbound(self):
        # Do not hardcode positions, group diagnostics at the end, or report a
        # fact that both stages refuse (the 2027 date on a page read in 2026).
        module = self.load_script()
        facts = (
            ('makes', 'jams, jellies and honey', '2026-11-21'),
            ('founded', '2027', '2026-11-21'),
            ('founded', '2027', '2027-01-15'),
        )
        with patch.object(module, 'FACTS', facts):
            code, lines = self.run_main(module)
        self.assertEqual(code, 1)
        self.assertEqual(lines, [
            'fact 01 s4=kept s5=unbound',
            'FAIL kept-unbound 01',
            'fact 02 s4=refused s5=unbound',
            'fact 03 s4=kept s5=unbound',
            'FAIL kept-unbound 03',
            FAIL,
        ])

    def test_c2_2_check_error(self):
        # A checker exception must not leak its text or get silently skipped.
        module = self.load_script()
        for owner, name in ((module.research, 'parse_page'), (module.research, '_check'),
                            (module.copy.Writer, 'bindings')):
            with self.subTest(step=name), patch.object(module, 'FACTS', FOUNDING_FIXTURE), \
                    patch.object(owner, name, side_effect=RuntimeError('synthetic exception')):
                code, lines = self.run_main(module)
                self.assertEqual(code, 1)
                self.assertEqual(lines, ['FAIL check-error', FAIL])

    def test_c3_usage_exit_2(self):
        # Even argparse's usual special tokens are not valid inputs here.
        for arg in ('unexpected', '--unknown', '--help', '--'):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.startswith('usage:'))

    def test_c4_read_only(self):
        # Catch cache files or an accidental writer touching either source tree.
        before = snapshot()
        result = self.run_cli()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Extra debug output or raw fixture values are not part of the report.
        result = self.run_cli()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, '')
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        for line in lines[:-1]:
            self.assertRegex(line, r'^(?:fact \d{2} s4=(?:kept|refused) s5=(?:bound|unbound)'
                                  r'|FAIL kept-unbound \d{2}|FAIL check-error)$')

    def test_c6_fixture(self):
        # Replacing FACTS must change the run, not just the displayed count.
        module = self.load_script()
        with patch.object(module, 'FACTS', FOUNDING_FIXTURE):
            code, lines = self.run_main(module)
        self.assertEqual(code, 0)
        self.assertEqual(lines, ['fact 01 s4=kept s5=bound', PASS])

    def test_c7_live_pins(self):
        # Pin the observed defaults so rule drift cannot hide either mismatch.
        result = self.run_cli()
        self.assertEqual(result.returncode, 1, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        facts = [line for line in lines if line.startswith('fact ')]
        self.assertEqual(len(facts), 9)
        self.assertTrue(all(' s4=kept ' in line for line in facts))
        self.assertIn('fact 03 s4=kept s5=unbound', facts)
        self.assertIn('fact 05 s4=kept s5=bound', facts)
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')],
                         ['FAIL kept-unbound 03', 'FAIL kept-unbound 06'])


if __name__ == '__main__':
    unittest.main()
