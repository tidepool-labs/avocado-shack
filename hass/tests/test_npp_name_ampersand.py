"""Case 3: a product printed as "Half & Half" still gets a name, so its card can be drawn.

The Writer binds the item slot only for a plain value. "M&M" was plain but the label's spaced
"Half & Half" was not, so every name template lacked its item slot, write() returned None and the
owner got "I couldn't draw the card yet" on both turns. A spaced '&' is now one more joiner;
markup, punctuation runs and leading/trailing joiners stay refused.
"""
import unittest

from hass.npp import assets
from hass.npp.copy import Context, Writer, plain


class SpacedAmpersandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.writer = Writer(assets())

    def test_label_names_with_a_spaced_ampersand_are_plain(self):
        for value in ('Half & Half', 'Smith & Sons', 'Salt & Pepper Chips', 'M&M', "Bob's Red Mill",
                      'half-and-half'):
            with self.subTest(value=value):
                self.assertTrue(plain(value))

    def test_other_joiners_and_markup_stay_refused(self):
        for value in ('Half &  Half', 'Half && Half', 'Half & ', ' & Half', '& Half', 'Half &',
                      'Half &amp; Half', 'Half <b>&</b> Half', 'Half & & Half', 'Half  Half',
                      'Half , Half', 'Half & Half!', 'Half &\nHalf', ''):
            with self.subTest(value=value):
                self.assertFalse(plain(value))

    def test_spaced_ampersand_item_renders_a_name_and_a_card(self):
        ctx = Context('food', 'dairy', 'polished', 'Half & Half',
                      owner_words='made by Straus, Straus half-and-half, $7 each', brand='Straus')
        result = self.writer.write(ctx)
        self.assertIsNotNone(result)
        self.assertEqual(result.text['name'], 'Half & Half')
        self.assertIn('Half & Half', result.text['description'])
        self.assertIn('Half & Half', result.text['imageAlt'])
        branded = self.writer.write(ctx, lambda *_: {'name': {'template_id': 'name-brand-item'}})
        self.assertEqual(branded.text['name'], 'Straus Half & Half')

    def test_unspaced_neighbour_unchanged(self):
        ctx = Context('food', 'pantry', 'raw', 'M&M')
        self.assertEqual(self.writer.write(ctx).text['name'], 'M&M')


if __name__ == '__main__':
    unittest.main()
