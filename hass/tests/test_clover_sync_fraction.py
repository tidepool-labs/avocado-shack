"""HASS-CLOVER-2 / M4b: the till pull stores each stock quantity as exact text; a small positive count is never stored as 0.
Fake merchant only, no network. Run: python3 -B -m unittest hass.tests.test_clover_sync_fraction -v
"""
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from hass.clover import cache, reports, sync

IDENT = cache.Identity("production", "FAKEMERCH0001")
T0 = datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc)


class SyncFractionCase(unittest.TestCase):
    def setUp(self):
        self.state = Path(tempfile.mkdtemp(prefix="clover-fraction-"))
        self.addCleanup(shutil.rmtree, self.state, True)
        os.chmod(self.state, 0o700)

    def stored(self, quantity):
        """Pull one fake item through sync.rows -> cache -> report, as the 15-minute pull does; (cache text, report section)."""
        rows, skipped = sync.rows([{"id": "FAKEFRACTION01", "name": "Fraction item", "price": 100}],
                                  [{"item": {"id": "FAKEFRACTION01"}, "quantity": quantity}])
        self.assertEqual(skipped, 0)
        cache.write_items(self.state, rows, T0, IDENT)
        snapshot, _ = cache.read(self.state, IDENT)
        self.assertIsNotNone(snapshot)
        sections = reports.low_stock(snapshot)["sections"]
        found = [name for name, items in sections.items() if [i.id for i in items] == ["FAKEFRACTION01"]]
        return snapshot.items[0].stock, rows[0]["stock"], found

    def test_small_positive_quantity_is_kept(self):
        # Contract: the cache holds the till's exact count, so a count above 0 never reads as Sold out.
        # Believable bug caught: sync formats through mapper.format_quantity, which rounds to 3 decimals, so 0.0004 is stored as '0'.
        for quantity, text in ((0.0004, "0.0004"), (0.001, "0.001"), ("0.0004", "0.0004"), (Decimal("0.00049"), "0.00049")):
            with self.subTest(quantity=quantity):
                value, stored, found = self.stored(quantity)
                self.assertEqual((stored, value), (text, Decimal(text)))
                self.assertEqual(found, ["Low stock (at or under 5)"])
        value, stored, found = self.stored(0)
        self.assertEqual((stored, value, found), ("0", Decimal(0), ["Sold out"]))

    def test_healthy_control_and_refusals_unchanged(self):
        # Contract: whole and ordinary decimal counts keep today's text; exponent form never reaches the cache; refusals stay refusals.
        for quantity, text in ((12, "12"), (1.5, "1.5"), ("12.50", "12.5"), ("1E+2", "100"), ("0.000", "0"), (999999999999, "999999999999"), (-3, "-3")):
            with self.subTest(quantity=quantity):
                self.assertEqual(sync._stock_text(quantity), text)
        for bad in (True, False, None, [], "NaN", "Infinity", "abc", float("nan"), float("inf"), 10 ** 12, "1" + "0" * 12):
            with self.subTest(bad=bad):
                self.assertIsNone(sync._stock_text(bad))


if __name__ == "__main__":
    unittest.main()
