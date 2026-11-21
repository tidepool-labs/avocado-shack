"""HCI-18: held-out synthetic sentences for the local count parser."""

import ast
from collections import Counter
from decimal import Decimal
from pathlib import Path
import re
from unittest import expectedFailure

from hass.clover.qty_words import CountIntent, parse
from hass.tests.test_clover_client import NoNetwork


ROOT = Path(__file__).resolve().parents[2]


def intent(mode, quantity, unit, query):
    return CountIntent(mode, Decimal(quantity), unit, query)


# Expected values describe what the speaker meant, not what parse returns today.
# Queries are text for lookup, not assertions that a product exists or matches.
PHRASES = (
    ("word order", "12 apricot jams just came in", intent("add", "12", None, "apricot jams")),
    ("word order", "30 blue mugs in", intent("add", "30", None, "blue mugs")),
    ("word order", "we got 8 more of the enamel trays", intent("add", "8", None, "enamel trays")),
    ("word order", "ceramic strainers: 5", intent("count", "5", None, "ceramic strainers")),
    ("word order", "the glass pitchers just arrived, 9 of them", intent("add", "9", None, "glass pitchers")),
    ("shorthand", "blue mug x30", intent("count", "30", None, "blue mug")),
    ("shorthand", "x14 linen bags", intent("count", "14", None, "linen bags")),
    ("shorthand", "pan scrapers = 11", intent("count", "11", None, "pan scrapers")),
    ("shorthand", "cork mats: 16!", intent("count", "16", None, "cork mats")),
    ("shorthand", "+7 lemon soaps", intent("add", "7", None, "lemon soaps")),
    ("units", "got 1.75 pounds of hazelnuts", intent("add", "1.75", "lb", "hazelnuts")),
    ("units", "we have 4lb of dried cherries", intent("count", "4", "lb", "dried cherries")),
    ("units", "ground rye: 2.25 lbs", intent("count", "2.25", "lb", "ground rye")),
    ("units", "just got 6 lb of split peas", intent("add", "6", "lb", "split peas")),
    ("units", "we have 15 each of the wax wraps", intent("count", "15", None, "wax wraps")),
    ("number words", "there are forty-two felt coasters", intent("count", "42", None, "felt coasters")),
    ("number words", "we got a dozen and a half cake boxes", intent("add", "18", None, "cake boxes")),
    ("number words", "sixteen of the copper scoops", intent("count", "16", None, "copper scoops")),
    ("number words", "a hundred and six paper straws", intent("count", "106", None, "paper straws")),
    ("number words", "three dozen cloth filters came in", intent("add", "36", None, "cloth filters")),
    ("shelf words", "put 30 mugs on the shelf", intent("count", "30", None, "mugs")),
    ("shelf words", "only 4 cedar soap dishes left", intent("count", "4", None, "cedar soap dishes")),
    ("shelf words", "11 jam spoons on the shelf now", intent("count", "11", None, "jam spoons")),
    ("shelf words", "we have 18 cork trivets in stock", intent("count", "18", None, "cork trivets")),
    ("shelf words", "on the shelf there's 7 butter crocks", intent("count", "7", None, "butter crocks")),
    ("typos", "WE  HAVE  6  linnen napkins ", intent("count", "6", None, "linnen napkins")),
    ("typos", "recevied 8 maple spreaders", intent("add", "8", None, "maple spreaders")),
    ("typos", "got 9 emamel cups!", intent("add", "9", None, "emamel cups")),
    ("typos", "there re 5 mixing bowls", intent("count", "5", None, "mixing bowls")),
    ("typos", "5 bown sugar scoops on the slehf", intent("count", "5", None, "bown sugar scoops")),
    # Refusals: non-inventory requests and insufficiently specific counts.
    ("vague", "around 20 cork lids", None),
    ("vague", "we got a handful of sachets", None),
    ("vague", "we have 8 or 9 drink mats", None),
    ("vague", "somewhere near 15 wire baskets", None),
    ("vague", "we got 4 or 5 more storage jars", None),
    ("money", "$19 for the linen roll", None),
    ("money", "got 17 dollars for the apron", None),
    ("money", "the deposit was $31", None),
    ("two products", "we got 6 honey jars plus 5 pickle jars", None),
    ("two products", "we have 7 blue plates and 4 yellow ones", None),
    ("two products", "12 jam jars, 8 jam spoons", None),
    ("two products", "oak boards: 4 and beech boards: 3", None),
    ("questions", "do we still have 11 glass tumblers", None),
    ("questions", "we have 16 tea tins, right?", None),
    ("questions", "will 14 baskets be enough", None),
    ("questions", "did 9 ceramic colanders come in yet", None),
    ("questions", "how many of the 12 spatulas are left?", None),
    ("prices", "set the price of the pie server to 13", None),
    ("prices", "change the price of the small kettle to 17", None),
    ("prices", "make the bamboo tongs 6 dollars each", None),
    ("prices", "price the berry bowl at $18 each", None),
    ("hikes", "meet at 8 for the bluff walk", None),
    ("hikes", "move the loop hike to the 16th", None),
    ("website edits", "hide the 4 gift bundles on the website", None),
    ("website edits", "put the 7 tea listings under pantry", None),
    ("website edits", "show 8 featured items on the home page", None),
)

# Each known false accept gets its own expectedFailure, never a KNOWN_GAPS entry.
FALSE_ACCEPTS = (
    ("bucks", "money", "12 bucks for the tea tin", "Treats bucks as part of the product name."),
    ("two_products", "two products", "6 cloth bags and a fruit basket", "Combines two products into one query."),
    ("hike_miles", "hikes", "9 miles for the ridge hike", "Treats the hike distance as a count."),
    ("website_photo", "website edits", "set the website photo of the wooden ladle to 3",
     "Treats a photo choice as a stock set."),
)
PHRASES += tuple((category, text, None) for _, category, text, _ in FALSE_ACCEPTS)

KNOWN_GAPS = (
    ("12 apricot jams just came in", "code"),
    ("30 blue mugs in", "code"),
    ("the glass pitchers just arrived, 9 of them", "code"),
    ("blue mug x30", "code"),
    ("x14 linen bags", "code"),
    ("pan scrapers = 11", "code"),
    ("+7 lemon soaps", "code"),
    ("we have 4lb of dried cherries", "code"),
    ("just got 6 lb of split peas", "code"),
    ("we have 15 each of the wax wraps", "code"),
    ("we got a dozen and a half cake boxes", "code"),
    ("a hundred and six paper straws", "code"),
    ("put 30 mugs on the shelf", "ask"),  # Could be a move, a new arrival, or a tally.
    ("only 4 cedar soap dishes left", "code"),
    ("we have 18 cork trivets in stock", "code"),
    ("on the shelf there's 7 butter crocks", "code"),
    ("recevied 8 maple spreaders", "code"),
    ("there re 5 mixing bowls", "code"),
    ("5 bown sugar scoops on the slehf", "code"),
)


class CountPhraseTests(NoNetwork):
    def test_c1_table(self):
        # C1: Copying the seed table or replacing a refusal with an inventory
        # example would make this held-out measurement misleading.
        self.assertEqual(len(PHRASES), 60)
        texts = {text for _, text, _ in PHRASES}
        self.assertEqual(len(texts), 60)
        seed = Path(__file__).with_name("test_clover_qty_words.py")
        seed_source = ast.parse(seed.read_text(encoding="utf-8"))
        table, = (node for node in ast.walk(seed_source)
                  if isinstance(node, ast.FunctionDef) and node.name == "test_c5_sentence_table")
        seed_strings = {node.value for node in ast.walk(table)
                        if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        self.assertFalse(texts & seed_strings, "phrases reused from HCI-03")

        positive_count = sum(expected is not None for _, _, expected in PHRASES)
        self.assertEqual(positive_count, 30)
        self.assertEqual({tag for tag, _, expected in PHRASES if expected is not None},
                         {"word order", "shorthand", "units", "number words", "shelf words", "typos"})
        self.assertEqual({tag for tag, _, expected in PHRASES if expected is None},
                         {"vague", "money", "two products", "questions", "prices", "hikes", "website edits"})
        for _, text, expected in PHRASES:
            if expected is not None:
                with self.subTest(text=text):
                    self.assertIsInstance(expected, CountIntent)
                    self.assertIn(expected.mode, {"count", "add"})
                    self.assertIsInstance(expected.quantity, Decimal)
                    self.assertIn(expected.unit, {None, "lb"})
                    self.assertTrue(expected.query.strip())

    def test_c2_gaps_pinned(self):
        # C2: A misread amount, arrival mode or query must fail unless it is
        # a named gap; a repaired gap must be promoted to an exact assertion.
        positives = {text: expected for _, text, expected in PHRASES if expected is not None}
        gaps = dict(KNOWN_GAPS)
        self.assertEqual(len(gaps), len(KNOWN_GAPS), "duplicate gap")
        self.assertLessEqual(gaps.keys(), positives.keys(), "only count or arrival rows can be gaps")
        self.assertLessEqual(set(gaps.values()), {"code", "ask"})
        for text, expected in positives.items():
            with self.subTest(text=text):
                actual = parse(text)
                if text in gaps:
                    self.assertNotEqual(actual, expected, "fixed: remove this row from KNOWN_GAPS")
                else:
                    self.assertEqual(actual, expected)
                    self.assertIsInstance(getattr(actual, "quantity", None), Decimal)

    def test_c3_no_false_accepts(self):
        # C3: A loose numeric grammar could interpret a price, two products,
        # or a website edit as a stock change; only measured exceptions fail softly.
        exceptions = {text for _, _, text, _ in FALSE_ACCEPTS}
        self.assertTrue(exceptions.isdisjoint(dict(KNOWN_GAPS)))
        for _, text, expected in PHRASES:
            if expected is None and text not in exceptions:
                with self.subTest(text=text):
                    self.assertIsNone(parse(text))

    def test_c4_report_matches(self):
        # C4: A stale report could still show the old pass rate, omit a gap,
        # or call an ambiguous sentence an automatic code fix.
        report = (ROOT / "docs/hass/CLOVER-COUNT-PHRASES.md").read_text(encoding="utf-8")
        totals = Counter(tag for tag, _, _ in PHRASES)
        matched = [(tag, expected) for tag, text, expected in PHRASES if parse(text) == expected]
        correct = Counter(tag for tag, _ in matched)
        counts = re.findall(r"^\| ([a-z ]+) \| (\d+) \| (\d+) \|$", report, re.M)
        self.assertCountEqual(counts, [(tag, str(n), str(correct[tag])) for tag, n in totals.items()])
        hits, size = sum(correct.values()), len(PHRASES)
        self.assertEqual(re.findall(r"^Exact matches: \*\*(.+)\*\*\.$", report, re.M),
                         [f"{hits}/{size} ({hits / size:.1%})"])
        intended = sum(expected is not None for _, _, expected in PHRASES)
        refused = sum(expected is None for _, expected in matched)
        self.assertIn(f"got {hits - refused}/{intended} counts or arrivals right and refused "
                      f"{refused}/{size - intended} non-counts", report)
        self.assertCountEqual(re.findall(r"^\| `([^`]+)` \| (code|ask) \|$", report, re.M), KNOWN_GAPS)
        self.assertCountEqual(re.findall(r"^\| `([^`]+)` \| False accept: (.+) \|$", report, re.M),
                              [(text, reason) for _, _, text, reason in FALSE_ACCEPTS])


def _expected_refusal_failure(text, reason):
    @expectedFailure
    def test(self):
        # C3: Pin this false accept individually. If it starts returning None,
        # unexpected success prompts moving it back to the ordinary refusal table.
        self.assertIsNone(parse(text), reason)

    test.__doc__ = reason
    return test


for suffix, _, text, reason in FALSE_ACCEPTS:
    setattr(CountPhraseTests, f"test_c3_no_false_accepts_{suffix}", _expected_refusal_failure(text, reason))
