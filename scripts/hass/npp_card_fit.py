#!/usr/bin/env python3
"""Check that a drawn card picture fits a phone and the chat media limit (offline).

Usage: npp_card_fit.py (--png FILE [--text FILE] | --dir DIR)

Picture (C1/C2): the file starts with the PNG signature from hass.media.KINDS and an
IHDR header, is no larger than hass.media.MAX_BYTES, and its pixel width fits the phone
capture. The phone width and device scale factor are read from hass/screenshot.cjs
(Playwright's default scale factor 1 applies when the script sets none). A card capture
(cardOnly) is an element screenshot inside that viewport, so it can never be wider than
phone width x scale; the phone catalog is one column, so a phone card is wider than half
of it (the real gallery draws 352 px cards in the 390 px viewport). Wider pictures (a
desktop page, a 2x capture) and narrower ones (thumbnails) fail.

Text (C3): the card text saved beside a capture (screenshot.cjs ``cardText``, the card's
innerText, one block per line). A price-shaped token must appear exactly once, and the
line just before it must carry the name: the site card renders the brand line, then the
name heading, then the price, so the name line is never the first line.

Directory (C4): every ``card-*.png`` with its ``card-*.txt`` when present, then a count.
Only file names and numbers are printed, never card text.
"""
import argparse
import os
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import media  # noqa: E402

SCREENSHOT = ROOT / 'hass' / 'screenshot.cjs'
PLAYWRIGHT_DEFAULT_SCALE = 1  # Playwright newPage() deviceScaleFactor when none is given
PRICE = re.compile(r'\$\s?\d+(?:,\d{3})*(?:\.\d{1,2})?'
                   r'|\b\d+\.\d{2}\b'
                   r'|\b\d+(?:\.\d{1,2})?\s?(?:dollars|bucks)\b', re.I)
LETTER = re.compile(r'[^\W\d_]')
HEADER = 24  # 8-byte signature + IHDR length/type + width + height


def phone_capture():
    """Return (css width, device scale factor) of the phone capture in screenshot.cjs."""
    source = SCREENSHOT.read_text(encoding='utf-8')
    found = re.findall(r'\bphone\s*:\s*\{\s*width\s*:\s*(\d+)\s*,', source)
    if len(set(found)) != 1:
        raise ValueError('phone viewport not found in screenshot.cjs')
    scales = set(re.findall(r'\bdeviceScaleFactor\s*:\s*(\d+(?:\.\d+)?)', source))
    if len(scales) > 1:
        raise ValueError('several device scale factors in screenshot.cjs')
    scale = float(scales.pop()) if scales else PLAYWRIGHT_DEFAULT_SCALE
    return int(found[0]), scale


def png_problems(path, width, scale):
    """FAIL reasons for one picture (empty when it fits)."""
    try:
        size = os.stat(path).st_size
        with open(path, 'rb') as fh:
            head = fh.read(HEADER)
    except OSError:
        return ['unreadable']
    problems = []
    signature = media.KINDS['png']
    if not head.startswith(signature) or head[len(signature):len(signature) + 8] != b'\x00\x00\x00\x0dIHDR':
        problems.append('not-png')
    else:
        drawn = struct.unpack('>I', head[16:20])[0]
        widest = int(width * scale)
        if not widest // 2 < drawn <= widest:
            problems.append(f'width {drawn} (phone {widest // 2 + 1}-{widest})')
    if size > media.MAX_BYTES:
        problems.append(f'too-big {size} > {media.MAX_BYTES}')
    return problems


def text_problems(path):
    """FAIL reasons for the card text: exactly one price, with the name line before it."""
    try:
        text = Path(path).read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        return ['text-unreadable']
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    hits = [(i, m) for i, line in enumerate(lines) for m in PRICE.finditer(line)]
    if len(hits) != 1:
        return [f'price-count {len(hits)}']
    # Card order is brand line, name heading, price: the name is the line before the
    # price and is never the first line (an empty name leaves the brand there).
    i = hits[0][0]
    return [] if i >= 2 and LETTER.search(lines[i - 1]) else ['no-name']


def check_one(png, text, width, scale):
    return png_problems(png, width, scale) + (text_problems(text) if text is not None else [])


def main(argv=None):
    parser = argparse.ArgumentParser(description='Check a drawn card fits a phone and the media limit.')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--png', type=Path, help='one card picture')
    group.add_argument('--dir', type=Path, help='gallery folder of card-*.png (and card-*.txt)')
    parser.add_argument('--text', type=Path, help='card text saved beside --png')
    args = parser.parse_args(argv)
    if args.text is not None and args.png is None:
        parser.error('--text needs --png')
    try:
        width, scale = phone_capture()
    except (OSError, UnicodeError, ValueError):
        print('FAIL phone-capture-unreadable')
        print('FAIL npp_card_fit')
        return 1
    if args.png is not None:
        problems = check_one(args.png, args.text, width, scale)
        for problem in problems:
            print(f'FAIL {problem}')
    else:
        cards = sorted(args.dir.glob('card-*.png')) if args.dir.is_dir() else []
        problems, passed, texts = [], 0, 0
        if not cards:
            print('FAIL no-cards')
            problems.append('no-cards')
        for card in cards:
            text = card.with_suffix('.txt')
            text = text if text.is_file() else None
            texts += text is not None
            found = check_one(card, text, width, scale)
            passed += not found
            for problem in found:
                print(f'FAIL {card.name} {problem}')
                problems.append(problem)
            if not found:
                print(f'PASS {card.name}')
        print(f'checked {len(cards)} passed {passed} failed {len(cards) - passed} with-text {texts}')
    print('FAIL npp_card_fit' if problems else 'PASS npp_card_fit')
    return int(bool(problems))


if __name__ == '__main__':
    sys.exit(main())
