"""H14 / case 16: the source he types with the photo reaches v1, and a price-only edit keeps it in v2.

Bug (H28, public persimmon fixture): "from Etto $3.50 a lb" kept "from Etto" after the price was read, and the
deterministic S10 reader reads that clause as supplier=Etto, but ProductionStages.start_plan never put a supplier in the
v1 listing. v1's product.add had no supplier (card: "Ask us about the source in store.") and the price-only v2 inherited
the missing source. A later "swap the supplier to River Farm" already worked, through the same reader.
"""
import unittest

from hass.npp import validate
from hass.tests import test_npp_stages as base


class OwnerSupplierTests(unittest.TestCase):
    """Reuses the real stage port fixture (synthetic capture, no model, no network) without re-running its tests."""

    setUp = base.StageTests.setUp
    deny = base.StageTests.deny
    capture = base.StageTests.capture
    start_render = base.StageTests.start_render

    def drafts(self, first, edit=None):
        self.start_render(first)
        self.case.work()
        if edit:
            self.case.say(edit)
            self.case.work()
        return [draft['ops'][-1]['args'] for draft in self.saved]

    def test_typed_source_reaches_v1_and_survives_a_price_only_edit(self):
        v1, v2 = self.drafts('from Etto $7 each', 'make it $8')
        self.assertEqual(v1['supplier'], 'Etto')
        self.assertEqual(v2['supplier'], 'Etto')
        self.assertEqual((v1['sellingPrice'], v2['sellingPrice']), ('7.00 each', '8.00 each'))
        # The price is the only public difference between the two versions.
        self.assertEqual({k for k in v1.keys() | v2.keys() if v1.get(k) != v2.get(k)}, {'sellingPrice'})
        self.assertNotIn('producerKey', v1)
        self.run_research.assert_not_called()
        self.case.assert_unpublished()

    def test_comma_or_semicolon_delimited_source_counts(self):
        for first in ('from Etto, $7 each', 'from Etto; $7 each'):
            with self.subTest(first=first):
                self.setUp()
                [v1] = self.drafts(first)
                self.assertEqual(v1['supplier'], 'Etto')

    def test_no_source_two_sources_or_a_maker_give_no_supplier(self):
        for first in ('$7 each', 'from Etto, from River Farm, $7 each', 'plum preserves from Etto made fresh $7 each',
                      'fresh from the oven $7 each'):
            with self.subTest(first=first):
                self.setUp()
                self.start_render(first)
                self.case.work()
                for draft in self.saved:
                    self.assertNotIn('supplier', draft['ops'][-1]['args'])

    def test_explicit_replacement_still_replaces_the_typed_source(self):
        v1, v2 = self.drafts('from Etto $7 each', 'swap the supplier to River Farm')
        self.assertEqual((v1['supplier'], v2['supplier']), ('Etto', 'River Farm'))
        self.assertEqual(v1['sellingPrice'], v2['sellingPrice'])

    def test_supplier_origin_line_is_the_validated_one(self):
        # validate.listing binds 'From <supplier>' to an owner-said supplier; the drafted record carries it.
        self.drafts('from Etto $7 each')
        [draft] = self.saved
        product = draft['records'][-1]['after']
        self.assertEqual(product.get('supplier'), 'Etto')
        self.assertTrue(validate.valid_supplier(product['supplier']))


if __name__ == '__main__':
    unittest.main()
