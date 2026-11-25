"""Finance provenance and independent numeric evidence, with synthetic captions/OCR."""
from decimal import Decimal
import re
import unittest

from hass.npp import private_numbers as pn


class Numbers(unittest.TestCase):
    def test_numeric_spans_cover_digits_grouping_and_spoken_equivalents(self):
        # A split/digit-only scanner misses dictation, grouped numbers and private cents.
        for text, wanted in [('1,200', {1200}), ('2.50', {Decimal('2.50')}), ('$3', {3}),
                             ('3 bucks', {3}), ('twenty five', {25}),
                             ('three fifty', {350, Decimal('3.50')}), ('a dozen', {12}), ('half a dozen', {6})]:
            with self.subTest(text=text):
                (n,) = pn.values('Look: ' + text)
                self.assertTrue(wanted <= n.amounts)
                self.assertTrue(pn.problem(text, wanted))
                self.assertEqual(n.start, 6 + int(text.startswith('$')))

    def test_equal_cost_and_price_require_separate_typed_spans(self):
        # Same value is allowed in the structured price, not in any other text.
        for caption, price in (('cost $3; sell $3 each; qty 12', 3),
                               ('cost three dollars; sell three dollars each; qty twelve', 3),
                               ('cost 14, selling 14 each, got 12 bags', 14),
                               ('cost fourteen, selling fourteen each, got twelve bags', 14)):
            with self.subTest(caption=caption):
                finance = pn.finance(caption)
                self.assertEqual(finance.selling_price, f'{price}.00 each')
                self.assertEqual(caption[slice(*finance.price_span)].strip(), re.split('[;,]', caption)[1].strip())
                self.assertEqual(finance.private, {price, price * 100, 12})
                self.assertTrue(finance.has_cost and finance.has_qty)
                self.assertEqual(finance.public_words, '')

    def test_ambiguous_or_unproven_amount_is_missing_not_model_guess(self):
        # A plausible local-model answer cannot bless ambiguous digits or a private cost's unit.
        local = dict(price_cents=500, cost_cents=None, quantity=None)
        for text in ('4 or 5 bucks, got 4', 'cost $4 per lb; sell $5', 'sell $5 each; sell $6 each',
                     'sell $5 per basket', 'selling fourteen or fifteen each', 'selling fourteen per basket',
                     'selling fourteen each; selling fifteen each', 'cost fourteen each; got twelve bags'):
            with self.subTest(text=text):
                result = pn.finance(text, local_answers=local)
                self.assertIsNone(result.selling_price)
                self.assertIsNone(result.price_span)
                self.assertFalse(any(c.isdigit() for c in result.public_words))
        self.assertEqual(pn.finance('three dollars', answer_unit='per lb').selling_price, '3.00 per lb')
        self.assertEqual(pn.finance('3.50 per lb', answer_unit='each').selling_price, '3.50 per lb')
        self.assertIsNone(pn.finance('12 oz').selling_price)

    def test_picture_exemption_needs_label_and_source_ocr_and_never_licenses_money(self):
        # A typed label size doesn't excuse another occurrence or a sticker.
        self.assertIsNone(pn.picture_problem('Jam 12 oz', 'Jam 12 oz', ['12 oz'], {12}))
        for read, source, expected in [('Jam 12 oz', 'Jam', 'private-number'),
                                       ('Jam 12 oz twelve', 'Jam 12 oz', 'private-number'),
                                       ('Jam $12', 'Jam $12', ['$12']), ('Jam 3.50', 'Jam', 'money'),
                                       (None, 'Jam', 'picture-unreadable')]:
            with self.subTest(read=read):
                if isinstance(expected, list):
                    self.assertEqual(pn.picture_problem(read, source, expected, {12}), 'money')
                else:
                    self.assertEqual(pn.picture_problem(read, source, ['12 oz'], {12}), expected)

    def test_unreadable_or_approximate_tokens_fail_closed(self):
        # A scanner must not ignore malformed/spelled amounts it cannot parse.
        for text in ('maybe twelve', 'four or five', 'a hundred', 'two point six', 'Ⅳ', 'Ｆｏｏ１２'):
            with self.subTest(text=text):
                self.assertEqual(pn.problem(text), 'number-unclear')

    def test_half_and_half_is_a_product_name_not_a_quantity(self):
        # Golden case 3 (live recording): "Straus half-and-half, $7 each" asked for the price again, and the
        # printed "Half & Half" label made the own-photo fallback a retake.
        for caption in ('made by Straus, Straus half-and-half, $7 each', 'Straus half and half, $7 each',
                        'Half & Half, $7 each', "half 'n' half, $7 each"):
            with self.subTest(caption=caption):
                finance = pn.finance(caption)
                self.assertEqual(finance.selling_price, '7.00 each')
                self.assertEqual(caption[slice(*finance.price_span)].strip(), '$7 each')
                self.assertEqual(finance.private, frozenset())
        for label in ('Half & Half', 'ORGANIC HALF & HALF', 'Half&Half', 'half-and-half', 'Half and Half'):
            with self.subTest(label=label):
                self.assertIsNone(pn.picture_problem(label, label, []))
        # Only the whole idiom is exempt: a loose fraction, a count or money still fails closed.
        for text, expected in (('half a crate', 'number-unclear'), ('Half & Half half', 'number-unclear'),
                               ('Half & Half $7', 'money')):
            with self.subTest(text=text):
                self.assertEqual(pn.problem(text, digits_allowed=True), expected)
        self.assertIsNone(pn.finance('half-and-half, $7 each; half a crate').selling_price)
        counted = pn.finance('half & half $7 each, got half a dozen')
        self.assertEqual((counted.selling_price, counted.private, counted.has_qty), ('7.00 each', {6}, True))
