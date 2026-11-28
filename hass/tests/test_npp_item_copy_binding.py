"""Offline CLI contract for the synthetic S3/S10 copy-binding replay."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_item_copy_binding.py'
PASS = 'PASS npp_item_copy_binding'
FAIL = 'FAIL npp_item_copy_binding'


def snapshot():
    result = {}
    for root in (ROOT / 'hass', ROOT / 'storefront-mockup'):
        for path in (root, *root.rglob('*')):
            info = path.lstat()
            result[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return result


class NppItemCopyBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('npp_item_copy_binding', SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def invoke(self, *args):
        with TemporaryDirectory() as root:
            return subprocess.run(
                [sys.executable, '-B', str(SCRIPT), *args],
                cwd=root, capture_output=True, text=True, timeout=15,
            )

    def run_main(self, *items):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(self.tool, 'ITEMS', items), redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        return code, stdout.getvalue().splitlines(), stderr.getvalue()

    def test_c1_full_pass(self):
        # A missing reading is informational, not a refused copy binding.
        code, lines, stderr = self.run_main('wildflower honey', '')
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(lines[:-1], ['item 01 s3=bound s10=bound', 'item 02 s3=none s10=none'])
        self.assertEqual(stderr, '')

    def test_c2_findings_trailer(self):
        # A later bound item must neither mask an earlier failure nor be skipped.
        code, lines, stderr = self.run_main('dill pickles!', 'wildflower honey')
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(lines[:-1], [
            'item 01 s3=unbound s10=bound', 'FAIL s3-unbound 01', 'item 02 s3=bound s10=bound',
        ])
        self.assertEqual(stderr, '')

    def test_c2_1_unbound(self):
        # Two unbound readings in one row must not be collapsed into one finding.
        code, lines, stderr = self.run_main('salt & pepper', "st. john's honey")
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')], [
            'FAIL s3-unbound 01', 'FAIL s10-unbound 01', 'FAIL s3-unbound 02',
        ])
        self.assertEqual(stderr, '')

    def test_c2_2_check_error(self):
        # A thrown reading or binding must not leak its text or pass as a missing name.
        for target, method in (
            (self.tool.label_reader, 'identity_text'),
            (self.tool.edits, 'read'),
            (self.tool.copy.Writer, 'bindings'),
        ):
            original = getattr(target, method)

            def fail_once(*args, **kwargs):
                if broken.call_count == 1:
                    raise RuntimeError('synthetic-private-marker')
                return original(*args, **kwargs)

            with self.subTest(method=method), patch.object(
                target, method, autospec=True, side_effect=fail_once,
            ) as broken:
                code, lines, stderr = self.run_main('wildflower honey', 'lemon-lime soda')
                self.assertEqual(code, 1)
                self.assertEqual(lines[-1], FAIL)
                self.assertEqual(lines[:-1], ['FAIL check-error', 'item 02 s3=bound s10=bound'])
                self.assertEqual(stderr, '')

    def test_c3_usage_exit_2(self):
        # Accepting options (even argparse's implicit help) would bypass the check.
        for arg in ('extra', '--unknown', '--help', '--'):
            with self.subTest(arg=arg):
                result = self.invoke(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')  # No last stdout line on usage errors.
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f'{SCRIPT.name}: error: unrecognized arguments: {arg}')

    def test_c4_read_only(self):
        # An accidental stage write can change either an existing file or a directory entry.
        before = snapshot()
        result = self.invoke()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug output must not expose any wording or add chatter to either stream.
        result = self.invoke()
        self.assertEqual(result.returncode, 1)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(result.stderr, '')
        allowed = re.compile(
            r'item [0-9]{2} s3=(?:bound|unbound|none) s10=(?:bound|unbound|none)'
            r'|FAIL (?:(?:s3|s10)-unbound [0-9]{2}|check-error)'
        )
        for line in lines[:-1]:
            self.assertIsNotNone(allowed.fullmatch(line), line)

    def test_c6_fixture(self):
        # Ignoring the configured ITEMS would replay the ten failing-base wordings.
        code, lines, stderr = self.run_main('wildflower honey')
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(lines[:-1], ['item 01 s3=bound s10=bound'])
        self.assertEqual(stderr, '')

    def test_c7_live_pins(self):
        # The real edit grammar/finance path differs from S3; using S3 for both
        # would add findings and miss the successful rename at position 10.
        result = self.invoke()
        self.assertEqual(result.returncode, 1)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        items = [line for line in lines if line.startswith('item ')]
        self.assertEqual(len(items), 10)
        self.assertEqual(items[3], 'item 04 s3=unbound s10=unbound')
        self.assertEqual(items[9], 'item 10 s3=unbound s10=bound')
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')], [
            'FAIL s3-unbound 02', 'FAIL s3-unbound 03', 'FAIL s3-unbound 04',
            'FAIL s10-unbound 04', 'FAIL s3-unbound 05', 'FAIL s3-unbound 08',
            'FAIL s3-unbound 10',
        ])


if __name__ == '__main__':
    unittest.main()
