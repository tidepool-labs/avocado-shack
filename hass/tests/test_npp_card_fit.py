"""Offline acceptance of the card fit CLI (HRM-23): fixture PNGs and card text only."""
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

from hass import media
from scripts.hass import npp_card_fit as fit

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts' / 'hass' / 'npp_card_fit.py'
WIDTH, SCALE = fit.phone_capture()
WIDEST = int(WIDTH * SCALE)
CARD = WIDEST - 38  # a cardOnly capture inside the phone page's side padding (352 of 390 today)
GOOD_TEXT = 'Example Maker\nTest Lentils\n$9.99 each\nBased in Exampletown\nA fictional fixture card.\nLink to this\n'


def png(width, height=4):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    rows = b''.join(b'\x00' + b'\xff' * width for _ in range(height))
    return (media.KINDS['png'] + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


class CardFitTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def write(self, name, data):
        path = self.dir / name
        path.write_bytes(data if isinstance(data, bytes) else data.encode('utf-8'))
        return path

    def sized(self, name, size):
        """A real PNG header padded (sparse) to exactly ``size`` bytes."""
        path = self.write(name, png(CARD))
        os.truncate(path, size)
        return path

    def run_cli(self, *args):
        done = subprocess.run([sys.executable, '-B', str(SCRIPT), *map(str, args)], cwd=ROOT,
                              capture_output=True, text=True, timeout=60)
        return done.returncode, done.stdout.splitlines()

    def assert_pass(self, *args):
        code, lines = self.run_cli(*args)
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines[-1], 'PASS npp_card_fit')
        self.assertFalse([line for line in lines if line.startswith('FAIL')], lines)
        return lines

    def assert_fail(self, expected, *args):
        code, lines = self.run_cli(*args)
        self.assertEqual(code, 1, lines)
        self.assertEqual(lines[-1], 'FAIL npp_card_fit')
        for line in expected:
            self.assertIn(line, lines)
        return lines

    def test_c1_pass_phone_card_and_full_phone_width(self):
        for width in (CARD, WIDEST, WIDEST // 2 + 1):
            with self.subTest(width=width):
                self.assert_pass('--png', self.write(f'card-{width}.png', png(width)))

    def test_c1_pass_at_exact_media_limit(self):
        self.assert_pass('--png', self.sized('card-limit.png', media.MAX_BYTES))

    def test_c1_pass_constants_come_from_screenshot_cjs(self):
        real = (ROOT / 'hass' / 'screenshot.cjs').read_text(encoding='utf-8')
        self.assertIn(f'phone:{{width:{WIDTH},', real)
        cases = (("const VIEWPORTS={phone:{width:400,height:900}};", (400, 1)),
                 ("const VIEWPORTS={phone:{width:400,height:900}};newPage({deviceScaleFactor:2})", (400, 2.0)))
        for source, expected in cases:
            with self.subTest(expected=expected):
                path = self.write('screenshot.cjs', source)
                with patch.object(fit, 'SCREENSHOT', path):
                    self.assertEqual(fit.phone_capture(), expected)
        path = self.write('screenshot.cjs', 'const VIEWPORTS={desktop:{width:1280,height:900}};')
        with patch.object(fit, 'SCREENSHOT', path), self.assertRaises(ValueError):
            fit.phone_capture()

    def test_c2_fail_not_png(self):
        path = self.write('card.png', b'\xff\xd8\xff' + png(CARD)[3:])
        self.assert_fail(['FAIL not-png'], '--png', path)

    def test_c2_truncated_header_fails_and_directory_continues(self):
        complete = png(CARD)
        for length in range(16, 24):
            with self.subTest(length=length):
                path = self.write('card-01.png', complete[:length])
                self.assert_fail(['FAIL not-png'], '--png', path)
                self.write('card-02.png', complete)
                self.assert_fail(['FAIL card-01.png not-png', 'PASS card-02.png',
                                  'checked 2 passed 1 failed 1 with-text 0'], '--dir', self.dir)

    def test_c2_fail_wrong_width(self):
        for width in (WIDEST + 1, 1280, WIDEST // 2):
            with self.subTest(width=width):
                path = self.write(f'card-{width}.png', png(width))
                self.assert_fail([f'FAIL width {width} (phone {WIDEST // 2 + 1}-{WIDEST})'], '--png', path)

    def test_c2_fail_too_big(self):
        path = self.sized('card-big.png', media.MAX_BYTES + 1)
        self.assert_fail([f'FAIL too-big {media.MAX_BYTES + 1} > {media.MAX_BYTES}'], '--png', path)

    def test_c2_fail_missing_file(self):
        self.assert_fail(['FAIL unreadable'], '--png', self.dir / 'card-none.png')

    def test_c3_text_name_and_one_price_pass(self):
        lines = self.assert_pass('--png', self.write('card-01.png', png(CARD)),
                                 '--text', self.write('card-01.txt', GOOD_TEXT))
        self.assertNotIn('Test Lentils', '\n'.join(lines))  # card text is never echoed

    def test_c3_text_price_count(self):
        image = self.write('card-01.png', png(CARD))
        for count, text in ((0, GOOD_TEXT.replace('$9.99 each\n', '')),
                            (2, GOOD_TEXT.replace('fictional', 'fictional $1.50 off')),
                            (2, GOOD_TEXT + 'Also 3.25 per jar\n')):
            with self.subTest(count=count, text=text):
                self.assert_fail([f'FAIL price-count {count}'], '--png', image,
                                 '--text', self.write('card-01.txt', text))

    def test_c3_text_no_name(self):
        image = self.write('card-01.png', png(CARD))
        for text in (GOOD_TEXT.replace('Test Lentils\n', ''), GOOD_TEXT.replace('Test Lentils', '1234'),
                     '$9.99 each\nA fictional fixture card.\n'):
            with self.subTest(text=text):
                self.assert_fail(['FAIL no-name'], '--png', image, '--text', self.write('card-01.txt', text))

    def test_c4_dir_checks_every_card_and_counts(self):
        self.write('card-01.png', png(CARD))
        self.write('card-01.txt', GOOD_TEXT)
        self.write('card-02.png', png(1280))
        self.write('card-03.png', png(WIDEST))
        self.write('card-03.txt', GOOD_TEXT + '$2.00\n')
        self.write('card-04.png', png(CARD))
        self.write('other.png', b'not a picture')  # not card-*.png: ignored
        self.write('index.html', '<p>gallery</p>')
        lines = self.assert_fail(['PASS card-01.png', 'FAIL card-02.png width 1280 (phone '
                                  f'{WIDEST // 2 + 1}-{WIDEST})', 'FAIL card-03.png price-count 2', 'PASS card-04.png',
                                  'checked 4 passed 2 failed 2 with-text 2'], '--dir', self.dir)
        self.assertFalse([line for line in lines if 'other.png' in line])

    def test_c4_dir_all_fit_passes(self):
        self.write('card-01.png', png(CARD))
        self.write('card-01.txt', GOOD_TEXT)
        self.write('card-02.png', png(CARD))
        lines = self.assert_pass('--dir', self.dir)
        self.assertEqual(lines[:-1], ['PASS card-01.png', 'PASS card-02.png', 'checked 2 passed 2 failed 0 with-text 1'])

    def test_c4_dir_without_cards_fails(self):
        self.write('index.html', '<p>gallery</p>')
        self.assert_fail(['FAIL no-cards', 'checked 0 passed 0 failed 0 with-text 0'], '--dir', self.dir)


if __name__ == '__main__':
    unittest.main()
