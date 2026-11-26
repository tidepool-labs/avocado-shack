"""Offline acceptance of the gallery CLI; the editor, generator and validator stay real."""
from base64 import b64decode
from contextlib import ExitStack, redirect_stdout
from hashlib import sha256
from html import escape
from io import BytesIO, StringIO
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.hass import npp_card_gallery as gallery

PNG = b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+Xac0AAAAASUVORK5CYII=')


class CardGalleryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.out = self.root / 'gallery'
        self.targets = []
        self.sandboxes = []
        self.bad_card = False

    def capture(self, files, target, out_png, assets):
        self.targets.append(target)
        self.sandboxes.append(out_png.parents[2])
        self.assertTrue(target['cardOnly'])
        self.assertIn(target['id'].encode(), files['storefront-mockup/catalog-products.js'])
        self.assertIn(target['image'], [path.removeprefix('storefront-mockup/') for path in assets])
        self.assertTrue(str(out_png).startswith(str(self.out)))
        out_png.parent.mkdir(exist_ok=True)
        out_png.write_bytes(PNG)
        fragments = [target['name'], target['description'], target['price']]
        if self.bad_card:
            fragments[1] = 'Unexpected copy.'
        return {'ok': True, 'png': str(out_png), 'cardEvidence': {
            'fragments': [{'text': text, 'role': None} for text in fragments], 'priceIndex': 2,
            'pngSha256': sha256(PNG).hexdigest(), 'productId': target['id'],
        }}

    def run_gallery(self, *args, out=None, fake=True):
        with ExitStack() as stack:
            stdout = stack.enter_context(redirect_stdout(StringIO()))
            if fake:
                stack.enter_context(patch.object(gallery, '_dependencies', return_value=None))
                stack.enter_context(patch.object(gallery.preview.Previewer, 'capture', side_effect=self.capture))
                stack.enter_context(patch.object(gallery.picture, 'read_text', return_value=''))
            code = gallery.main(['--out', str(self.out if out is None else out), *args])
        return code, stdout.getvalue().splitlines()

    def test_c1_gallery_with_fake_capture(self):
        # C1: catches a data-only renderer, skipped defaults/fixture card, or non-private output.
        self.out.mkdir(mode=0o755)
        with patch.object(gallery.copy.Writer, 'write', autospec=True, side_effect=gallery.copy.Writer.write) as write:
            code, lines = self.run_gallery('--strict')
        self.assertEqual(code, 0, lines)
        self.assertEqual(write.call_count, 12)
        self.assertTrue(all(call.args[-1] is None for call in write.call_args_list))
        self.assertEqual(len(self.targets), 12)
        self.assertEqual(lines[-1], 'DRAWN 12 card(s)')
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o700)
        pngs = {f'card-{case}.png' for case in gallery.CASE_IDS}
        self.assertEqual({p.name for p in self.out.iterdir()}, pngs | {'index.html'})
        for path in self.out.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            if path.name in pngs:
                self.assertEqual(path.read_bytes(), PNG)
        # Synthetic linked-worktree .git marker: refusal before creating anything.
        checkout = self.root / 'checkout'
        checkout.mkdir()
        (checkout / '.git').write_text('gitdir: fixture\n', encoding='utf-8')
        refused = checkout / 'private'
        self.assertEqual(self.run_gallery(out=refused)[0], 1)
        self.assertFalse(refused.exists())

    def test_c2_missing_deps(self):
        # C2: catches accidental success, fallback Node on a bad override, or partial skip notices.
        for dependency in ('node', 'playwright'):
            with self.subTest(dependency=dependency):
                env = {'PLAYWRIGHT_MODULE': str(self.root / 'absent-playwright')}
                resolved = None if dependency == 'node' else '/fixture/node'
                with (patch.object(gallery.preview.Previewer, '__init__', return_value=None),
                      patch.object(gallery.preview.Previewer, 'env', env, create=True),
                      patch.object(gallery.shutil, 'which', return_value=resolved) as which,
                      patch.object(gallery.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'v22.0.0\n')),
                      patch.object(gallery.preview.Previewer, 'capture') as capture):
                    out = self.root / dependency
                    args = ('--node', 'fixture-node', '--case', '01', '12')
                    self.assertEqual(self.run_gallery(*args, '--strict', out=out, fake=False), (1, [f'FAIL missing {dependency}']))
                    self.assertFalse(out.exists())
                    skipped = [f'NOT-RUN {case} {dependency}' for case in ('01', '12')]
                    self.assertEqual(self.run_gallery(*args, out=out, fake=False), (0, [*skipped, 'DRAWN 0 card(s)']))
                    which.assert_called_with('fixture-node')
                    capture.assert_not_called()
                page = (out / 'index.html').read_text(encoding='utf-8')
                self.assertEqual({p.name for p in out.iterdir()}, {'index.html'})
                for line in skipped:
                    self.assertIn(line, page)
                self.assertNotIn('PASS', page)

    def test_c3_page_fields(self):
        # C3: catches missing reference/price/digest and a hard-coded validation pass.
        self.bad_card = True
        code, lines = self.run_gallery('--case', '09')
        self.assertEqual(code, 0, lines)
        self.assertIn('DRAWN 09 Validate: REFUSED: card-copy', lines)
        page = (self.out / 'index.html').read_text(encoding='utf-8')
        case = gallery._json(next(gallery.CASES.glob('case-09-golden-*.json')))
        reference = gallery._json(gallery.GOLDENS / Path(case['golden']).name)
        drawn, golden = page.split('<h3>Golden reference (saved fixture)</h3>')
        for text in ('src="card-09.png"', 'Name: Crimson lentils', 'Price: $4.00 each', 'Category: pantry',
                     'Validate: REFUSED: card-copy', sha256(PNG).hexdigest()):
            self.assertIn(text, drawn)
        for text in (f'Name: {escape(reference["card"]["name"])}', f'Category: {reference["category"]}', 'data:image/webp;'):
            self.assertIn(text, golden)
        self.assertNotIn('card-01.png', page)

    def test_c4_clean(self):
        # C4: catches leftover private state, writes into checkout inputs, or any transport launch.
        inputs = [*gallery.CASES.glob('case-*-golden-*.json'), *gallery.CASES.glob('photos/golden-*.jpg'),
                  *gallery.GOLDENS.glob('*.json'), *(gallery.ROOT / rel for rel in gallery.editor.REVISION_PATHS)]
        inputs.extend(gallery.ROOT / gallery.preview.SITE / gallery._json(p)['photo_path']
                      for p in gallery.GOLDENS.glob('*.json'))

        def snapshot():
            return {p: (sha256(p.read_bytes()).digest(), p.stat().st_mtime_ns) for p in inputs}

        before = snapshot()
        run = subprocess.run

        def local_git(argv, *args, **kwargs):
            self.assertEqual(argv[:2], ['git', '-C'])
            self.assertEqual(argv[3:], ['rev-parse'])
            return run(argv, *args, **kwargs)

        with (patch('socket.socket', side_effect=AssertionError('network is forbidden')) as network,
              patch.object(subprocess, 'run', side_effect=local_git),
              patch.object(gallery.editor, 'apply', side_effect=AssertionError('no apply'))):
            code, lines = self.run_gallery('--case', '09')
        self.assertEqual(code, 0, lines)
        self.assertIn('DRAWN 09 Validate: PASS', lines)
        network.assert_not_called()
        self.assertTrue(self.sandboxes)
        self.assertTrue(all(not box.exists() for box in self.sandboxes))
        self.assertEqual(snapshot(), before)
        self.assertEqual({p.name for p in self.out.iterdir()}, {'card-09.png', 'index.html'})

    def test_c5_reference_picture_sources(self):
        # C5 (H73): catches a run-time picture swap, a widened site-picture list, a changed screen
        # input, or a page that hides which picture a card was drawn from.
        self.assertEqual(gallery.SITE_PICTURE_CASES, frozenset({'03', '08', '09'}))
        stored, checked = [], []
        store, listing = gallery.media.store_original, gallery.validate.listing

        def keep(root, data, **kwargs):
            stored.append(data)
            return store(root, data, **kwargs)

        def check(*args, **kwargs):
            checked.append(kwargs)
            return listing(*args, **kwargs)

        with (patch.object(gallery.media, 'store_original', side_effect=keep),
              patch.object(gallery.validate, 'listing', side_effect=check)):
            code, lines = self.run_gallery('--strict')
        self.assertEqual(code, 0, lines)
        self.assertEqual(len(stored), 12)
        page = (self.out / 'index.html').read_text(encoding='utf-8')
        sections = page.split('<section>')[1:]
        for case_id, data, kwargs, section in zip(gallery.CASE_IDS, stored, checked, sections, strict=True):
            with self.subTest(case=case_id):
                case = gallery._json(next(gallery.CASES.glob(f'case-{case_id}-golden-*.json')))
                golden = gallery._json(gallery.GOLDENS / Path(case['golden']).name)
                photo = gallery.CASES / 'photos' / case['turns'][0]['photos'][0].removeprefix('npp:')
                site = case_id in gallery.SITE_PICTURE_CASES
                self.assertEqual(data, gallery._reference_photo(golden) if site else photo.read_bytes())
                self.assertEqual(kwargs['photo_sha'], sha256(data).hexdigest())
                # The screen gets no extra label evidence or permits: only the gallery's own arguments.
                self.assertNotIn('label_words', kwargs)
                note = gallery.SITE_PICTURE_NOTE if site else gallery.CASE_PHOTO_NOTE
                self.assertIn(f'<p>{escape(note)}</p>', section)

    def test_c6_saved_picture_is_a_fixed_intake_jpeg(self):
        # C6 (H73): catches a non-intake format, a resized picture, or bytes that vary per run.
        from PIL import Image

        for case_id in sorted(gallery.SITE_PICTURE_CASES):
            with self.subTest(case=case_id):
                case = gallery._json(next(gallery.CASES.glob(f'case-{case_id}-golden-*.json')))
                golden = gallery._json(gallery.GOLDENS / Path(case['golden']).name)
                data = gallery._reference_photo(golden)
                self.assertEqual(gallery.media.sniff(data), 'jpeg')
                self.assertEqual(data, gallery._reference_photo(golden))
                site = gallery.ROOT / gallery.preview.SITE / golden['photo_path']
                with Image.open(site) as original, Image.open(BytesIO(data)) as drawn:
                    self.assertEqual(drawn.size, original.size)
                    self.assertEqual(drawn.mode, 'RGB')
