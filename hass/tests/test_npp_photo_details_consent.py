"""Offline CLI and mutation checks for the NPP photo consent drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_photo_details_consent.py'
PASS = 'PASS npp_photo_details_consent'
FAIL = 'FAIL npp_photo_details_consent'
LIVE_LINES = [
    "case 0 sources=['Wildflower Honey', 'Cedar Row Apiary', '12 oz'] basis=None",
    "case 1 sources=[] basis=None",
    "case 2 sources=['Wildflower Honey', 'Cedar Row Apiary', '12 oz'] basis=None",
    "case 3 sources=['Wildflower Honey', 'Cedar Row Apiary', '12 oz', 'local'] basis=None",
    "case 4 sources=['Wildflower Honey', 'Cedar Row Apiary', '12 oz', 'raw'] basis=None",
    "case 5 sources=['glass jar', 'cedar lid'] basis=None",
    "case 6 sources=[] basis='basket'",
    "case 7 sources=[] basis='bundle'",
    "case 8 sources=[] basis=None",
    "case 9 sources=[] basis=None",
]


def drop_size_but_keep_refused_claims(got):
    if got.get('photo_confirmed') is False:
        return {}
    details = dict(got.get('photo_details') or {})
    details.pop('size', None)
    return details


def snapshot():
    result = {}
    for name in ('hass', 'storefront-mockup'):
        tree = ROOT / name
        for path in (tree, *tree.rglob('*')):
            stat = path.lstat()
            result[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return result


class PhotoDetailsConsentTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        # Restore the import path adjusted by the CLI's standalone bootstrap.
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(self.tool)

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, '-B', str(SCRIPT), *args], cwd=ROOT.parent,
            capture_output=True, text=True, timeout=10,
        )

    def assert_run(self, code, trailer):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = self.tool.main([])
        self.assertEqual(result, code)
        self.assertEqual(err.getvalue(), '')
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def run_size_mutation(self):
        with patch.object(self.tool.intake_simple, 'photo_details', drop_size_but_keep_refused_claims):
            return self.assert_run(1, FAIL)

    def test_c1_full_pass(self):
        # The standalone entrypoint must import and propagate success outside the repo cwd.
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # A fail-fast loop, grouped findings, or an unconditional PASS loses the report.
        lines = self.run_size_mutation()
        self.assertEqual(lines, [
            "case 0 sources=['Wildflower Honey', 'Cedar Row Apiary'] basis=None",
            'FAIL sources-changed 0',
            LIVE_LINES[1],
            "case 2 sources=['Wildflower Honey', 'Cedar Row Apiary'] basis=None",
            'FAIL sources-changed 2',
            "case 3 sources=['Wildflower Honey', 'Cedar Row Apiary', 'raw', 'local'] basis=None",
            'FAIL refused-text-public 3',
            'FAIL sources-changed 3',
            "case 4 sources=['Wildflower Honey', 'Cedar Row Apiary', 'raw', 'local'] basis=None",
            'FAIL refused-text-public 4',
            'FAIL sources-changed 4',
            *LIVE_LINES[5:],
        ])

    def test_c2_1_refused_text_public(self):
        # Bypassing consent must flag the full rejection and each distinct refused claim.
        with patch.object(self.tool.intake_simple, 'photo_details',
                          lambda got: dict(got.get('photo_details') or {})):
            lines = self.assert_run(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], [
            'FAIL refused-text-public 1', 'FAIL sources-changed 1',
            'FAIL refused-text-public 3', 'FAIL sources-changed 3',
            'FAIL refused-text-public 4', 'FAIL sources-changed 4',
        ])

    def test_c2_2_sources_changed(self):
        # Dropping size is drift even for plain and accepted photos without a refusal.
        lines = self.run_size_mutation()
        self.assertEqual([line for line in lines if line.startswith('FAIL sources-changed')], [
            'FAIL sources-changed 0', 'FAIL sources-changed 2',
            'FAIL sources-changed 3', 'FAIL sources-changed 4',
        ])

    def test_c2_3_check_error(self):
        # Neither repo call may leak exception text or continue to later cases on error.
        for name in ('public_sources', '_private_price_basis'):
            with self.subTest(name=name), patch.object(
                self.tool.intake_simple, name, side_effect=RuntimeError('synthetic error detail'),
            ) as check:
                self.assertEqual(self.assert_run(1, FAIL), ['FAIL check-error'])
                check.assert_called_once()

    def test_c3_usage_exit_2(self):
        # Argparse's help and bare delimiter must not turn arguments into a successful run.
        for args in [('extra',), ('--unknown',), ('--help',), ('--',)]:
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.startswith('usage: '))
                self.assertIn('error:', result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Incidental cache or report writes must not change either tree.
        before = snapshot()
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug output, extra blank lines, or an alternate serialization break the CLI format.
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.stdout, '\n'.join([*LIVE_LINES, PASS, '']))

    def test_c6_fixture(self):
        # The same mutation yields drift alone on two rows and both findings on two more.
        lines = self.run_size_mutation()
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], [
            'FAIL sources-changed 0', 'FAIL sources-changed 2',
            'FAIL refused-text-public 3', 'FAIL sources-changed 3',
            'FAIL refused-text-public 4', 'FAIL sources-changed 4',
        ])

    def test_c7_live_pins(self):
        # A hardcoded report must not pass; call through to both real functions for each row.
        intake = self.tool.intake_simple
        with patch.object(intake, 'public_sources', wraps=intake.public_sources) as sources, \
                patch.object(intake, '_private_price_basis', wraps=intake._private_price_basis) as basis:
            self.assertEqual(self.assert_run(0, PASS), LIVE_LINES)
        self.assertEqual(sources.call_args_list, [call({'intake': got}) for got in self.tool.CASES])
        self.assertEqual(basis.call_args_list, [call(got) for got in self.tool.CASES])
