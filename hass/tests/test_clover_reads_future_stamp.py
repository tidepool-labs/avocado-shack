"""AV1124D-05: a till snapshot stamped in the future is never quoted as fresh. Synthetic fixtures only.
Run: python3 -B -m unittest hass.tests.test_clover_reads_future_stamp -v

Contract: a stamp more than 5 minutes after `now` (a clock jump, a restored backup, a hand-edited cache) has no knowable age, so it is
`too-old` (not quoted); up to 5 minutes ahead is ordinary clock skew and stays `fresh`; everything at or before `now` is unchanged.
"""
import unittest
from datetime import datetime, timedelta, timezone

from hass.clover import reads
from hass.tests.test_clover_mapper import items

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
CANT_TELL = ("I can't tell how old the till count is, so I will not quote it. "
             "Check the till, or ask me again in a few minutes.")
M = timedelta(minutes=1)


def snap(fetched_at):
    return reads.Snapshot(tuple(items().values()), fetched_at)


def fresh(delta, reachable=True):
    return reads.freshness(snap(NOW + delta), NOW, reachable)


class FutureStampTests(unittest.TestCase):
    # Protects: a future stamp has a negative age, so a bug that compares only the upper bounds calls it fresh with no 'as of' label.
    def test_future_stamp_beyond_skew_is_not_quoted(self):
        for delta in (10 * M, timedelta(days=3), 5 * M + timedelta(seconds=1)):
            for reachable in (True, False):
                with self.subTest(ahead=delta, reachable=reachable):
                    self.assertEqual(fresh(delta, reachable), ("too-old", CANT_TELL))

    # Protects: the skew allowance. A bug that rejects every future stamp would refuse counts over ordinary clock skew.
    def test_small_skew_still_fresh(self):
        for delta in (timedelta(0), 4 * M, 5 * M):
            with self.subTest(ahead=delta):
                self.assertEqual(fresh(delta), ("fresh", ""))

    # Healthy control: every stamp at or before now keeps today's state and label.
    def test_past_states_unchanged(self):
        at = reads.when(NOW - 25 * timedelta(hours=1), NOW)
        for age, reachable, want in (
                (10 * M, True, ("fresh", "")),
                (21 * M, True, ("stale", f"(till count as of {reads.when(NOW - 21 * M, NOW)})")),
                (timedelta(hours=25), True, ("too-old", f"I have not been able to read the till since {at}, "
                                             "so I will not quote a count that old. Check the till, or ask me again in a few minutes.")),
                (21 * M, False, ("unreachable", "I can't reach the till right now. The last count I have is from "
                                 f"{reads.when(NOW - 21 * M, NOW)}, so treat it as old."))):
            with self.subTest(age=age, reachable=reachable):
                self.assertEqual(fresh(-age, reachable), want)

    # Protects: the public answer. A caller must not turn a future-stamped snapshot into a quoted count.
    def test_how_many_does_not_quote_a_future_count(self):
        reply = reads.how_many("hass avocado", snap(NOW + 10 * M), NOW)
        self.assertEqual(reply, CANT_TELL)
        self.assertNotIn("40", reply)
        self.assertEqual(reads.how_many("hass avocado", snap(NOW - 5 * M), NOW), "Hass avocado: 40 in the till.")


if __name__ == "__main__":
    unittest.main()
