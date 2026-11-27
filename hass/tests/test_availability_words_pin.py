"""AV1102-03: the catalog filter's current words in shop.js must equal sitegen.AVAILABILITY_WORDS.

Run: python3 -B -m unittest hass.tests.test_availability_words_pin -v
"""

import re
import unittest
from pathlib import Path

from hass import sitegen

SHOP = Path(__file__).resolve().parents[2] / "storefront-mockup" / "shop.js"


def _words(name: str) -> "list[str]":
    sets = re.findall(r"\b" + name + r"=new Set\(\[([^\]]*)\]\)", SHOP.read_text(encoding="utf-8"))
    assert len(sets) == 1, name
    return re.findall(r"'([^']*)'", sets[0])


class AvailabilityWordsPin(unittest.TestCase):
    def test_current_words_match_sitegen(self):
        self.assertEqual(_words("CURRENT"), list(sitegen.AVAILABILITY_WORDS.values()))

    def test_available_words_exclude_sold_out_and_last_confirmed(self):
        self.assertEqual(_words("AVAIL"), [sitegen.AVAILABILITY_WORDS["yes"], sitegen.AVAILABILITY_WORDS["limited"]])


if __name__ == "__main__":
    unittest.main()
