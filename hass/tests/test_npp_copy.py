"""S5 contract: only pinned IDs, locally bound slots, and independently checked final strings."""
from dataclasses import replace
import json
import unittest

from hass.npp import assets
from hass.cloud_codex import CodexTransport
from hass.npp.copy import Context, Fact, Writer, codex_selector
from hass.npp.private_numbers import finance


def selection(ctx_kind='food'):
    return {'name': {'template_id': 'name-item'}, 'imageAlt': {'template_id': 'alt-photo'},
            'description': {'template_id': 'desc-food-plain', 'phrase_ids': [f'{ctx_kind}-{bank}-1' for bank in ('open', 'use', 'close')]},
            'story': None}


class CopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pinned = assets()
        cls.writer = Writer(cls.pinned)

    def test_fabricated_prose_falls_back_per_field_even_with_no_keyword_hit(self):
        # Cases 30/36: a keyword-only filter would accept the unsupported method.
        ctx = Context('food', 'pantry', 'raw', 'beans')
        expected = self.writer.write(ctx, lambda *_: selection())
        planted = 'The beans are roasted in copper pans.'
        proposed = {**expected.text, 'description': planted}
        self.assertFalse(self.writer.conform(proposed, expected.selections, ctx))
        for chooser, final in [(lambda *_: selection(), proposed),
                               (lambda *_: {**selection(), 'description': {'text': planted}}, None)]:
            result = self.writer.write(ctx, chooser, proposed=final)
            self.assertTrue(result.basic)
            self.assertEqual(result.text['description'], 'Pick up beans for the kitchen. Set beans out on the table.')
            self.assertEqual(result.text['imageAlt'], expected.text['imageAlt'])

    def test_selection_transport_contains_only_ids_no_private_or_owner_projection(self):
        # Case 33: capture the actual adapter argument, not just intended schema.
        f = finance('4 or 5 bucks, got 4')
        ctx = Context('food', 'pantry', 'raw', 'beans', owner_words='4 or 5 bucks, got 4; private filler', private=f.private)
        def offline(step, prompt, schema, payload):
            self.assertEqual((step['model'], step['effort'], step['timeout_s']), ('gpt-6.2-sol', 'low', 16))
            self.assertFalse(schema['additionalProperties'])
            self.assertEqual(set(payload), {'kind', 'category', 'templates', 'phrase_ids', 'fact_ids'})
            for private in ('4', '5', 'private filler', 'beans', 'bucks'):
                self.assertNotIn(private, json.dumps(payload))
            raise TimeoutError
        self.assertTrue(self.writer.write(ctx, offline).basic)

        def runner(req):
            self.assertEqual((req['model'], req['effort'], req['timeout'], req['images']), ('gpt-6.2-sol', 'low', 16, []))
            self.assertIn('Eligible IDs:', req['instructions'])
            for private in ('private filler', 'beans', 'bucks', '4 or 5'):
                self.assertNotIn(private, req['instructions'] + req['text'])
            return {'ok': True, 'text': json.dumps(selection())}
        result = self.writer.write(ctx, codex_selector(CodexTransport(runner=runner)))
        self.assertFalse(result.basic)  # the real transport guard did not send this to fallback

    def test_copying_swaps_one_phrase_then_uses_two_anchored_rungs(self):
        # A fallback that just picks a generic bank phrase can copy a neighboring listing.
        ctx = Context('food', 'pantry', 'raw', 'beans')
        choice = lambda *_: selection()
        first = self.writer.write(ctx, choice)
        swapped = self.writer.write(replace(ctx, other_descriptions=(first.text['description'],)), choice)
        self.assertEqual(swapped.selections['description']['template_id'], 'desc-food-plain')
        self.assertNotEqual(swapped.text['description'], first.text['description'])
        anchored = replace(ctx, item='black beans')
        rung_a = self.writer.write(anchored)
        rung_b = self.writer.write(replace(anchored, other_descriptions=(rung_a.text['description'],)))
        self.assertEqual(rung_b.text['description'], 'Take black beans home. Keep black beans handy.')
        self.assertIsNone(self.writer.write(replace(anchored, other_descriptions=(rung_a.text['description'], rung_b.text['description']))))

    def test_story_binds_only_kept_typed_fact_ids(self):
        # Unknown, unrelated, uncited, or contradicting facts cannot seed a story.
        found = Fact('f-year', 'founded', '1982', 'https://orchard.example/about', 'Bay Orchard was founded in 1982.', 'supports')
        ctx = Context('food', 'pantry', 'raw', 'beans', owner_words='Made by Bay Orchard', maker_name='Bay Orchard', facts=(found,))
        result = self.writer.write(ctx)
        self.assertIn('founded in 1982.', result.text['story'])
        self.assertNotIn('1982', result.text['description'])
        bad = {**result.selections, 'story': {**result.selections['story'], 'fact_ids': ['unrelated']}}
        self.assertFalse(self.writer.conform(result.text, bad, ctx))
        for evidence in (replace(found, verdict='unclear'), replace(found, quote='The maker sells beans.'),
                         replace(found, url=''), replace(found, source='directory')):
            self.assertNotIn('story', self.writer.write(replace(ctx, facts=(evidence,))).text)

    def test_offered_story_templates_can_bind_evidence(self):
        # S5 selector contract: slot presence alone advertises a choice the renderer will refuse.
        # Use identity slots in a synthetic template: unlike makes/nature/founded, they can
        # be fully populated by owner words without carrying fact IDs.
        pins, files, digest = self.pinned
        path = 'hass-listing-copy/copy-templates.json'
        spec = json.loads(files[path])
        story_id = 'story-test-attested-base'
        spec['templates'].append({
            'id': story_id, 'field': 'story', 'kinds': ['food'],
            'text': '{maker_name} is based in {town}.',
            'slots': {'maker_name': 'maker_name', 'town': 'town'},
            'requires_facts_any': ['maker_name'], 'requires_facts_all': ['town'],
        })
        writer = Writer((pins, {**files, path: json.dumps(spec).encode()}, digest))
        maker, town = 'Bay Orchard', 'Test Harbor'
        url = 'https://orchard.example/about'
        name_fact = Fact('f-maker', 'name', maker, url, 'Our name is Bay Orchard.', 'supports')
        town_fact = Fact('f-town', 'town', town, url, 'Our base is Test Harbor.', 'supports')
        cases = (
            ('owner only', (maker, town), (), {}, False),
            ('missing all', (town,), (name_fact,), {'maker_name': 'f-maker'}, False),
            ('missing any', (maker,), (town_fact,), {'town': 'f-town'}, False),
            ('attested', (), (name_fact, town_fact), {'maker_name': 'f-maker', 'town': 'f-town'}, True),
        )
        for case, owner_slots, facts, expected_ids, offered in cases:
            with self.subTest(case=case):
                ctx = Context('food', 'pantry', 'raw', 'beans', maker_name=maker, town=town,
                              owner_words='\n'.join((*owner_slots, 'private filler')), facts=facts)
                requests = []

                def choose(_step, _prompt, _schema, options):
                    requests.append(options)
                    choice = selection()
                    if story_id in options['templates']['story']:
                        choice['story'] = {'template_id': story_id, 'phrase_ids': [],
                                           'fact_ids': list(options['fact_ids'].values())}
                    return choice

                result = writer.write(ctx, choose)
                payload, = requests
                self.assertEqual(payload['fact_ids'], expected_ids)
                self.assertTrue(set(selection()['description']['phrase_ids']) <= set(payload['phrase_ids']))
                for plain_value in (maker, town, 'private filler', 'beans'):
                    self.assertNotIn(plain_value, json.dumps(payload))
                self.assertEqual(story_id in payload['templates']['story'], offered)
                self.assertFalse(result.basic)
                if offered:
                    self.assertEqual(result.selections['story']['template_id'], story_id)
                    self.assertEqual(result.text['story'], 'Bay Orchard is based in Test Harbor.')
                    self.assertTrue(writer.conform(result.text, result.selections, ctx))
                else:
                    self.assertNotIn('story', result.text)

    def test_health_claims_drop_before_public_copy_with_one_safe_note(self):
        # F12 and case 15: the claim does not refuse an otherwise complete product or enter copy.
        ctx = Context('drink', 'drinks', 'raw', 'elderberry syrup, cures colds', label_claims=('cures colds',))
        result = self.writer.write(ctx)
        self.assertEqual(result.text['name'], 'Elderberry syrup')
        self.assertNotIn('cures', ' '.join(result.text.values()))
        self.assertEqual(result.dropped, ('cures colds',))
        control = self.writer.write(replace(ctx, item='elderberry syrup', label_claims=('immune support',)))
        self.assertEqual(control.dropped, ('immune support',))

    def test_pinned_gallery_identity_renders_new_copy_without_reusing_descriptions(self):
        # Golden projections are pinned reference inputs, not permission to reuse their exact text.
        files = self.pinned[1]
        goldens = [json.loads(data) for path, data in files.items() if '/golden/' in path]
        catalog = tuple(g['card']['description'] for g in goldens)
        self.assertEqual(len(goldens), 12)
        for g in goldens:
            card, category = g['card'], g['category']
            kind = 'fresh' if category == 'flowers' else 'drink' if category == 'drinks' else 'food'
            maker = card.get('meet_the_maker') or {}
            brand = card['brand'] if maker else ''
            item = card['name'].removeprefix(brand + ' ') if brand else card['name']
            ctx = Context(kind, category, 'house', item, owner_words=brand, brand=brand, other_descriptions=catalog)
            with self.subTest(case=g['product_id']):
                choice = {**selection(), 'name': {'template_id': 'name-brand-item' if brand and item != card['name'] else 'name-item'},
                          'imageAlt': {'template_id': 'alt-plain-bg'}}
                result = self.writer.write(ctx, lambda *_: choice)
                self.assertIsNotNone(result, item)
                self.assertTrue(self.writer.conform(result.text, result.selections, ctx))
                self.assertEqual(result.text['name'].casefold(), card['name'].casefold())
                self.assertNotIn(result.text['description'], catalog)
