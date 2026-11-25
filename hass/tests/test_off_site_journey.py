"""L22 owns the actual writer → HTTP → Market DOM boundary, not draft correctness."""
import re
import unittest

from scripts.hass import off_site_journey as off


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
