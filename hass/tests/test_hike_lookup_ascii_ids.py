"""AV1124C-01 tests: an OpenStreetMap element id and its public link accept ASCII digits only.

Synthetic ids only; no network. Contract protected: a route idea Mike approves never carries a look-alike digit
(superscript, Arabic-Indic, full-width) in its id or its openstreetmap.org link. The believable bug is the bare
``str.isdigit()`` test, which is true for those characters.
Run: python3 -B -m unittest hass.tests.test_hike_lookup_ascii_ids -v
"""

import unittest
from datetime import date

from hass import hike_lookup as hl

PLAIN = "https://www.openstreetmap.org/"
LOOKALIKES = {"superscript": "\u00b2", "arabic-indic": "\u0663\u0664", "full-width": "\uff11\uff12"}


def candidate(*osm):
    return hl.Candidate(name="Synthetic Ridge", miles=3.0, gain_ft=300, shape="loop", source="synthetic",
                        retrieved=date(2026, 1, 1), osm=tuple(osm))


class AsciiIdTests(unittest.TestCase):
    def assertBad(self, ident):
        with self.assertRaises(hl.TransportError) as caught:
            hl._element_id({"id": ident})
        self.assertEqual(caught.exception.kind, "bad")

    def test_element_id_refuses_non_ascii_digit_strings(self):
        for label, ident in LOOKALIKES.items():
            with self.subTest(label):
                self.assertBad(ident)

    def test_source_url_refuses_non_ascii_digits(self):
        for label, num in LOOKALIKES.items():
            for kind in ("way", "relation"):
                with self.subTest(label, kind=kind):
                    self.assertEqual(hl.source_url(candidate(f"{kind}/{num}")), PLAIN)

    def test_ascii_and_int_ids_unchanged(self):
        # Healthy control: correct ids and links stay byte-identical; a bool is still refused.
        self.assertEqual(hl._element_id({"id": "123"}), "123")
        self.assertEqual(hl._element_id({"id": 123}), 123)
        self.assertEqual(hl.source_url(candidate("way/123")), PLAIN + "way/123")
        self.assertEqual(hl.source_url(candidate("relation/45")), PLAIN + "relation/45")
        for bad in (True, False):
            with self.subTest(bad):
                self.assertBad(bad)


if __name__ == "__main__":
    unittest.main()
