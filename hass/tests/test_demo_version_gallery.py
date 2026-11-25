"""Synthetic tests for the side-by-side version page; never reads private recordings, replays or chat history."""
import hashlib
import io
import json
import os
import struct
import tempfile
import unittest
import zlib
from contextlib import redirect_stdout
from pathlib import Path

from scripts.hass import demo_version_gallery as gallery

HEAD = 'b' * 40


def png(seed):
    """A tiny valid PNG whose pixel bytes depend on `seed`; equal length for equal-length seeds."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    raw = b'\x00' + seed.encode().ljust(12, b'.')[:12]
    return (gallery.PNG_MAGIC + chunk(b'IHDR', struct.pack('>IIBBBBB', 4, 1, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def delivery(case_id, n, data, *, variant=None, state='confirmed', attachment=None):
    return {'id': case_id, 'variant': variant, 'n': n, 'state': state, 'png_sha256': sha(data),
            'attachment_sha256': sha(data) if attachment is None else attachment}


class Bundle:
    """A synthetic evidence.json, delivered-card directory and gallery directory in a temporary folder."""

    def __init__(self, root):
        self.root = Path(root)
        self.delivered, self.references = self.root / 'delivered', self.root / 'gallery'
        self.delivered.mkdir()
        self.references.mkdir()
        self.rows, self.cards = [], []

    def deliver(self, case_id, n, data, *, variant=None, write=True, **row):
        self.rows.append(delivery(case_id, n, data, variant=variant, **row))
        if write:
            (self.delivered / f'case-{case_id:02}{variant or ""}-v{n}.png').write_bytes(data)

    def reference(self, card_id, data, *, write=True):
        self.cards.append({'id': card_id, 'png_sha256': sha(data)})
        if write:
            (self.references / f'card-{card_id}.png').write_bytes(data)

    def evidence(self, **overrides):
        body = {'checkout': HEAD, 'replay_sha256': 'c' * 64, 'deliveries': self.rows,
                'reference_cards': self.cards, **overrides}
        return json.dumps(body, sort_keys=True).encode()

    def build(self, **kwargs):
        return gallery.build(self.evidence(), self.delivered, self.references, **kwargs)

    def run(self, *extra, evidence=None):
        path = self.root / 'evidence.json'
        path.write_bytes(self.evidence() if evidence is None else evidence)
        out = io.StringIO()
        with redirect_stdout(out):
            code = gallery.main(['--evidence', str(path), '--delivered', str(self.delivered),
                                 '--references', str(self.references), '--out', str(self.root / 'page'), *extra])
        return code, json.loads(out.getvalue())


def cells(rows, case_id, variant=None):
    row = next(r for r in rows if r['id'] == case_id and r['variant'] == variant)
    return {cell['version']: cell for cell in row['versions']}, row['reference']


class VersionGalleryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bundle = Bundle(self.tmp.name)

    def test_confirmed_versions_and_reference_are_shown_side_by_side(self):
        b = self.bundle
        v1, v2, ref = png('one-v1'), png('one-v2'), png('one-ref')
        b.deliver(1, 1, v1)
        b.deliver(1, 2, v2)
        b.reference('01', ref)
        code, result = b.run()
        self.assertEqual((code, result['status'], result['cases']), (0, 'shown', 1))
        page = b.root / 'page'
        self.assertEqual((page / 'chat-01-v1.png').read_bytes(), v1)
        self.assertEqual((page / 'chat-01-v2.png').read_bytes(), v2)
        self.assertEqual((page / 'reference-01.png').read_bytes(), ref)
        html = (page / 'index.html').read_text()
        for name in ('chat-01-v1.png', 'chat-01-v2.png', 'reference-01.png'):
            self.assertIn(f'src="{name}"', html)
        self.assertIn('no v2 reference exists', html)
        self.assertIn("default-src 'none'; img-src 'self'", html)
        self.assertNotIn('http', html.split('</title>', 1)[1].replace('http-equiv', ''))
        receipt = json.loads((page / 'receipt.json').read_text())
        self.assertEqual(receipt['checkout'], HEAD)
        self.assertEqual(receipt['counts'], {'reference shown': 1, 'v1 delivered': 1, 'v2 delivered': 1})
        self.assertEqual(oct(page.stat().st_mode & 0o777), '0o700')
        self.assertEqual(oct((page / 'chat-01-v1.png').stat().st_mode & 0o777), '0o600')

    def test_same_size_swap_between_cases_is_refused_and_not_drawn(self):
        b = self.bundle
        one, two = png('case-one'), png('case-two')
        self.assertEqual(len(one), len(two))
        b.deliver(1, 1, one, write=False)
        b.deliver(2, 1, two, write=False)
        (b.delivered / 'case-01-v1.png').write_bytes(two)
        (b.delivered / 'case-02-v1.png').write_bytes(one)
        code, result = b.run()
        self.assertEqual((code, result['status']), (1, 'refused'))
        rows = json.loads((b.root / 'page' / 'receipt.json').read_text())['rows']
        self.assertEqual(cells(rows, 1)[0][1]['reason'], 'bytes-of-02-v1')
        self.assertEqual(cells(rows, 2)[0][1]['reason'], 'bytes-of-01-v1')
        self.assertFalse(list((b.root / 'page').glob('chat-*.png')))

    def test_v1_v2_swap_within_one_case_is_refused(self):
        b = self.bundle
        v1, v2 = png('same-v1'), png('same-v2')
        b.deliver(5, 1, v2, write=False)
        b.deliver(5, 2, v1, write=False)
        (b.delivered / 'case-05-v1.png').write_bytes(v1)
        (b.delivered / 'case-05-v2.png').write_bytes(v2)
        versions, _ = cells(b.build()[1], 5)
        self.assertEqual((versions[1]['reason'], versions[2]['reason']), ('bytes-of-05-v2', 'bytes-of-05-v1'))

    def test_file_without_a_confirmed_row_is_never_shown(self):
        b = self.bundle
        b.deliver(3, 1, png('three-v1'))
        (b.delivered / 'case-03-v2.png').write_bytes(png('three-v2'))
        b.deliver(4, 1, png('four-v1'), state='sent')
        b.deliver(4, 2, png('four-v2'), attachment='d' * 64)
        head, rows, files = b.build()
        three, _ = cells(rows, 3)
        four, _ = cells(rows, 4)
        self.assertEqual(three[2], {'version': 2, 'status': 'not delivered', 'reason': 'no-delivery-row',
                                    'file_ignored': True})
        self.assertEqual([four[n]['reason'] for n in (1, 2)], ['no-confirmed-delivery'] * 2)
        self.assertEqual(sorted(files), ['chat-03-v1.png'])

    def test_missing_files_are_explicit_not_refusals(self):
        b = self.bundle
        b.deliver(6, 1, png('six-v1'), write=False)
        b.reference('06', png('six-ref'), write=False)
        b.reference('07', png('seven-ref'))
        code, result = b.run()
        self.assertEqual((code, result['status']), (0, 'shown'))
        rows = json.loads((b.root / 'page' / 'receipt.json').read_text())['rows']
        six, six_ref = cells(rows, 6)
        self.assertEqual((six[1]['status'], six[2]['status'], six_ref['status']),
                         ('missing', 'not delivered', 'missing'))
        seven, seven_ref = cells(rows, 7)
        self.assertEqual((seven[1]['reason'], seven_ref['status']), ('no-delivery-row', 'shown'))
        html = (b.root / 'page' / 'index.html').read_text()
        self.assertIn('delivered-file-absent', html)
        self.assertIn('reference-file-absent', html)

    def test_changed_reference_link_and_non_png_are_refused(self):
        b = self.bundle
        b.reference('08', png('eight-ref'), write=False)
        (b.references / 'card-08.png').write_bytes(png('eight-new'))
        target = b.root / 'elsewhere.png'
        v1 = png('nine-v1')
        target.write_bytes(v1)
        b.deliver(9, 1, v1, write=False)
        os.symlink(target, b.delivered / 'case-09-v1.png')
        b.deliver(10, 1, b'not a png at all', write=True)
        rows = b.build()[1]
        self.assertEqual(cells(rows, 8)[1], {'status': 'refused', 'reason': 'bytes-differ',
                                             'png_sha256': sha(png('eight-ref'))})
        self.assertEqual(cells(rows, 9)[0][1]['reason'], 'not-a-regular-file')
        self.assertEqual(cells(rows, 10)[0][1]['reason'], 'not-a-png')
        self.assertTrue(gallery.refused(rows))

    def test_signature_only_or_garbage_png_with_a_confirmed_row_is_refused(self):
        # Review t_5ad8caa3: a confirmed, digest-matching file that is only the PNG signature (or signature plus
        # garbage) must be refused with exit 1, never copied or drawn as delivered.
        b = self.bundle
        sig_only, sig_garbage = gallery.PNG_MAGIC, gallery.PNG_MAGIC + b'garbage, not chunks'
        b.deliver(12, 1, sig_only)
        b.deliver(12, 2, sig_garbage)
        b.reference('12', gallery.PNG_MAGIC + b'\x00' * 40)
        code, result = b.run()
        self.assertEqual((code, result['status']), (1, 'refused'))
        rows = json.loads((b.root / 'page' / 'receipt.json').read_text())['rows']
        versions, ref = cells(rows, 12)
        self.assertEqual([versions[n]['reason'] for n in (1, 2)], ['not-a-png'] * 2)
        self.assertEqual((ref['status'], ref['reason']), ('refused', 'not-a-png'))
        self.assertFalse(list((b.root / 'page').glob('*.png')))

    def test_png_structure_is_checked_chunk_by_chunk(self):
        good = png('structure')
        self.assertIsNone(gallery.png_problem(good))
        iend = good.rindex(b'IEND') - 4
        ihdr_end = len(gallery.PNG_MAGIC) + 8 + 13 + 4
        flipped = bytearray(good)
        flipped[ihdr_end - 5] ^= 0x01  # one IHDR data byte: its CRC no longer matches
        idat = good.index(b'IDAT') - 4
        idat_len = int.from_bytes(good[idat:idat + 4], 'big')

        def chunk(kind, data):
            return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
        bad_stream = good[:idat] + chunk(b'IDAT', b'\x78\x9c not deflate') + good[idat + 12 + idat_len:]
        no_idat = good[:idat] + good[idat + 12 + idat_len:]
        cases = {
            'signature': b'\x89PNX\r\n\x1a\n' + good[8:],
            'truncated-chunk': good[:-3],
            'no-iend': good[:iend],
            'bytes-after-iend': good + b'\x00',
            'bad-crc': bytes(flipped),
            'no-idat': no_idat,
            'bad-image-data': bad_stream,
            'no-ihdr': gallery.PNG_MAGIC + good[ihdr_end:],
        }
        for reason, data in cases.items():
            with self.subTest(reason=reason):
                self.assertEqual(gallery.png_problem(data), reason)

    def test_variants_are_kept_apart_and_reference_only_on_the_base_case(self):
        b = self.bundle
        b.deliver(11, 1, png('eleven'))
        b.deliver(11, 1, png('eleven-a'), variant='a')
        b.reference('11', png('eleven-ref'))
        rows = b.build()[1]
        base, base_ref = cells(rows, 11)
        variant, variant_ref = cells(rows, 11, 'a')
        self.assertEqual((base[1]['file'], variant[1]['file']), ('chat-11-v1.png', 'chat-11a-v1.png'))
        self.assertEqual((base_ref['status'], variant_ref['status']), ('shown', 'no reference'))

    def test_case_filter_and_checkout_binding(self):
        b = self.bundle
        b.deliver(1, 1, png('f-one'))
        b.deliver(2, 1, png('f-two'))
        self.assertEqual([row['id'] for row in b.build(cases={'02'})[1]], [2])
        with self.assertRaisesRegex(gallery.Hold, 'evidence-checkout-mismatch'):
            b.build(checkout='e' * 40)
        code, result = b.run('--checkout', 'e' * 40)
        self.assertEqual((code, result), (1, {'status': 'hold', 'reasons': ['evidence-checkout-mismatch']}))
        self.assertFalse((b.root / 'page').exists())

    def test_malformed_evidence_holds(self):
        b = self.bundle
        b.deliver(1, 1, png('dup'))
        duplicate = dict(b.rows[0])
        for evidence, reason in (
                (b.evidence(deliveries=[*b.rows, duplicate]), 'evidence-duplicate-delivery'),
                (b'{"checkout": "x", "checkout": "y"}', 'evidence-unreadable'),
                (b.evidence(checkout='short'), 'evidence-checkout'),
                (b.evidence(deliveries={}), 'evidence-shape'),
                (b.evidence(deliveries=[{**b.rows[0], 'id': '1'}]), 'evidence-identity'),
                (b.evidence(deliveries=[{**b.rows[0], 'variant': '../x'}]), 'evidence-identity'),
                (b.evidence(reference_cards=[{'id': '13', 'png_sha256': 'a' * 64}]), 'evidence-reference'),
                (b.evidence(reference_cards=[{'id': '01', 'png_sha256': 'a' * 64}] * 2),
                 'evidence-duplicate-reference')):
            with self.subTest(reason=reason), self.assertRaisesRegex(gallery.Hold, reason):
                gallery.build(evidence, b.delivered, b.references)

    def test_output_must_be_new_and_outside_git(self):
        b = self.bundle
        b.deliver(1, 1, png('out'))
        (b.root / 'page').mkdir()
        (b.root / 'page' / 'old.txt').write_text('keep')
        code, result = b.run()
        self.assertEqual((code, result['status']), (1, 'hold'))
        self.assertEqual((b.root / 'page' / 'old.txt').read_text(), 'keep')
        (b.root / 'repo').mkdir()
        (b.root / 'repo' / '.git').write_text('gitdir: elsewhere')
        with self.assertRaisesRegex(ValueError, 'git worktree'):
            gallery._output_path(b.root / 'repo' / 'page')

    def test_inputs_are_left_unchanged(self):
        b = self.bundle
        b.deliver(1, 1, png('ro-v1'))
        b.reference('01', png('ro-ref'))
        before = {p: p.read_bytes() for p in (*b.delivered.iterdir(), *b.references.iterdir())}
        self.assertEqual(b.run()[0], 0)
        self.assertEqual({p: p.read_bytes() for p in (*b.delivered.iterdir(), *b.references.iterdir())}, before)


if __name__ == '__main__':
    unittest.main()
