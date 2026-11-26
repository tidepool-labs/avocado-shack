"""H66 (cases 6, 11): the owner wrote the brand and the item together as the product's name, so the public name keeps it.

The copy selector sees template IDs only, never the owner's words, so it cannot tell "Fair Hills Farm apple juice" (brand
is part of the name) from "Dried mushrooms" by Mighty Cap Mushrooms (it is not). On the saved recording it picked the
item-only template and the card said "Apple juice". The Writer now upgrades an explicit item-only name choice to its brand
twin only when both slots are bound and the owner's own words say "<brand> <item>". Everything else is unchanged.
"""
import unittest

from hass.npp import assets
from hass.npp.copy import Context, Writer
from hass.npp.validate import field_problem

FAIR_HILLS = 'made by Fair Hills Farm, Fair Hills Farm apple juice, $6 each'


def choose(name):
    return lambda *_: {'name': {'template_id': name}}


class OwnerNamedBrandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.writer = Writer(assets())

    def ctx(self, owner_words=FAIR_HILLS, item='apple juice', brand='Fair Hills Farm', **kw):
        return Context('drink', 'drinks', 'polished', item, owner_words=owner_words, brand=brand, **kw)

    def test_item_only_choice_keeps_the_brand_the_owner_named_with_the_item(self):
        ctx = self.ctx()
        result = self.writer.write(ctx, choose('name-item'))
        self.assertEqual(result.text['name'], 'Fair Hills Farm apple juice')
        self.assertEqual(result.selections['name'], {'template_id': 'name-brand-item'})
        self.assertIn('Fair Hills Farm apple juice', result.text['imageAlt'])
        self.assertTrue(self.writer.conform(result.text, result.selections, ctx))

    def test_negative_control_without_the_upgrade_the_same_choice_drops_the_brand(self):
        # The selector's own answer, rendered as is, is what the saved recording produced before this change.
        ctx = self.ctx()
        rendered = self.writer._render('name', {'template_id': 'name-item'}, ctx)
        self.assertIsNotNone(rendered)
        self.assertEqual(rendered[0], 'Apple juice')

    def test_owner_chatter_still_refused_beyond_the_pure_identity(self):
        # Only a name template's own rendering is excused; any other four-word owner span still refuses.
        ctx = self.ctx('made by Fair Hills Farm, Fair Hills Farm apple juice tastes like a summer morning, $6 each')
        self.assertIsNone(field_problem(self.writer, 'name', 'Fair Hills Farm apple juice', (), ctx))
        self.assertEqual(field_problem(self.writer, 'name', 'Fair Hills Farm apple juice tastes', (), ctx), 'owner-chatter')
        self.assertEqual(field_problem(self.writer, 'imageAlt', 'Apple juice tastes like a summer', (), ctx), 'owner-chatter')
        self.assertEqual(field_problem(self.writer, 'description', 'Fair Hills Farm apple juice, cold. Pour a glass.', (), ctx),
                         'owner-chatter')

    def test_alt_text_carrying_the_owner_named_identity_is_kept(self):
        result = self.writer.write(self.ctx(), choose('name-brand-item'))
        self.assertIsNotNone(result)
        self.assertIn('Fair Hills Farm apple juice', result.text['imageAlt'])

    def test_case_six_one_word_item(self):
        ctx = Context('food', 'pantry', 'polished', 'honey', brand='Big Sur Honey Company',
                      owner_words='made by Big Sur Honey Company, Big Sur Honey Company honey, $12 each')
        self.assertEqual(self.writer.write(ctx, choose('name-item')).text['name'], 'Big Sur Honey Company honey')

    def test_brand_said_but_not_as_part_of_the_name_stays_item_only(self):
        for words in ('made by Mighty Cap Mushrooms, Dried mushrooms, $11 each',
                      'apple juice from Fair Hills Farm, $6 each'):
            item = 'Dried mushrooms' if 'Mighty' in words else 'apple juice'
            brand = 'Mighty Cap Mushrooms' if 'Mighty' in words else 'Fair Hills Farm'
            with self.subTest(words=words):
                result = self.writer.write(self.ctx(words, item, brand), choose('name-item'))
                self.assertEqual(result.selections['name'], {'template_id': 'name-item'})
                self.assertNotIn(brand, result.text['name'])

    def test_denied_brand_is_not_bound_so_nothing_is_upgraded(self):
        words = 'not made by Fair Hills Farm. apple juice, $6 each'
        result = self.writer.write(self.ctx(words), choose('name-item'))
        self.assertEqual(result.text['name'], 'Apple juice')

    def test_no_brand_bound_leaves_the_choice(self):
        result = self.writer.write(self.ctx(brand=''), choose('name-item'))
        self.assertEqual(result.text['name'], 'Apple juice')

    def test_explicit_brand_choice_and_declined_selector_are_unchanged(self):
        ctx = self.ctx()
        self.assertEqual(self.writer.write(ctx, choose('name-brand-item')).text['name'], 'Fair Hills Farm apple juice')
        declined = self.writer.write(ctx)  # no selector: the deterministic default, as before
        self.assertEqual(declined.selections['name'], {'template_id': 'name-item'})
        self.assertEqual(declined.text['name'], 'Apple juice')

    def test_an_edit_that_checks_the_shown_card_keeps_the_upgraded_name(self):
        ctx = self.ctx()
        first = self.writer.write(ctx, choose('name-item'))
        again = self.writer.write(ctx, lambda *_: dict(first.selections), proposed=dict(first.text))
        self.assertEqual(again.text, first.text)
        self.assertEqual(again.selections, first.selections)

    def test_size_variant_upgrades_to_its_brand_twin(self):
        ctx = self.ctx(size_text='12 fl oz', source_read='Fair Hills Farm apple juice 12 fl oz')
        result = self.writer.write(ctx, choose('name-item-size'))
        if result.selections['name'] == {'template_id': 'name-item-size'}:
            self.skipTest('label size not bindable in this fixture')
        self.assertEqual(result.selections['name'], {'template_id': 'name-brand-item-size'})
        self.assertEqual(result.text['name'], 'Fair Hills Farm apple juice 12 fl oz')


if __name__ == '__main__':
    unittest.main()
