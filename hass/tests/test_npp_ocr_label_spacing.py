"""Offline CLI contracts for the photo stage's OCR label-word handoff."""

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
SCRIPT = ROOT / 'scripts/hass/npp_ocr_label_spacing.py'
PASS = 'PASS npp_ocr_label_spacing'
FAIL = 'FAIL npp_ocr_label_spacing'


def snapshot():
    result = {}
    for tree in (ROOT / 'hass', ROOT / 'storefront-mockup'):
        for path in (tree, *tree.rglob('*')):
            info = path.lstat()
            result[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return result


class NppOcrLabelSpacingTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('npp_ocr_label_spacing', SCRIPT)
        assert spec is not None and spec.loader is not None
        self.script = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(self.script)

    def invoke(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.script.main([])
        self.assertEqual(stderr.getvalue(), '')
        return code, stdout.getvalue().splitlines()

    def cli(self, directory, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args],
                              cwd=directory, capture_output=True, text=True, timeout=20)

    def test_c1_full_pass(self):
        # An unconfirmed, unpassed amount is informational, not a lost label word.
        with patch.multiple(self.script, OCR='Honey', WORDS=('12 oz', 'Honey')):
            code, lines = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertIn('word 01 confirmed=no passed=no', lines[:-1])

    def test_c2_findings_trailer(self):
        # A finding must not yield exit 0 or end the report without a FAIL trailer.
        with patch.multiple(self.script, OCR='12\noz', WORDS=('12 oz',)):
            code, lines = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertIn('FAIL label-word-lost 01', lines[:-1])

    def test_c2_1_label_word_lost(self):
        # An isolated newline split and a spacing mismatch must both be reported, in order.
        with patch.multiple(self.script, OCR='16  fl oz\nHoney\n12\noz',
                            WORDS=('12 oz', 'Honey', '16 fl oz')):
            code, lines = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(lines, [
            'word 01 confirmed=yes passed=no',
            'word 02 confirmed=yes passed=yes',
            'word 03 confirmed=yes passed=no',
            'FAIL label-word-lost 01',
            'FAIL label-word-lost 03',
            FAIL,
        ])

    def test_c2_2_not_reached(self):
        # Returning before choose is not the same as choose receiving an empty list.
        with patch.object(self.script.stages.ProductionStages, '_picture', return_value=None):
            code, lines = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(lines, ['FAIL not-reached', FAIL])

    def test_c2_3_check_error(self):
        # A failed stage must not leak its exception or leave either fake installed.
        picture = self.script.picture
        originals = (picture.read_text, picture.choose)
        with patch.object(self.script.private_numbers, 'literal_spans',
                          side_effect=ValueError('synthetic error detail')):
            code, lines = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(lines, ['FAIL check-error', FAIL])
        self.assertIs(picture.read_text, originals[0])
        self.assertIs(picture.choose, originals[1])

    def test_c3_usage_exit_2(self):
        # Even argparse's usual help option is disallowed by the no-arguments CLI.
        with TemporaryDirectory() as directory:
            for arg in ('extra', '--unknown', '-h', '--help', '--'):
                with self.subTest(arg=arg):
                    result = self.cli(directory, arg)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, '')  # No last stdout line on usage errors.
                    self.assertTrue(result.stderr.startswith('usage: '))
                    self.assertIn('error: unrecognized arguments:', result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # A real reader/chooser could write sidecars under these trees or the working directory.
        with TemporaryDirectory() as directory:
            before = snapshot()
            result = self.cli(directory)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout.splitlines()[-1], FAIL)
            self.assertEqual(snapshot(), before)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_c5_output_shape(self):
        # Debug logging or echoing literal label text would violate the output protocol.
        with TemporaryDirectory() as directory:
            result = self.cli(directory)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, '')
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        for line in lines[:-1]:
            self.assertRegex(line, r'^(word [0-9]{2} confirmed=(yes|no) passed=(yes|no)'
                                    r'|FAIL (label-word-lost [0-9]{2}|not-reached|check-error))$')

    def test_c6_fixture(self):
        # Exact matches are handed to choose; neither stub should survive success.
        picture = self.script.picture
        originals = (picture.read_text, picture.choose)
        with patch.multiple(self.script, OCR='Honey 12 oz', WORDS=('12 oz', 'Honey')):
            code, lines = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(lines, ['word 01 confirmed=yes passed=yes',
                                 'word 02 confirmed=yes passed=yes', PASS])
        self.assertIs(picture.read_text, originals[0])
        self.assertIs(picture.choose, originals[1])

    def test_c7_live_pins(self):
        # The raw handoff loses the double-space phrase, not the exact 16 fl oz match.
        code, lines = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        words = [line for line in lines if line.startswith('word ')]
        self.assertEqual(len(words), 4)
        self.assertIn('word 02 confirmed=yes passed=no', words)
        self.assertIn('word 03 confirmed=yes passed=yes', words)
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')],
                         ['FAIL label-word-lost 02'])
