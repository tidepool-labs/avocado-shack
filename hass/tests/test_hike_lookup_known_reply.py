"""Pin ``hike_lookup.known_reply()``: the sentence Mike reads when a hike name fits a route idea he already has.

Pure call on synthetic ideas: no network, no files, no clock. The ``voice.quote`` marks are taken from ``voice.quote()`` itself.
The optional distance is appended as given; a distance with an embedded newline is deliberately not asserted here.
Run: python3 -B -m unittest hass.tests.test_hike_lookup_known_reply -v
"""
import unittest

from hass import hike_lookup as hl, voice

TAIL = " I'll use that one, with no new lookup. Tell me the day, the time and where to meet, and I'll set up the hike."


def sentence(title, distance=None):
    far = f", {distance}" if distance else ""
    return f"You already have a route idea called {voice.quote(title)}{far}." + TAIL


class KnownReply(unittest.TestCase):
    # Contract: Mike is told, in these exact words, that his existing route idea is used and no lookup runs.
    # Bug that fails it: the wording, punctuation or the order of the clauses drifts, so the one sentence he reads changes silently.
    def test_reply_with_distance_exact(self):
        self.assertEqual(hl.known_reply({"title": "Cerro Alto Loop", "distance": "3.5 miles"}),
                         sentence("Cerro Alto Loop", "3.5 miles"))

    # Contract: an idea with no distance (missing, None or empty) gets no ", <distance>" part and no stray comma.
    # Bug that fails it: the distance clause is always added, or a dangling ", " / ", None" is printed.
    def test_reply_without_distance_exact(self):
        for idea in ({"title": "Cerro Alto Loop"}, {"title": "Cerro Alto Loop", "distance": None},
                     {"title": "Cerro Alto Loop", "distance": ""}):
            with self.subTest(idea=idea):
                self.assertEqual(hl.known_reply(idea), sentence("Cerro Alto Loop"))

    # Contract: the title is cleaned (markup gone, runs of spaces folded), cut at 60 characters after cleaning, and wrapped
    # by voice.quote so it shows as Mike's own words.
    # Bug that fails it: the raw title is printed (markup or double spaces reach Mike), the cut is longer or shorter than 60,
    # or the quote marks are dropped.
    def test_title_is_cleaned_quoted_and_cut(self):
        messy = hl.known_reply({"title": "Cerro  Alto <b>Loop", "distance": "3.5 miles"})
        self.assertNotIn("<b>", messy)
        self.assertNotIn("  ", messy)
        self.assertIn(voice.quote("Cerro Alto Loop"), messy)
        self.assertEqual(messy, sentence("Cerro Alto Loop", "3.5 miles"))
        # Control: a plain title passes through unchanged.
        self.assertEqual(hl.known_reply({"title": "Bishop Peak"}), sentence("Bishop Peak"))
        # Markup is removed before the cut, so the cut keeps a full 60 characters of the title.
        long = hl.known_reply({"title": "<i>" + "Ab" * 40 + "</i>"})
        self.assertEqual(long, sentence("Ab" * 30))
        self.assertIn(voice.OPEN + "Ab" * 30 + voice.CLOSE, long)
        self.assertNotIn("Ab" * 31, long)
        self.assertNotIn("<", long)


if __name__ == "__main__":
    unittest.main()
