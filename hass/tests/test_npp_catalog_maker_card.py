"""Case 3 (golden Straus half-and-half): a new card for an existing catalog maker shows what the shop shows.

Two refusals kept every new Straus card off the chat ("I couldn't draw the card yet"):
1. storefront-mockup/shop.js badges every Straus, Ocean Ranch, Green Gold and Massa Organics product "Organic"
   whatever its name; the card gate only allowed that badge when the product NAME said organic (card-copy).
2. The published Straus and Sierra Nevada stories say "about"/"or" as ordinary words far from their founding year;
   numbers.problem() calls any such word in a text with a number unclear (public-text).
Both stay fail-closed for everything else; see the negative controls below.
"""
import re
import unittest
from dataclasses import replace
from pathlib import Path

from hass.npp import validate
from hass.ops import catalog
from hass.tests import test_npp_validate as base

ROOT = Path(__file__).resolve().parents[2]
STRAUS = ('Straus helped change the conversation about American dairy when its family farm became certified organic '
          'in 1994. The creamery carries that commitment into its milk, cream and cultured products. Good dairy earns '
          'its place in coffee, a sauce, or simply a cold glass.')


class ShopOrganicMakersTests(unittest.TestCase):
    def test_badge_makers_are_the_catalog_list_shop_js_badges(self):
        # test_organic_sync keeps catalog.ORGANIC_MAKERS equal to shop.js organic() in a real JS run; here the card
        # gate must read that same list, and shop.js still badges by maker key (not by name alone).
        self.assertIs(validate.catalog.ORGANIC_MAKERS, catalog.ORGANIC_MAKERS)
        source = (ROOT / 'storefront-mockup/shop.js').read_text()
        listed = re.search(r'function organic\(p\)\{.*?\[([^\]]*)\]\.includes\(p\.producerKey\)', source)
        self.assertIsNotNone(listed)
        self.assertEqual(set(re.findall(r"'([^']+)'", listed.group(1))), set(catalog.ORGANIC_MAKERS))

    def test_badge_needs_the_name_or_an_existing_listed_maker(self):
        known = {'Straus': {'name': 'Straus'}, 'Oak Farm': {'name': 'Oak Farm'}}
        badge = validate._organic_badge
        self.assertTrue(badge({'name': 'Half & Half', 'producerKey': 'Straus'}, known, []))
        self.assertTrue(badge({'name': 'Organic plums', 'producerKey': 'Oak Farm'}, known, []))
        self.assertTrue(badge({'name': 'Organic plums'}, {}, []))
        self.assertFalse(badge({'name': 'Plums', 'producerKey': 'Oak Farm'}, known, []))
        self.assertFalse(badge({'name': 'Plums'}, known, []))
        # A listed key the catalog does not hold, or a maker this draft adds under that key, earns nothing.
        self.assertFalse(badge({'name': 'Half & Half', 'producerKey': 'Green Gold'}, known, []))
        self.assertFalse(badge({'name': 'Half & Half', 'producerKey': 'Straus'}, known, [{'key': 'Straus'}]))
        self.assertFalse(badge({'name': 'Half & Half', 'producerKey': 'straus'}, {'straus': {}}, []))


class CatalogStoryYearCueTests(unittest.TestCase):
    def ok(self, story, private=frozenset()):
        return validate._catalog_story_numbers_ok(story, private)

    def test_published_stories_with_a_year_and_a_distant_cue_word_are_shown(self):
        sierra = ('Sierra Nevada Cheese Company began in 1997 with Ben Gregersen and John Dundon’s shared interest in '
                  'traditional dairy craft. The Sierra Jack varieties bring a sandwich or a generous snack plate.')
        for story in (STRAUS, sierra):
            with self.subTest(story=story[:30]):
                self.assertEqual(validate.numbers.problem(story, frozenset(), digits_allowed=True), 'number-unclear')
                self.assertTrue(self.ok(story))

    def test_a_cue_near_a_year_or_any_other_number_still_keeps_the_story_off(self):
        for story in ('Founded about 1994 by the Straus family.',
                      'Founded in 1994 or 1995 by the Straus family.',
                      'Since 1994, roughly a sauce maker.',
                      'The farm began in 1994. It has about 30 cows, or so.',
                      'The farm began in 1994. It milks two or three herds a day.',
                      'The farm began in 1994. Twelve hundred cows, or more.',
                      'The farm began in 1994. A couple of us talk about cheese.',
                      'The farm began in 1794. We talk about cheese.',
                      'The farm began in 2094. We talk about cheese.',
                      'The farm began in 19940. We talk about cheese.',
                      'Born on Highway 1 across from the beach. Eggs, tacos, or seafood.',
                      'The farm began in 1994. A pint costs $4, or about that.',
                      'The farm began in １９９４. We talk about cheese.'):
            with self.subTest(story=story):
                self.assertFalse(self.ok(story))

    def test_a_private_reading_of_the_year_is_never_shown(self):
        story = 'The farm began in 1994. Since then we have talked about cheese, or butter.'
        self.assertTrue(self.ok(story))
        self.assertFalse(self.ok(story, frozenset({validate.numbers.Decimal(1994)})))


class StrausCardTests(unittest.TestCase):
    """listing()-level: the shop's badge and the published Straus story on a new Straus card."""

    setUp = base.ValidateTests.setUp
    verdict = base.ValidateTests.verdict

    def card(self, *, story=STRAUS, badge=True, key='Straus', makers=None):
        # The owner names the maker (case 3: "made by Straus"), so the existing-claims check passes.
        self.ctx = replace(self.ctx, owner_words=f'made by {key}')
        self.product['producerKey'] = key
        origin = 'Based in Northern California'
        nodes = [*self.nodes, origin, story]
        if badge:
            nodes.append({'text': 'Organic', 'role': '.food-badges > span'})
        makers = makers if makers is not None else {key: {'name': 'Straus', 'place': 'Northern California',
                                                          'story': story}}
        return self.verdict(makers=makers, origin=origin, card_nodes=nodes).problems

    def test_new_straus_card_passes_with_the_shop_badge_and_published_story(self):
        self.assertEqual(self.card(story='We grow plums on a small hill.', badge=False), ())
        self.assertEqual(self.card(badge=False), ())
        self.assertEqual(self.card(), ())

    def test_badge_on_an_unlisted_maker_and_a_year_story_with_a_near_cue_still_fail(self):
        oak = {'Oak Farm': {'name': 'Oak Farm', 'place': 'Northern California', 'story': 'We grow plums.'}}
        self.assertEqual(self.card(story='We grow plums.', key='Oak Farm', makers=oak, badge=False), ())
        self.assertIn('card-copy', self.card(story='We grow plums.', key='Oak Farm', makers=oak))
        self.assertIn('public-text', self.card(story='Founded about 1994. We talk about cream.', badge=False))


if __name__ == '__main__':
    unittest.main()
