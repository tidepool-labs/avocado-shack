"""Offline CLI and live-function contract for the capture-binding drift guard."""

import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_captured_dom_binding.py'
PASS = 'PASS npp_captured_dom_binding'
FAIL = 'FAIL npp_captured_dom_binding'


class CapturedDomBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args],
                              cwd=self.tmp, capture_output=True, text=True, timeout=10)

    def load(self):
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        self.addCleanup(sys.path.__setitem__, slice(None), sys.path[:])
        spec.loader.exec_module(module)
        return module

    def run_main(self, module):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = module.main([])
        return code, stdout.getvalue(), stderr.getvalue()

    def assert_run(self, code, stdout, stderr, expected_code, trailer):
        lines = stdout.splitlines()
        self.assertEqual(code, expected_code, stderr)
        self.assertEqual(stderr, '')
        self.assertTrue(lines, 'missing stdout trailer')
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def assert_findings(self, module, *findings):
        lines = self.assert_run(*self.run_main(module), 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], list(findings))
        return lines

    def test_c1_full_pass(self):
        # A successful check must not carry the wrong exit status or trailer.
        run = self.cli()
        self.assert_run(run.returncode, run.stdout, run.stderr, 0, PASS)

    def test_c2_findings_trailer(self):
        # An early return could hide later findings or print the trailer too soon.
        module = self.load()
        actual = module.validate.captured_dom

        def regress(evidence, png, product):
            if product == 'p-other':
                return (['a'], None, None)
            if isinstance(png, str):
                raise RuntimeError('synthetic check failure')
            if isinstance(evidence, list):
                return (None, None, 2)
            return actual(evidence, png, product)

        with patch.object(module.validate, 'captured_dom', side_effect=regress):
            self.assert_findings(module, 'FAIL capture-used other-product',
                                 'FAIL check-error', 'FAIL capture-used not-dict')

    def test_c2_1_capture_used(self):
        # Checking only fragments, truthiness, or a fully accepted tuple misses partial use.
        module = self.load()
        with patch.object(module.validate, 'captured_dom', side_effect=[
            (['a'], 0, 2), ([], None, None), (None, 0, None), (None, None, 0),
            (['a'], None, None), (None, 1, None), (None, None, 2),
        ]):
            lines = self.assert_findings(
                module, 'FAIL capture-used other-bytes', 'FAIL capture-used other-product',
                'FAIL capture-used empty-product', 'FAIL capture-used text-png',
                'FAIL capture-used upper-hash', 'FAIL capture-used not-dict',
            )
        self.assertEqual([line for line in lines if line.startswith('capture ')], [
            'capture same used=yes', 'capture other-bytes used=yes',
            'capture other-product used=yes', 'capture empty-product used=yes',
            'capture text-png used=yes', 'capture upper-hash used=yes', 'capture not-dict used=yes',
        ])

    def test_c2_2_same_refused(self):
        # Unexpected data on the matching capture isn't a pass just because some data survived.
        module = self.load()
        for result in ((None, None, None), (['a'], 0, None)):
            with self.subTest(result=result):
                with patch.object(module.validate, 'captured_dom', side_effect=[
                    result, *[(None, None, None)] * 6,
                ]):
                    self.assert_findings(module, 'FAIL same-refused')

    def test_c2_3_check_error(self):
        # Do not echo exception details or turn an incomplete check into a pass.
        module = self.load()
        actual = module.validate.captured_dom

        def broken(evidence, png, product):
            if png == module.PNG + b'0':
                raise ValueError('synthetic-detail-not-for-output')
            return actual(evidence, png, product)

        with patch.object(module.validate, 'captured_dom', side_effect=broken):
            lines = self.assert_findings(module, 'FAIL check-error')
        self.assertNotIn('synthetic-detail-not-for-output', '\n'.join(lines))

    def test_c3_usage_exit_2(self):
        # Reject positional and option tokens (including argparse's usual help option).
        for arg in ('fixture', '--unknown', '-h', '--help', '--', ''):
            with self.subTest(arg=arg):
                run = self.cli(arg)
                self.assertEqual(run.returncode, 2)
                self.assertEqual(run.stdout, '')
                self.assertTrue(run.stderr.startswith('usage: '))
                self.assertIn('error: unrecognized arguments:', run.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Catch artifact creation and even same-length rewrites under either input tree.
        def snapshot():
            entries = {}
            for name in ('hass', 'storefront-mockup'):
                tree = ROOT / name
                for path in (tree, *tree.rglob('*')):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        run = self.cli()
        self.assert_run(run.returncode, run.stdout, run.stderr, 0, PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Unrequested debug text or a wrong case label/use marker breaks the line protocol.
        run = self.cli()
        lines = self.assert_run(run.returncode, run.stdout, run.stderr, 0, PASS)
        expected = [
            'capture same used=yes', 'capture other-bytes used=no',
            'capture other-product used=no', 'capture empty-product used=no',
            'capture text-png used=no', 'capture upper-hash used=no', 'capture not-dict used=no',
        ]
        self.assertEqual(lines, expected)

        module = self.load()
        actual = module.validate.captured_dom

        def missing_same(*args):
            fragments, price_index, _ = actual(*args)
            return fragments, price_index, None

        with patch.object(module.validate, 'captured_dom', side_effect=missing_same):
            lines = self.assert_run(*self.run_main(module), 1, FAIL)
        self.assertEqual(lines, [expected[0], 'FAIL same-refused', *expected[1:]])

    def test_c6_fixture(self):
        # Make the real function see the evidence's product, bypassing only the product gate.
        module = self.load()
        actual = module.validate.captured_dom

        def ignoring_product(evidence, png, product):
            if isinstance(evidence, dict):
                product = evidence['productId']
            return actual(evidence, png, product)

        with patch.object(module.validate, 'captured_dom', side_effect=ignoring_product):
            self.assert_findings(module, 'FAIL capture-used other-product',
                                 'FAIL capture-used empty-product')

    def test_c7_live_pins(self):
        # Independent call inputs catch a missing/miswired probe; observe the unchanged rule.
        module = self.load()
        self.assert_run(*self.run_main(module), 0, PASS)
        png = b'\x89PNG\r\n\x1a\nfixture'
        digest = hashlib.sha256(png).hexdigest()
        evidence = {'pngSha256': digest, 'productId': 'p-fixture',
                    'fragments': ['a'], 'priceIndex': 0, 'makerCount': 2}
        actual = module.validate.captured_dom
        observed = []

        def record(*args):
            result = actual(*args)
            observed.append((args, result))
            return result

        with patch.object(module.validate, 'captured_dom', side_effect=record):
            self.assert_run(*self.run_main(module), 0, PASS)
        refused = (None, None, None)
        self.assertEqual(observed, [
            ((evidence, png, 'p-fixture'), (['a'], 0, 2)),
            ((evidence, png + b'0', 'p-fixture'), refused),
            ((evidence, png, 'p-other'), refused),
            ((evidence, png, ''), refused),
            ((evidence, png.decode('latin-1'), 'p-fixture'), refused),
            ((dict(evidence, pngSha256=digest.upper()), png, 'p-fixture'), refused),
            ((list(evidence.items()), png, 'p-fixture'), refused),
        ])
