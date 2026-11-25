"""L22 owns the actual writer → HTTP → Market DOM boundary, not draft correctness."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from scripts.hass import off_site_journey as off


def _git(root, *args):
    subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)


class TrackedInputsOnlyTests(unittest.TestCase):
    """The inherited sandbox copies hass/ and storefront assets wholesale; extras must stop it."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='hass-l22-inputs-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        _git(self.root, 'init', '-q')
        _git(self.root, 'config', 'user.email', 'hass-test@example.invalid')
        _git(self.root, 'config', 'user.name', 'hass-test')
        products = self.root / 'storefront-mockup' / 'assets' / 'products'
        products.mkdir(parents=True)
        (products / 'tracked.jpg').write_bytes(b'public')
        (self.root / 'hass').mkdir()
        (self.root / 'hass' / 'editor.py').write_text('x = 1\n')
        (self.root / '.gitignore').write_text('.env\n**/__pycache__/\n/storefront-mockup/assets/products/*.png\n')
        _git(self.root, 'add', '-A')
        _git(self.root, 'commit', '-q', '-m', 'base')

    def refused(self):
        with self.assertRaisesRegex(off.Refused, '^untracked-or-changed-input$'):
            off.tracked_inputs_only(self.root)

    def test_clean_tracked_tree_and_interpreter_cache_pass(self):
        for parent in (self.root / 'hass' / 'tests', self.root / 'storefront-mockup'):
            cache = parent / '__pycache__'
            cache.mkdir(parents=True)
            (cache / 'x.cpython-312.pyc').write_bytes(b'cache')
        off.tracked_inputs_only(self.root)

    def test_ignored_private_files_refuse(self):
        (self.root / 'hass' / '.env').write_text('TOKEN=private\n')
        self.refused()
        (self.root / 'hass' / '.env').unlink()
        (self.root / 'storefront-mockup' / 'assets' / 'products' / 'original.png').write_bytes(b'private')
        self.refused()

    def test_untracked_or_changed_input_refuses(self):
        (self.root / 'hass' / 'notes.json').write_text('{}')
        self.refused()
        (self.root / 'hass' / 'notes.json').unlink()
        (self.root / 'hass' / 'editor.py').write_text('x = 2\n')
        self.refused()

    def test_cache_in_copied_assets_and_unverifiable_tree_refuse(self):
        cache = self.root / 'storefront-mockup' / 'assets' / 'products' / '__pycache__'
        cache.mkdir()
        (cache / 'x.pyc').write_bytes(b'cache')
        self.refused()
        with self.assertRaisesRegex(off.Refused, '^input-tree-unverified$'):
            off.tracked_inputs_only(self.root / 'missing')


@unittest.skipUnless(off.Previewer(off.ROOT).env.get('PLAYWRIGHT_MODULE'), 'local Playwright runtime unavailable')
class OffSiteJourneyTests(unittest.TestCase):
    def test_bound_shop_serves_and_reverses_the_exact_fixture_card(self):
        # A watcher pointed at another root, a stale catalog, a broken Market
        # script, or a take-down that leaves the deep link visible must not pass.
        receipt = off.fixture_pass()
        self.assertEqual(set(receipt['checks']), {
            'public-target-refused', 'wrong-root-refused', 'absent-before-yes',
            'browser-and-photo-match', 'stale-catalog-refused', 'one-coded-takedown',
            'browser-absent-and-catalog-restored',
        })
        self.assertEqual(receipt['initial_catalog_sha256'], receipt['restored_catalog_sha256'])
        self.assertNotEqual(receipt['initial_catalog_sha256'], receipt['served_catalog_sha256'])
        self.assertEqual(receipt['preview']['approved_photo_sha256'], receipt['readback_photo_sha256'])
        self.assertEqual(receipt['preview']['approved_public_fields_sha256'], receipt['browser_public_fields_sha256'])
        self.assertEqual((receipt['publish_commits'], receipt['takedown_commits']), (1, 1))
        for digest in (receipt['server_sha256'], receipt['market_html_sha256'], *receipt['preview'].values()):
            self.assertTrue(re.fullmatch(r'[a-f0-9]{64}', digest))
