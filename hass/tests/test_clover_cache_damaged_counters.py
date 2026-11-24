"""AV1124B-04: a damaged `failures` or `itemCount` meta row in the private till cache must not stop the failure record or the status read.

Contract: an unreadable stored count reads as 0 in `facts()` and in `record_failure()` (which still records failure 1 and starts the usual
backoff); numeric meta and the identity refusal behave exactly as before; the damaged text is never returned.
Believable bug: a bare int() on the stored text raises ValueError, so the failed pull is never recorded (no backoff) and status crashes.
Synthetic fixtures and fake ids only; no token, no network.
Run: python3 -B -m unittest hass.tests.test_clover_cache_damaged_counters
"""
import sqlite3
import unittest
from datetime import timedelta

from hass.clover import cache
from hass.tests.test_clover_cache import PROD_A, PROD_B, CacheCase, fixture_rows
from hass.tests.test_clover_cli import T0

DAMAGED = "zz-damaged-17"   # made-up text that is not a count


class DamagedCounterTests(CacheCase):
    def damage(self, **values):
        db = sqlite3.connect(cache.path_for(self.state))
        with db:
            for key, value in values.items():
                db.execute("UPDATE meta SET value = ? WHERE key = ?", (value, key))
        db.close()

    def good_pull(self):
        cache.write_items(self.state, fixture_rows(), T0, PROD_A)

    def test_facts_with_damaged_counters_reports_zero(self):
        self.good_pull()
        self.damage(failures=DAMAGED, itemCount=DAMAGED)
        facts = cache.facts(self.state, PROD_A)
        self.assertEqual((facts["failures"], facts["itemCount"]), (0, 0))
        self.assertEqual((facts["lastResult"], facts["asOf"], facts["environment"], facts["merchantId"]),
                         ("ok", "2026-11-10T20:00:00+00:00", "production", "FAKEMERCH0001"))   # the rest is still reported
        self.assertNotIn(DAMAGED, repr(facts))
        for key in ("failures", "itemCount"):                                                   # one damaged row alone is enough
            with self.subTest(only=key):
                self.good_pull()
                self.damage(**{key: DAMAGED})
                self.assertEqual(cache.facts(self.state, PROD_A)[key], 0)

    def test_record_failure_with_damaged_failures_starts_backoff(self):
        self.good_pull()
        self.damage(failures=DAMAGED)
        now = T0 + timedelta(minutes=15)
        self.assertEqual(cache.record_failure(self.state, "unreachable", now, identity=PROD_A), 1)
        meta = self.meta()
        self.assertEqual((meta["failures"], meta["lastResult"], meta["nextAttempt"]), ("1", "unreachable", "2026-11-10T20:30:00+00:00"))
        self.assertNotIn(DAMAGED, repr(meta))                                                    # the damaged value is overwritten
        self.assertEqual(cache.facts(self.state, PROD_A)["failures"], 1)
        self.assertEqual(self.item_count(), 6)                                                   # the last good pull is kept
        self.assertEqual(cache.record_failure(self.state, "unreachable", now, identity=PROD_A), 2)   # and the backoff keeps doubling

    def test_numeric_meta_unchanged(self):
        """Healthy control: normal numeric meta gives the exact values it gave before."""
        self.good_pull()
        self.assertEqual(cache.record_failure(self.state, "unreachable", T0 + timedelta(minutes=15), identity=PROD_A), 1)
        self.assertEqual(cache.record_failure(self.state, "unreachable", T0 + timedelta(minutes=30), identity=PROD_A), 2)
        facts = cache.facts(self.state, PROD_A)
        self.assertEqual((facts["failures"], facts["itemCount"], facts["nextAttempt"], facts["lastResult"]),
                         (2, 6, "2026-11-10T21:00:00+00:00", "unreachable"))
        self.assertEqual(self.meta()["failures"], "2")

    def test_other_tills_cache_still_refused(self):
        self.good_pull()
        self.damage(failures=DAMAGED, itemCount=DAMAGED)
        self.assertEqual(cache.facts(self.state, PROD_B), {"refused": "identity", "environment": "production", "merchantId": "FAKEMERCH0001"})
        self.assertEqual(cache.read(self.state, PROD_B), (None, True))
        self.assertEqual(cache.history(self.state, PROD_B), [])
        # the other till's first failure restarts its own record, as before
        self.assertEqual(cache.record_failure(self.state, "unreachable", T0 + timedelta(minutes=15), identity=PROD_B), 1)
        self.assertEqual(cache.facts(self.state, PROD_A)["refused"], "identity")


if __name__ == "__main__":
    unittest.main()
