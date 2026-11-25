#!/usr/bin/env python3
"""Side-by-side page of delivered card versions and their gallery references, for a person to look at.

  demo_version_gallery.py --evidence EVIDENCE.json --delivered DIR --references DIR --out NEW_DIR
                          [--checkout SHA] [--case 01 ...]

EVIDENCE is the demo bundle's evidence.json (npp_demo_bundle / npp_demo_acceptance schema):
  {checkout, replay_sha256, deliveries: [{id, variant, n, state, png_sha256, attachment_sha256}],
   reference_cards: [{id, png_sha256}]}
DELIVERED holds the chat card bytes, one file per version, named case-<NN><variant>-v<n>.png
(for example case-01-v2.png or case-18a-v1.png). REFERENCES is the bundle's gallery directory
(card-<NN>.png).

For every case it shows chat v1, chat v2 and the gallery reference side by side:
  delivered       a confirmed delivery row whose attachment equals the frozen card, and a file with those
                  exact bytes. Only these are drawn.
  missing         the delivery row exists but the file does not; shown as unavailable.
  not delivered   no confirmed delivery row. A file without a row is never shown (no inferred delivery).
  refused         the file's bytes are not the delivered bytes (swapped, edited or not a PNG the pinned Pillow
                  decodes completely), the image is outside the preview envelope (outside-envelope: too large
                  or interlaced), or the file is a link or not a regular file. Any refusal makes the command exit 1.
The gallery reference is a v1 render; a v2 reference does not exist and the page says so.

Read-only on its inputs. Writes index.html, receipt.json and copies of the shown PNGs into a new or empty
directory outside any Git worktree. This is for looking, not scoring: it does not count a pass, prove
acceptance, approval, attendance or a live listing, and it makes no network call.
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import zlib
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.hass.npp_card_gallery import CASE_IDS, _output_path  # noqa: E402
from scripts.hass.npp_demo_acceptance import decode, digest  # noqa: E402

PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
VARIANT = re.compile(r'[a-z0-9-]{1,24}')
VERSIONS = (1, 2)


class Hold(Exception):
    """The evidence itself cannot be read as one bundle; the message is a short fixed reason."""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def label(case_id, variant):
    return f'{case_id:02}{variant or ""}'


def read_evidence(raw, checkout=None):
    """Return (checkout, deliveries {(id, variant, n): row}, references {id: sha})."""
    try:
        evidence = decode(raw)
    except (ValueError, RecursionError):
        raise Hold('evidence-unreadable') from None
    head = evidence.get('checkout')
    if not digest(head, 40):
        raise Hold('evidence-checkout')
    if checkout is not None and checkout != head:
        raise Hold('evidence-checkout-mismatch')
    rows, refs = evidence.get('deliveries'), evidence.get('reference_cards')
    if not isinstance(rows, list) or not isinstance(refs, list):
        raise Hold('evidence-shape')
    deliveries = {}
    for row in rows:
        if not isinstance(row, dict):
            raise Hold('evidence-shape')
        case_id, variant, n = row.get('id'), row.get('variant'), row.get('n')
        if (type(case_id) is not int or not 1 <= case_id <= 99 or type(n) is not int or n < 1
                or (variant is not None and not (isinstance(variant, str) and VARIANT.fullmatch(variant)))):
            raise Hold('evidence-identity')
        key = (case_id, variant, n)
        if key in deliveries:
            raise Hold('evidence-duplicate-delivery')
        deliveries[key] = row
    references = {}
    for row in refs:
        if not isinstance(row, dict) or row.get('id') not in CASE_IDS or not digest(row.get('png_sha256')):
            raise Hold('evidence-reference')
        if row['id'] in references:
            raise Hold('evidence-duplicate-reference')
        references[row['id']] = row['png_sha256']
    return head, deliveries, references


def confirmed(row):
    """The delivered bytes of a row, or None when the row does not prove a confirmed chat delivery."""
    png = row.get('png_sha256')
    if row.get('state') == 'confirmed' and digest(png) and row.get('attachment_sha256') == png:
        return png
    return None


# Envelope for a chat card or gallery reference. Real ones are non-interlaced phone renders (all 87 PNGs tracked in
# the repo are non-interlaced; the largest is 1440 x 3190, 4.6 M pixels, 3.1 MB). Anything outside it is refused
# from the file size or the IHDR alone, before one image byte is decompressed, so a small file cannot claim a huge
# image and no size arithmetic can overflow.
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_SIDE = 8192
MAX_PIXELS = 8 * 1024 * 1024
INFLATE_STEP = 1 << 20
# PNG colour type -> (samples per pixel, allowed bit depths)
PNG_COLOUR = {0: (1, (1, 2, 4, 8, 16)), 2: (3, (8, 16)), 3: (1, (1, 2, 4, 8)), 4: (2, (8, 16)), 6: (4, (8, 16))}


def ihdr_fields(body):
    """(width, height, depth, colour type, interlace) of a valid IHDR body, else None."""
    if len(body) != 13:
        return None
    width, height = int.from_bytes(body[:4], 'big'), int.from_bytes(body[4:8], 'big')
    depth, colour, compression, filtering, interlace = body[8:13]
    if not (0 < width <= 0x7fffffff and 0 < height <= 0x7fffffff):
        return None
    if colour not in PNG_COLOUR or depth not in PNG_COLOUR[colour][1] or compression or filtering or interlace > 1:
        return None
    return width, height, depth, colour, interlace


def outside_envelope(width, height, depth, colour, interlace):
    """Why an IHDR is outside the preview envelope, or None. Plain integer comparisons on bounded values."""
    if width > MAX_SIDE or height > MAX_SIDE or width * height > MAX_PIXELS:
        return 'too-large'
    return 'interlaced' if interlace else None


def inflated_size_is(stream_bytes, want):
    """True when the joined IDAT data is one complete zlib stream that inflates to exactly `want` bytes. Inflates in
    INFLATE_STEP pieces and stops as soon as the count passes `want`, so memory stays at one piece whatever the
    stream claims."""
    stream, total, pending = zlib.decompressobj(), 0, stream_bytes
    try:
        while True:
            piece = stream.decompress(pending, INFLATE_STEP)
            total += len(piece)
            if total > want:
                return False
            pending = stream.unconsumed_tail
            if not pending and len(piece) < INFLATE_STEP:
                break
    except zlib.error:
        return False
    return stream.eof and not stream.unused_data and total == want


def _pillow():
    """The pinned Pillow (CI installs Pillow==$PILLOW_VERSION, the host per docs/hass/PILLOW-HOST.md). Without it the
    command holds rather than showing a file it cannot decode."""
    try:
        from PIL import Image, ImageFile
    except ImportError:
        raise Hold('pillow-missing') from None
    if ImageFile.LOAD_TRUNCATED_IMAGES:
        raise Hold('pillow-accepts-truncated-images')
    return Image


def png_problem(data):
    """None if `data` is a complete PNG inside the preview envelope, else why not. The eight-byte signature alone
    proves nothing. In order:
      1. framing: 4-byte length, 4-letter type, data, CRC-32 over type+data; IHDR first and once, at least one IDAT,
         PLTE for a palette image, IEND last with no bytes after it;
      2. envelope: file size, width, height, pixel count and non-interlaced, from the IHDR alone;
      3. size: the joined IDAT data is one complete zlib stream holding exactly the IHDR's scanlines (one filter
         byte plus the packed pixels per row), counted in bounded pieces;
      4. pixels: the pinned Pillow, a maintained decoder, reads it as a PNG of the IHDR's size and decodes every
         scanline (an undefined filter type or broken stream is refused).
    Raises Hold without Pillow."""
    if len(data) > MAX_FILE_BYTES:
        return 'too-large'
    if not data.startswith(PNG_MAGIC):
        return 'signature'
    pos, chunks, idat, header = len(PNG_MAGIC), [], [], None
    while pos < len(data):
        if len(data) - pos < 12:
            return 'truncated-chunk'
        length = int.from_bytes(data[pos:pos + 4], 'big')
        kind = data[pos + 4:pos + 8]
        end = pos + 8 + length
        if length > 0x7fffffff or end + 4 > len(data):
            return 'truncated-chunk'
        if not (kind.isascii() and kind.isalpha()):
            return 'bad-chunk-type'
        body = data[pos + 8:end]
        if int.from_bytes(data[end:end + 4], 'big') != zlib.crc32(kind + body) & 0xffffffff:
            return 'bad-crc'
        chunks.append(kind)
        if kind == b'IHDR':
            header = ihdr_fields(body)
            if header is None:
                return 'bad-ihdr'
        elif kind == b'IDAT':
            idat.append(body)
        pos = end + 4
        if kind == b'IEND':
            break
    if header is None or not chunks or chunks[0] != b'IHDR' or chunks.count(b'IHDR') != 1:
        return 'no-ihdr'
    if not idat:
        return 'no-idat'
    if chunks[-1] != b'IEND' or pos != len(data):
        return 'no-iend' if chunks[-1] != b'IEND' else 'bytes-after-iend'
    if header[3] == 3 and b'PLTE' not in chunks:
        return 'no-plte'
    outside = outside_envelope(*header)
    if outside:
        return outside
    width, height, depth, colour, _ = header
    want = height * (1 + (width * PNG_COLOUR[colour][0] * depth + 7) // 8)
    if not inflated_size_is(b''.join(idat), want):
        return 'bad-image-data'
    image_module = _pillow()
    try:
        with image_module.open(io.BytesIO(data), formats=['PNG']) as image:
            if image.format != 'PNG' or image.size != (width, height):
                return 'bad-image-data'
            image.load()
    except Exception:  # noqa: BLE001 - any decoder failure (OSError, ValueError, SyntaxError, zlib, bomb) is a refusal
        return 'bad-image-data'
    return None


def read_png(path):
    """(bytes, None) for a regular non-link PNG file inside the preview envelope that passes png_problem; (None,
    reason) otherwise; (None, None) if absent. A file larger than MAX_FILE_BYTES is refused from its size without
    being read; reason is 'outside-envelope' (too large or interlaced) or 'not-a-png' (anything else)."""
    if not os.path.lexists(path):
        return None, None
    if path.is_symlink() or not path.is_file():
        return None, 'not-a-regular-file'
    if path.stat().st_size > MAX_FILE_BYTES:
        return None, 'outside-envelope'
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as handle:
        data = handle.read(MAX_FILE_BYTES + 1)
    problem = png_problem(data)
    if problem:
        return None, 'outside-envelope' if problem in ('too-large', 'interlaced') else 'not-a-png'
    return data, None


def build(evidence_raw, delivered_dir, references_dir, *, checkout=None, cases=None):
    """Return (head, rows, files); rows are per case with one cell per version plus the reference."""
    head, deliveries, references = read_evidence(evidence_raw, checkout)
    expected = {key: confirmed(row) for key, row in deliveries.items()}
    owner = {}
    for key, png in expected.items():
        if png is not None:
            owner.setdefault(png, key)
    identities = {(case_id, variant) for case_id, variant, _ in deliveries}
    identities |= {(int(card_id), None) for card_id in references}
    if cases is not None:
        identities = {item for item in identities if f'{item[0]:02}' in cases}
    rows, files = [], {}
    for case_id, variant in sorted(identities, key=lambda item: (item[0], item[1] or '')):
        name = label(case_id, variant)
        cells = []
        for n in VERSIONS:
            key = (case_id, variant, n)
            path = delivered_dir / f'case-{name}-v{n}.png'
            data, problem = read_png(path)
            want = expected.get(key)
            cell: dict = {'version': n}
            if problem:
                cell.update(status='refused', reason=problem)
            elif key not in deliveries or want is None:
                # No confirmed row: never show the file, whatever it contains.
                cell.update(status='not delivered', reason='no-confirmed-delivery' if key in deliveries
                            else 'no-delivery-row', file_ignored=data is not None)
            elif data is None:
                cell.update(status='missing', reason='delivered-file-absent', png_sha256=want)
            elif sha256(data) != want:
                other = owner.get(sha256(data))
                reason = f'bytes-of-{label(other[0], other[1])}-v{other[2]}' if other else 'bytes-differ'
                cell.update(status='refused', reason=reason, png_sha256=want)
            else:
                out_name = f'chat-{name}-v{n}.png'
                files[out_name] = data
                cell.update(status='delivered', png_sha256=want, file=out_name)
            cells.append(cell)
        reference = {'status': 'no reference', 'reason': 'no-gallery-card'}
        card_id = f'{case_id:02}'
        if variant is None and card_id in references:
            data, problem = read_png(references_dir / f'card-{card_id}.png')
            want = references[card_id]
            if problem:
                reference = {'status': 'refused', 'reason': problem}
            elif data is None:
                reference = {'status': 'missing', 'reason': 'reference-file-absent', 'png_sha256': want}
            elif sha256(data) != want:
                reference = {'status': 'refused', 'reason': 'bytes-differ', 'png_sha256': want}
            else:
                out_name = f'reference-{card_id}.png'
                files[out_name] = data
                reference = {'status': 'shown', 'png_sha256': want, 'file': out_name}
        rows.append({'id': case_id, 'variant': variant, 'versions': cells, 'reference': reference})
    return head, rows, files


def counts(rows):
    tally = {}
    for row in rows:
        for cell in row['versions']:
            tally[f"v{cell['version']} {cell['status']}"] = tally.get(f"v{cell['version']} {cell['status']}", 0) + 1
        tally[f"reference {row['reference']['status']}"] = tally.get(f"reference {row['reference']['status']}", 0) + 1
    return dict(sorted(tally.items()))


def refused(rows):
    return any(cell['status'] == 'refused' for row in rows for cell in (*row['versions'], row['reference']))


def _cell(title, cell):
    body = f'<img src="{escape(cell["file"])}" alt="{escape(title)}">' if cell.get('file') else ''
    reason = f' ({escape(cell["reason"])})' if cell.get('reason') else ''
    sha = f'<p><code>{escape(cell["png_sha256"])}</code></p>' if cell.get('png_sha256') else ''
    return (f'<article class="{escape(cell["status"].replace(" ", "-"))}"><h3>{escape(title)}</h3>{body}'
            f'<p><b>{escape(cell["status"])}</b>{reason}</p>{sha}</article>')


PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'">
<title>Hass card versions side by side</title>
<style>body{font:1rem system-ui;margin:1rem auto;padding:0 1rem;max-width:72rem}
.row{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem}
article{background:#f4f3ee;padding:.75rem;overflow-wrap:anywhere}img{max-width:100%;height:auto}
.refused{background:#f8d7d3}.missing,.not-delivered,.no-reference{background:#eceae4;color:#555}
@media(max-width:40rem){.row{grid-template-columns:1fr}}</style>
<h1>Hass card versions side by side</h1>
<p>Only chat cards with a confirmed delivery and matching bytes are drawn. The gallery reference is a v1
render; no v2 reference exists. For looking only: this is not a score, an approval or a live listing.</p>
'''


def render(head, rows):
    parts = [PAGE, f'<p>Checkout <code>{escape(head)}</code></p>']
    for row in rows:
        name = label(row['id'], row['variant'])
        cells = ''.join(_cell(f'Chat v{cell["version"]}', cell) for cell in row['versions'])
        cells += _cell('Gallery reference (v1 render)', row['reference'])
        parts.append(f'<section><h2>Case {escape(name)}</h2><div class="row">{cells}</div></section>')
    return ''.join(parts) + '\n'


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Side-by-side page of delivered card versions and references.')
    parser.add_argument('--evidence', type=Path, required=True, help="the demo bundle's evidence.json")
    parser.add_argument('--delivered', type=Path, required=True, help='chat card files case-<NN><variant>-v<n>.png')
    parser.add_argument('--references', type=Path, required=True, help="the bundle's gallery directory")
    parser.add_argument('--out', type=Path, required=True, help='new or empty directory outside Git')
    parser.add_argument('--checkout', help='refuse evidence from any other checkout')
    parser.add_argument('--case', nargs='+', action='extend', help='case numbers to show, e.g. 01 18 (default: all)')
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        out = _output_path(args.out)
        evidence_raw = args.evidence.read_bytes()
        head, rows, files = build(evidence_raw, args.delivered, args.references, checkout=args.checkout,
                                  cases=None if args.case is None else {f'{int(c):02}' for c in args.case})
    except Hold as why:
        print(json.dumps({'status': 'hold', 'reasons': [str(why)]}, sort_keys=True))
        return 1
    except (OSError, ValueError) as why:
        print(json.dumps({'status': 'hold', 'reasons': [type(why).__name__]}, sort_keys=True))
        return 1
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    out.chmod(0o700)
    for name, data in files.items():
        write_private(out / name, data)
    receipt = {'checkout': head, 'evidence_sha256': sha256(evidence_raw), 'counts': counts(rows), 'rows': rows}
    write_private(out / 'receipt.json', json.dumps(receipt, sort_keys=True, indent=1).encode('utf-8'))
    write_private(out / 'index.html', render(head, rows).encode('utf-8'))
    status = 'refused' if refused(rows) else 'shown'
    print(json.dumps({'status': status, 'cases': len(rows), 'counts': counts(rows)}, sort_keys=True))
    return 1 if status == 'refused' else 0


if __name__ == '__main__':
    sys.exit(main())
