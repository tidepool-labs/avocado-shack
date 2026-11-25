"""Case 26 observer: the shown product image is the PNG delivered in chat (alt + loaded image SHA-256).

Fixtures only: no model, network, live Hass, host.json, Clover or recording. Each test names the contract it protects
and the believable bug that makes it fail.
"""
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hass import preview, sitegen
from hass.content_model import load_and_validate, shop_today
from hass.tests import test_preview

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('npp_run_case26_observer', ROOT / 'hass' / 'tests' / 'npp' / 'run_npp.py')
run_npp = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = run_npp
spec.loader.exec_module(run_npp)


def sha(label):
    return hashlib.sha256(label.encode()).hexdigest()


IMG1, IMG2 = sha('honey image v1'), sha('honey image v2 after the edit')
PNG1, PNG2 = sha('card png v1'), sha('card png v2')
ALT = 'A jar of honey'


def versions():
    return {1: {'n': 1, 'image_sha256': IMG1, 'card_png_sha': PNG1, 'outbox_id': 11},
            2: {'n': 2, 'image_sha256': IMG2, 'card_png_sha': PNG2, 'outbox_id': 12}}


def shot(image, png, alt=ALT):
    return {'image': None if image is None else {'alt': alt, 'image_sha256': image, 'png_sha256': png}}


def findings(shots, delivered=None, alts=None, lacks=('(illustration)',)):
    return run_npp.card_image_findings(
        list(lacks), versions(), {11: [PNG1], 12: [PNG2]} if delivered is None else delivered,
        shots, {1: ALT, 2: ALT} if alts is None else alts)


class CardImageObserverTests(unittest.TestCase):
    def test_alt_and_loaded_image_match_the_delivered_png_for_both_versions(self):
        # Contract: before and after the edit, the img alt and the loaded image SHA-256 belong to the PNG sent to chat.
        # Bug caught: an observer that records data but never compares it (a vacuous pass).
        self.assertEqual(findings({1: [shot(IMG1, PNG1)], 2: [shot(IMG2, PNG2)]}), ([], []))

    def test_a_stale_image_after_the_edit_fails_and_is_not_not_run(self):
        # Contract: version 1's bytes shown after the edit are a failure, not a missing observation.
        # Bug caught: treating a mismatching observation as not-run, which strict replay would never flag.
        bad, missing = findings({1: [shot(IMG1, PNG1)], 2: [shot(IMG1, PNG2)]})
        self.assertEqual(missing, [])
        self.assertEqual(len(bad), 1)
        self.assertIn('v2 loaded image SHA-256 is not the delivered image', bad[0])

    def test_missing_observer_data_is_not_run_not_pass_or_fail(self):
        # Contract: a capture that carries no observation (or a malformed one) is not-run.
        # Bug caught: defaulting absent data to pass (fabricated evidence) or to fail (hides a real gap).
        for label, seen in (('absent', None), ('malformed sha', {'image': {'alt': ALT, 'image_sha256': 'x', 'png_sha256': PNG2}}),
                            ('alt not text', {'image': {'alt': None, 'image_sha256': IMG2, 'png_sha256': PNG2}})):
            with self.subTest(label):
                data = seen if seen is not None else shot(None, PNG2)
                bad, missing = findings({1: [shot(IMG1, PNG1)], 2: [data]})
                self.assertEqual(bad, [])
                self.assertEqual(len(missing), 1)
                self.assertIn('v2 has no shown-image observation', missing[0])
        bad, missing = findings({1: [], 2: []})
        self.assertEqual((bad, len(missing)), ([], 2))

    def test_observation_of_another_png_or_alt_or_unsent_png_fails(self):
        # Contract: the observation is bound to the delivered PNG digest, the frozen alt and the alt rule.
        # Bug caught: comparing only the image bytes, so a card sent with another PNG or the illustration alt passes.
        ok = {1: [shot(IMG1, PNG1)], 2: [shot(IMG2, PNG2)]}
        cases = (('another png', {**ok, 2: [shot(IMG2, PNG1)]}, {}, 'observation is of another PNG'),
                 ('alt differs', {**ok, 2: [shot(IMG2, PNG2, 'Honey (illustration)')]}, {}, 'shown alt is not the frozen alt'),
                 ('alt rule', ok, {'alts': {1: ALT, 2: ALT}, 'lacks': ('jar',)}, 'shown alt contains jar'),
                 ('sent bytes differ', ok, {'delivered': {11: [PNG1], 12: [PNG1]}}, 'PNG sent to chat is not its frozen card'),
                 ('never sent', ok, {'delivered': {11: [PNG1]}}, 'PNG sent to chat is not its frozen card'))
        for label, shots, extra, text in cases:
            with self.subTest(label):
                bad, _ = findings(shots, **extra)
                self.assertTrue(any(text in item for item in bad), bad)

    def test_two_captures_of_one_png_are_ambiguous(self):
        # Bug caught: picking the first of several captures and so binding the wrong browser session.
        bad, _ = findings({1: [shot(IMG1, PNG1)], 2: [shot(IMG2, PNG2), shot(IMG2, PNG2)]})
        self.assertTrue(any('2 captures' in item for item in bad), bad)


@unittest.skipUnless(preview.Previewer('.').env.get('PLAYWRIGHT_MODULE'), 'Playwright not installed')
class LiveObserverTests(test_preview.BrowserCase):
    def test_observer_reports_the_loaded_image_before_and_after_an_edit(self):
        # Contract: card_observer.cjs reads the <img> alt and the body of the resource the browser really loaded, in
        # the session that made the PNG. Bug caught: hashing the file the record names instead of what was shown.
        wt = self.repo.wt
        content = load_and_validate(wt / 'hass' / 'content', wt / 'storefront-mockup')
        item = next(p for p in content.products if p['id'] == 'photo-product-001')
        other = next(p for p in content.products if p['id'] == 'photo-product-002')
        today = shop_today()
        browser = preview.Previewer(wt, dict(preview.Previewer(wt).env), viewports=('phone',))

        def observe():
            item['addedOn'] = today.isoformat()
            files = sitegen.render(content, wt / 'hass' / 'templates', today=today)
            target = preview.target_for({'collection': 'products', 'key': item['id'], 'after': item})
            with tempfile.TemporaryDirectory() as raw, patch.object(preview, 'SCRIPT', run_npp.CARD_OBSERVER):
                sink = Path(raw) / 'seen.json'
                result = browser.capture(files, target | {'cardOnly': True, 'observeTo': str(sink)},
                                         self.repo.state / 'screenshots' / 'observed.png')
                self.assertTrue(result['ok'], result)
                return json.loads(sink.read_text()), Path(result['png']).read_bytes()

        def loaded(product):
            return hashlib.sha256((wt / 'storefront-mockup' / product['image']).read_bytes()).hexdigest()

        item['imageAlt'] = 'A first jar of honey'
        before, before_png = observe()
        # The renderer may add its own suffix to the record alt, so the DOM alt is read, not assumed.
        self.assertTrue(before['alt'].startswith(item['imageAlt']), before['alt'])
        self.assertEqual((before['imageSha256'], before['pngSha256']),
                         (loaded(item), hashlib.sha256(before_png).hexdigest()))
        item.update(image=other['image'], imageAlt='A different jar of honey')
        after, after_png = observe()
        self.assertTrue(after['alt'].startswith('A different jar of honey'), after['alt'])
        self.assertEqual((after['imageSha256'], after['pngSha256']),
                         (loaded(other), hashlib.sha256(after_png).hexdigest()))
        self.assertNotEqual(before['imageSha256'], after['imageSha256'])


if __name__ == '__main__':
    unittest.main()
