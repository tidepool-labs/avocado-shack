"""S7 fixture checks use assembled draft records and independently supplied image/DOM evidence."""
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch

from hass import claims
from hass.npp import assets, validate
from hass.npp.copy import Context, Writer
from hass.npp.private_numbers import finance


class ValidateTests(unittest.TestCase):
    def setUp(self):
        self.writer = Writer(assets())
        self.finance = finance('cost $3; sell $3 each; qty 12')
        self.ctx = Context('food', 'pantry', 'raw', 'plum jam', size_text='12 oz', source_read='Plum Jam 12 oz', private=self.finance.private)
        choice = {'name': {'template_id': 'name-item-size'}, 'story': None}
        self.copy = self.writer.write(self.ctx, lambda *_: choice)
        self.asset = 'assets/products/photo-0123456789abcdef.jpg'
        self.sha = 'a' * 64
        self.product = dict(self.copy.text, brand=claims.PLACEHOLDER, displayBrand='From the market', category='pantry',
                            id='photo-product-001', image=self.asset, sellingPrice='3.00 each')
        self.draft = {'ops': [{'op': 'product.add', 'args': {'sellingPrice': '3.00 each', 'brand': claims.PLACEHOLDER,
                                                         'name': self.copy.text['name']}}],
                      'records': [{'collection': 'products', 'before': None, 'after': self.product, 'key': self.product['id']}],
                      'assets': {self.asset: 'sha256:' + self.sha}}
        self.nodes = [self.copy.text['name'], '$3.00 each', self.copy.text['description']]
        self.kw = dict(finance=self.finance, origin=validate.ORIGIN_UNKNOWN, makers={}, live_site=True,
                       photo_sha='b' * 64, frozen_sha=self.sha, rendered_sha=self.sha, picture_read='Plum Jam 12 oz',
                       card_nodes=self.nodes, price_index=1,
                       label_words=['12 oz'])

    def verdict(self, **changes):
        return validate.listing(self.writer, self.ctx, self.copy, self.draft, **(self.kw | changes))

    def test_added_on_requires_exact_shop_day_and_explicit_clock(self):
        # Reject implicit-clock exemptions, permissive parsing and a freshness window.
        now = datetime(2026, 11, 21, 3, tzinfo=timezone.utc)  # still Nov 20 at the shop
        self.product['addedOn'] = '2026-11-20'
        self.assertEqual(self.verdict(added_on_now=now).problems, ())
        self.assertEqual(self.verdict().problems, ('public-text',))
        for value in ('2026-02-30', '20261120', '2026-11-19', '2026-11-21'):
            with self.subTest(value=value):
                self.product['addedOn'] = value
                self.assertEqual(self.verdict(added_on_now=now).problems, ('public-text',))

    def test_added_on_does_not_exempt_elsewhere_or_bypass_contact(self):
        # Catch global value-based exemptions and short-circuiting the contact scan.
        now = datetime(2026, 11, 20, 20, tzinfo=timezone.utc)
        day = self.product['addedOn'] = '2026-11-20'
        self.product['displayBrand'] = day
        self.assertIn('public-text', self.verdict(added_on_now=now).problems)
        self.product['displayBrand'] = 'From the market'
        self.product['producerKey'] = 'oak-farm'
        maker = {'name': 'Oak Farm', 'addedOn': day}
        self.assertIn('public-text', self.verdict(added_on_now=now, makers={'oak-farm': maker}).problems)
        del self.product['producerKey']
        self.assertEqual(self.verdict(added_on_now=now, card_nodes=[*self.nodes, day]).problems, ('card-number',))
        with patch.object(validate, '_contact', side_effect=lambda text: text == day):
            self.assertEqual(self.verdict(added_on_now=now).problems, ('public-text',))

    def test_independent_price_and_size_pass_but_alt_gets_no_size_permit(self):
        # Case 32: banning values globally blocks legal price/size; granting by value leaks into other text.
        self.assertEqual(self.copy.text['name'], 'Plum jam 12 oz')
        self.assertNotIn('12', self.copy.text['imageAlt'])
        self.assertEqual(self.verdict().problems, ())
        for leak in ('Take twelve home.', 'Take 12 oz home.'):
            self.assertIn('card-number', self.verdict(card_nodes=[*self.nodes, leak]).problems)

    def test_price_must_be_in_exact_dom_element_once_and_picture_bound(self):
        # A string search for the total could pass duplicate/off-element prices or a different preview asset.
        self.assertIn('card-price', self.verdict(price_index=0).problems)
        for text in ('$3.00 each', 'only three dollars', '3.50'):
            self.assertIn('card-number', self.verdict(card_nodes=[*self.nodes, text]).problems)
        self.assertIn('money', self.verdict(picture_read='Plum Jam $3.00').problems)
        self.assertIn('picture-binding', self.verdict(rendered_sha='c' * 64).problems)
        self.assertIn('price-provenance', self.verdict(finance=finance('cost $3')).problems)

    def test_card_cannot_bind_another_record_key(self):
        # Contract: captured evidence must describe the product the draft will write.
        # Regression: checking only after.id lets a stale record key name another product.
        png = (Path(__file__).parent / 'fixtures' / 'media' / 'pixel.png').read_bytes()
        capture = dict(productId=self.product['id'], pngSha256=sha256(png).hexdigest(),
                       fragments=[{'text': text, 'role': None} for text in self.nodes],
                       priceIndex=1, makerCount=None)
        shot = dict(card_evidence=capture, card_png=png, card_nodes=None, price_index=None)
        self.assertEqual(self.verdict(**shot).problems, ())
        self.draft['records'][0]['key'] = 'photo-product-002'
        self.assertEqual(self.verdict(**shot).problems, ('listing-records',))

    def test_matching_product_identity_still_requires_an_editor_id(self):
        # Contract: the write key must exist and meet the editor's ID grammar.
        # Regression: equality alone accepts two missing or identically malformed IDs.
        row = self.draft['records'][0]
        del row['key'], self.product['id']
        self.assertEqual(self.verdict().problems, ('listing-records',))
        for value in ('', 'Photo-product-001', 'photo_product_001', 'a' * 65):
            with self.subTest(value=value):
                row['key'] = self.product['id'] = value
                self.assertEqual(self.verdict().problems, ('listing-records',))

    def test_assembled_record_cannot_override_checked_copy_or_legacy_gates(self):
        # Valid text alone is insufficient: S7 must check the exact records that apply uses.
        self.product['description'] = 'This cures colds. It is made the old way.'
        self.product['brand'] = 'Unknown Farms'
        self.product['displayBrand'] = 'Unknown Farms'
        verdict = self.verdict()
        self.assertTrue({'listing-fields', 'brand', 'existing-claims', 'existing-identity', 'existing-live-policy'} <= set(verdict.problems))
        self.assertNotIn('colds', repr(verdict))

    def test_planted_length_hype_chatter_and_contact_are_distinct_checks(self):
        # Non-template public fields and future template revisions still need independent lint.
        for text, code in [('x' * 201, 'length'), ('The best jam. Take it home.', 'hype'),
                           ('My next delivery arrives soon. Take it home.', 'owner-chatter'),
                           ('Ask me at help@example.test. Take it home.', 'contact')]:
            with self.subTest(code=code):
                ctx = replace(self.ctx, owner_words='My next delivery arrives soon')
                self.assertEqual(validate.field_problem(self.writer, 'description', text, (), ctx), code)

    def test_card_text_must_be_the_validated_copy_and_nothing_else(self):
        # Contract: S7 checks the rendered card against the approved draft, not just price/number/contact.
        # Bug caught: a swapped description ("This cures cancer.") or an extra unlisted line passed with no problems.
        description = self.copy.text['description']
        swapped = [self.nodes[0], self.nodes[1], 'This cures cancer.']
        self.assertIn('card-copy', self.verdict(card_nodes=swapped).problems)
        self.assertIn('card-copy', self.verdict(card_nodes=[*self.nodes, 'Handmade with love.']).problems)
        self.assertIn('card-copy', self.verdict(card_nodes=[self.nodes[0], self.nodes[1]]).problems)
        # Whitespace folding and the checked origin line stay legal.
        self.assertEqual(self.verdict(card_nodes=[self.nodes[0], self.nodes[1], ' '.join(description.split()) + ' ',
                                                  validate.ORIGIN_UNKNOWN, 'From the market']).problems, ())

    def test_existing_maker_story_is_shown_only_when_it_carries_no_protected_claim(self):
        # Contract: the card-copy gate binds maker-panel text too. Bug caught: an existing maker's catalog story
        # ("This cures cancer.") was auto-allowed on the card because only contacts/numbers were checked.
        self.product['producerKey'] = 'oak-farm'
        origin = 'Based in Oakdale'
        def card(story):
            return self.verdict(makers={'oak-farm': {'name': 'Oak Farm', 'place': 'Oakdale', 'story': story}}, origin=origin,
                                card_nodes=[*self.nodes, origin, story])
        self.assertNotIn('card-copy', card('We grow plums on a small hill.').problems)
        self.assertIn('card-copy', card('This cures cancer.').problems)

    def test_existing_maker_story_year_is_shown_but_private_numbers_and_other_fragments_still_fail(self):
        # Contract: an existing maker's published catalog story may carry a founded year on the card, exactly as the
        # record check already allows. Bug caught (private live replay, golden cases): every card for a known maker whose
        # story said "in 1976" failed as 'card-number', so Hass only said "I couldn't draw the card yet".
        self.product['producerKey'] = 'oak-farm'
        origin = 'Based in Oakdale'

        def card(story, extra=()):
            return self.verdict(makers={'oak-farm': {'name': 'Oak Farm', 'place': 'Oakdale', 'story': story}}, origin=origin,
                                card_nodes=[*self.nodes, origin, story, *extra])
        story = 'It started as a roadside stand in 1976.'
        clean = card(story).problems
        self.assertNotIn('card-number', clean)
        self.assertNotIn('card-copy', clean)
        # The exemption is the exact catalog fragment, not the value: the same year elsewhere is still a leak.
        self.assertIn('card-number', card(story, extra=['Picked in 1976.']).problems)
        # A private number (the owner's qty 12) inside the story is never exempt.
        self.assertIn('card-number', card('It started as a roadside stand 12 years ago.').problems)

    def test_existing_maker_catalog_story_may_narrate_origin_but_no_other_claim(self):
        # Contract: an existing maker's unchanged catalog story is the text every other card of that maker already shows.
        # Origin narration in it ("a family farm", "organic orchard", "raw and unfiltered") is not a new claim by this draft.
        # Bug caught (private replay, golden cases 5/6/11): 17 of 26 real catalog stories tripped the origin/organic class,
        # so no new product from those makers could ever be drawn ("I couldn't draw the card yet").
        self.product['producerKey'] = 'oak-farm'
        origin = 'Based in Oakdale'

        def card(story, extra=()):
            return self.verdict(makers={'oak-farm': {'name': 'Oak Farm', 'place': 'Oakdale', 'story': story}}, origin=origin,
                                card_nodes=[*self.nodes, origin, story, *extra]).problems
        narration = 'A small family farm in Oakdale; an organic orchard. The honey is raw and unfiltered.'
        self.assertFalse(validate._panel_clean(narration))  # the old rule refused it
        plain = card('We grow plums on a small hill.')  # this fixture's owner never names the maker: existing-claims only
        self.assertEqual(plain, ('existing-claims',))
        self.assertEqual(card(narration), plain)
        # Any other claim kind still keeps the story off the card, even next to origin narration.
        for story in ('An organic orchard in Oakdale. This cures cancer.', 'A family farm in Oakdale. Award-winning jam.',
                      'The best farm in Oakdale.'):
            with self.subTest(story=story):
                self.assertIn('card-copy', card(story))
        # The exemption is the exact catalog fragment: the same narration typed as another card line is still refused.
        self.assertIn('card-copy', card(narration, extra=['An organic orchard.']))
        # RETURN t_bf22eb69 item 2: the exact catalog fragment repeated as a second card line is refused too.
        self.assertIn('card-copy', card(narration, extra=[narration]))
        self.assertIn('card-copy', card(narration, extra=['  ' + narration.replace(' ', '\n', 1)]))

    def test_existing_maker_catalog_story_number_words_are_fine_but_private_and_money_are_not(self):
        # Contract: published catalog text may use a number-like word ("The point is the fruit") or a founded year.
        # Bug caught (private replay, golden case 11): "point" read as a spoken decimal made the story 'number-unclear',
        # failing both the record check (public-text) and the card scan (card-number).
        self.product['producerKey'] = 'oak-farm'
        origin = 'Based in Oakdale'

        def card(story):
            return self.verdict(makers={'oak-farm': {'name': 'Oak Farm', 'place': 'Oakdale', 'story': story}}, origin=origin,
                                card_nodes=[*self.nodes, origin, story]).problems
        plain = card('We grow plums on a small hill.')
        self.assertEqual(plain, ('existing-claims',))  # this fixture's owner never names the maker
        self.assertEqual(card('We grow plums. The point is the fruit.'), plain)
        self.assertEqual(card('We grow plums, since 1976.'), plain)
        # Fail closed: "point" next to any number reading could be a decimal, so that story stays off.
        self.assertIn('public-text', card('We grow plums. The point is the fruit, since 1976.'))
        # A reading equal to a private value (qty 12, cost 3) is never exempt, spelled, digits or ambiguous.
        for story in ('We planted twelve trees. The point is the fruit.', 'We planted about 12 trees.',
                      'Three generations. The point is the fruit.', 'Jars were $5 in 1976.', 'Call 805-555-0100 to visit.'):
            with self.subTest(story=story):
                problems = card(story)
                self.assertTrue({'public-text', 'card-number', 'card-copy', 'card-contact'} & set(problems), problems)
                self.assertIn('public-text', problems)

    def test_catalog_story_number_words_fail_closed_on_any_unresolved_reading(self):
        # RETURN t_bf22eb69 item 1: "twelve hundred" is 'number-unclear' and values() reads only "twelve", so a private
        # quantity of 1200 slipped through. Only a bare "point" in a story with no number at all may pass.
        private = finance('cost $3; sell $3 each; qty 1200').private
        ok = validate._catalog_story_numbers_ok
        self.assertTrue(ok('We grow plums. The point is the fruit.', private))
        self.assertTrue(ok('Founded in 1976 on a hill.', private))
        for story in ('We planted twelve hundred trees.', 'We planted twelve hundred trees. The point is the fruit.',
                      'A couple of hives. The point is the honey.', 'Two point five acres of plums.',
                      'Since １９７６, the point is the fruit.', 'We grow ½ of our plums.', 'We planted 1200 trees.',
                      'The point is the fruit, about 3 kinds.'):
            with self.subTest(story=story):
                self.assertFalse(ok(story, private))

    def test_existing_maker_name_and_place_are_shown_only_when_they_carry_no_protected_claim(self):
        # Contract: the card-copy gate binds EVERY maker-panel fragment, not only the story. Bug caught: an existing
        # maker whose catalog name/place was "This cures cancer." was auto-allowed on the card (no contact or number in it).
        self.product['producerKey'] = 'oak-farm'
        origin = 'Based in Oakdale'
        def card(name='Oak Farm', place='Oakdale', shown=()):
            return self.verdict(makers={'oak-farm': {'name': name, 'place': place, 'story': 'We grow plums.'}}, origin=origin,
                                card_nodes=[*self.nodes, origin, 'We grow plums.', *shown])
        self.assertNotIn('card-copy', card(shown=['Oak Farm']).problems)
        self.assertIn('card-copy', card(name='This cures cancer.', shown=['This cures cancer.']).problems)
        self.assertIn('card-copy', card(place='Cures cancer', shown=['Cures cancer']).problems)

    def test_computed_origin_line_is_shown_only_when_the_maker_place_behind_it_is_clean(self):
        # Contract: the derived "Based in <place>" origin line cannot launder a place that fails the panel check.
        # Bug caught: with place 'Cures cancer' and the matching computed origin rendered (no separate place node),
        # the origin was unconditionally allowed, so the protected claim showed without card-copy.
        self.product['producerKey'] = 'oak-farm'
        def card(place):
            origin = f'Based in {place}'
            return self.verdict(makers={'oak-farm': {'name': 'Oak Farm', 'place': place, 'story': 'We grow plums.'}}, origin=origin,
                                card_nodes=[*self.nodes, origin, 'We grow plums.', 'Oak Farm'])
        self.assertNotIn('card-copy', card('Oakdale').problems)
        dirty = card('Cures cancer').problems
        self.assertIn('card-copy', dirty)
        self.assertNotIn('origin', dirty)  # the origin line itself is the legitimate computed one; only its source place is unfit
