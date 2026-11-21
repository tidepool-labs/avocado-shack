"""HRM-05: an offline baseline for S10, not a list of desired parser changes.

HRM-14: rows the code now reads without a model keep their HRM-05 answer in ``was``; every other mapper or unclear row
names who it is left for (``left``: the HRM-33 asset change, the model, or by design) and why. GUARDS are extra
phrasings that pin where the HRM-14 everyday wording stops; they are not part of the HRM-05 table or its counts.
"""

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re
import unittest
from unittest.mock import Mock

from hass.npp import assets, edits


MAPPER = "mapper"
UNCLEAR = "unclear"
GENERIC_ASK = edits.Edit(ask="ask_edit_unclear")
ASK_PRICE = edits.Edit(ask="ask_price")
PICTURE = edits.Edit(reply="picture_request")
REWRITE = edits.Edit(patch=(("rewrite", "description"),))
HRM05_COUNTS = {"grammar": 29, "ask": 7, "mapper": 22, "unclear": 7}
LEFT_FOR = ("HRM-33", "model", "by design")
DIGIT_LOCAL = "a digit never reaches the model"
WHY = {  # the report's one reason per row left (C4)
    "unit": "a correction with not is unsure wording, and a unit with no code-parsed price still asks for the price",
    "unsure": f"an unsure amount is asked, never guessed, and {DIGIT_LOCAL}",
    "field": "the name could be the maker, the supplier or part of the product name, and code cannot tell which field",
    "clear": "clearing a field has no typed patch: a value must be his words, so a blank needs a clear action in the assets",
    "length": f"a length has no typed slot, reading it as plain shorter would drop his number, and {DIGIT_LOCAL}",
    "copy": "owner copy is never pasted (F1), so it needs a typed note slot and a reviewed template",
    "shelf": "snacks is not one of the ten shelves; a shelf synonym table is an asset change, and guessing a shelf is not safe",
    "photo": f"a photo number has no typed slot, and {DIGIT_LOCAL}",
    "nothing": "there are no words to read; the model may still answer with one question",
    "question": "a question to Hass is not an edit; chat routing gives it its normal answer",
}


@dataclass(frozen=True)
class Phrase:
    text: str
    expected: edits.Edit | str
    price: str | None = None
    sold_by: str | None = None
    remainder: str | None = None
    explicit_value: tuple[str, str] | None = None
    was: str | None = None  # HRM-14 fixed this row; its HRM-05 expectation (MAPPER or UNCLEAR)
    left: tuple[str, str] | None = None  # a mapper/unclear row HRM-14 left: (who it is left for, the reason)

    def read(self, grammar, mapper=None):
        text = self.text if self.remainder is None else self.remainder
        finance = {"price": self.price, "sold_by": self.sold_by}
        return edits.read(grammar, text, finance, mapper=mapper)

    @property
    def bucket(self):
        if isinstance(self.expected, str):
            return self.expected
        return "ask" if self.expected.ask else "grammar"


def patch(**fields):
    return edits.Edit(patch=tuple(fields.items()))


# Synthetic owner texts. Text goes straight to edits.read unless a remainder is
# specified. Prices in finance are explicit local fixtures, not parsed here.
PHRASES = (
    # Price and unit, including exact input vs. the upstream finance split.
    Phrase("make it 4 bucks", ASK_PRICE, was=UNCLEAR),
    Phrase("$4.50 a pound", ASK_PRICE, was=UNCLEAR),
    Phrase("each not per lb", MAPPER, left=("model", WHY["unit"])),
    Phrase("make it four bucks", ASK_PRICE, was=MAPPER),
    Phrase("four dollars and fifty cents a pound", ASK_PRICE, was=MAPPER),
    Phrase("sell it for five dollars each", ASK_PRICE, was=MAPPER),
    Phrase("make it $4", ASK_PRICE),
    Phrase("price is 4.50 each", ASK_PRICE),
    Phrase("change the price to 4.50 a pound", patch(sellingPrice="4.50", priceUnit="lb"), price="4.50"),
    Phrase("now $4 each", patch(sellingPrice="4.00", priceUnit="each"), price="4.00"),
    Phrase("actually 4 or 5 bucks", UNCLEAR, left=("by design", WHY["unsure"])),
    Phrase("per pound please", ASK_PRICE, was=MAPPER),
    Phrase("actually make it four bucks", patch(sellingPrice="4.00"), price="4.00", remainder="make it"),
    Phrase("okay make it 4 bucks", patch(sellingPrice="4.00"), price="4.00", remainder="okay make it"),
    Phrase("$4.50 per lb", patch(sellingPrice="4.50", priceUnit="lb"), price="4.50", sold_by="pound", remainder=""),
    Phrase("sell it for five bucks each", patch(sellingPrice="5.00", priceUnit="each"),
           price="5.00", sold_by="item", remainder="sell it for"),
    # Name.
    Phrase("call it Wildflower Honey", patch(name="Wildflower Honey")),
    Phrase("name: Lemon Tea", patch(name="Lemon Tea")),
    Phrase("name it Three Hills Wildflower Honey", patch(name="Three Hills Wildflower Honey"),
           explicit_value=("name", "Three Hills Wildflower Honey")),
    Phrase("call it Wildflower Honey please", patch(name="Wildflower Honey please")),
    Phrase('call it "Wildflower Honey"', patch(name="Wildflower Honey"), was=MAPPER),
    Phrase("rename it to Orchard Honey", patch(name="Orchard Honey"), was=MAPPER),
    Phrase("call it Wildflower Honey!", patch(name="Wildflower Honey"), was=MAPPER),
    Phrase("name it Orchard Blend No 7", patch(name="Orchard Blend No 7"),
           explicit_value=("name", "Orchard Blend No 7")),
    # Maker and source.
    Phrase("made by Miners", patch(maker="Miners")),
    Phrase("made by Lantern Kitchen, Pebble Bay", patch(maker="Lantern Kitchen", makerTown="Pebble Bay")),
    Phrase("made by little lantern jam kitchen", patch(maker="Little Lantern Jam Kitchen"),
           explicit_value=("maker", "little lantern jam kitchen")),
    Phrase("it's Miners' honey", MAPPER, left=("model", WHY["field"])),
    Phrase("no maker", MAPPER, left=("HRM-33", WHY["clear"])),
    Phrase("leave the maker blank", MAPPER, left=("HRM-33", WHY["clear"])),
    Phrase("made by Miners or Lantern Kitchen", GENERIC_ASK),
    Phrase("from Etto", patch(supplier="Etto")),
    Phrase("from little lantern trading co", patch(supplier="Little Lantern Trading Co"),
           explicit_value=("supplier", "little lantern trading co")),
    Phrase("from Etto maybe", edits.Edit(ask="ask_edit_source", ask_args=(("name", "Etto maybe"),))),
    Phrase('Looks good otherwise. This is from "Etto".', patch(supplier="Etto")),
    Phrase("we get it from Lantern Kitchen", patch(supplier="Lantern Kitchen")),
    Phrase("swap the supplier to Lantern Kitchen", patch(supplier="Lantern Kitchen"), was=MAPPER),
    Phrase("take the source off", MAPPER, left=("HRM-33", WHY["clear"])),
    # Wording and owner copy.
    Phrase("shorter", REWRITE),
    Phrase("less fancy", REWRITE),
    Phrase("make it simpler", REWRITE),
    Phrase("bit warmer", REWRITE),
    Phrase("a little less fancy", REWRITE),
    Phrase("shorter please", REWRITE, was=MAPPER),
    Phrase("make the description a little shorter", REWRITE, was=MAPPER),
    Phrase("make it 2 lines shorter", UNCLEAR, left=("HRM-33", WHY["length"])),
    Phrase("add: great on toast", GENERIC_ASK),
    Phrase("add: really good on warm toast", GENERIC_ASK),
    Phrase("add: nice with tea on a cold day", GENERIC_ASK),
    Phrase("say it's nice with tea on a cold day", MAPPER, left=("HRM-33", WHY["copy"])),
    # Category.
    Phrase("put it in pantry", patch(category="pantry")),
    Phrase("category: Bread", patch(category="bread")),
    Phrase("shelf: drinks", patch(category="drinks")),
    Phrase("move that to dairy", patch(category="dairy"), was=MAPPER),
    Phrase("put it under fruit please", patch(category="fruit"), was=MAPPER),
    Phrase("category: snacks", MAPPER, left=("HRM-33", WHY["shelf"])),
    # Picture.
    Phrase("use my photo", PICTURE),
    Phrase("try the picture again", PICTURE),
    Phrase("different picture", PICTURE),
    Phrase("use my photo please", PICTURE, was=MAPPER),
    Phrase("use the photo I just sent", PICTURE, was=MAPPER),
    Phrase("use photo 2", UNCLEAR, left=("HRM-33", WHY["photo"])),
    # Nonsense/questions: a question stays local even without a question mark.
    Phrase("asdf hjkl", MAPPER, left=("model", WHY["nothing"])),
    Phrase("what did you put for the maker", UNCLEAR, left=("by design", WHY["question"])),
    Phrase("Hass, is this on the site yet?", UNCLEAR, left=("by design", WHY["question"])),
)

# HRM-14 guards: where the everyday wording stops. Unsure names still ask, digits stay local, a pinned negative or a
# non-shelf is never read, no lead-in is invented, a question mark is never an edit, and a named price still needs
# finance.
GUARDS = (
    Phrase("rename it to Orchard Honey please", patch(name="Orchard Honey")),
    Phrase("rename it to maybe Orchard Honey", MAPPER),
    Phrase("change the name to Lemon Tea", patch(name="Lemon Tea")),
    Phrase("change the maker to Rosa", patch(maker="Rosa")),
    Phrase("set the source to Etto maybe", edits.Edit(ask="ask_edit_source", ask_args=(("name", "Etto maybe"),))),
    Phrase("change the supplier to 3 Hills", UNCLEAR),
    Phrase("move it to the fridge", MAPPER),
    Phrase("make the description a bit warmer", REWRITE),
    Phrase("make the description 4", UNCLEAR),  # Wording aliases must not fall through to the price form.
    Phrase("make it a little 4", UNCLEAR),
    Phrase("use the photo I sent you", PICTURE),
    Phrase("call it “Orchard Honey”", patch(name="Orchard Honey")),
    Phrase("make it four bucks please", ASK_PRICE),
    Phrase("sell it for four dollars a pound", patch(sellingPrice="5.00", priceUnit="lb"), price="5.00"),
    Phrase("sold by the pound", patch(sellingPrice="4.50", priceUnit="lb"), price="4.50"),
    Phrase("maybe four bucks", MAPPER),
    Phrase("call me later please", MAPPER),
    Phrase("put it in the fridge please", MAPPER),
    Phrase("the name is wrong", MAPPER),
    Phrase("make it shorter please?", UNCLEAR),
)


def words(text):
    return re.findall(r"[^\W_]+", text.casefold())


def four_word_spans(tokens):
    return set(zip(tokens, tokens[1:], tokens[2:], tokens[3:]))


def label(edit):
    """How the report names a local answer: the patched fields, the ask id or the reply key."""
    if edit.patch:
        return "patch " + "+".join(field for field, _ in edit.patch)
    return edit.ask or edit.reply


class EditPhraseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, files, _ = assets()
        cls.files = files
        cls.grammar = edits.Grammar(files)

    def check_row(self, row):
        expected = GENERIC_ASK if isinstance(row.expected, str) else row.expected
        self.assertEqual(row.read(self.grammar), expected)
        # Use a no-op callback to observe route eligibility, not to predict Sol's output.
        if not re.search(r"\d", row.text):  # C3 checks callback suppression for digit rows.
            spy = Mock(return_value=None)
            row.read(self.grammar, mapper=spy)
            if row.expected == MAPPER:
                spy.assert_called_once()
            else:
                spy.assert_not_called()
        if expected == GENERIC_ASK:
            # A form that asks (e.g. add:) is not an unmatched local miss.
            self.assertEqual(self.grammar.match(row.text) is not None, row.bucket == "ask")

    def test_c1_table(self):
        # C1: catch a form capturing the wrong value, or silent drift between
        # local handling and fallback. With no mapper both misses ask the same thing.
        self.assertGreaterEqual(len(PHRASES), 40)
        self.assertEqual(len({row.text for row in PHRASES + GUARDS}), len(PHRASES) + len(GUARDS))
        for row in PHRASES:
            with self.subTest(text=row.text):
                self.check_row(row)
                # HRM-14: a fixed row was a mapper/unclear row and is now answered locally; every row still on the
                # fallback says who it is left for and why. Undoing ``was`` gives back the HRM-05 buckets exactly.
                if row.was is not None:
                    self.assertIn(row.was, (MAPPER, UNCLEAR))
                    self.assertNotIn(row.bucket, (MAPPER, UNCLEAR))
                self.assertEqual(row.left is not None, row.bucket in (MAPPER, UNCLEAR))
                if row.left is not None:
                    self.assertIn(row.left[0], LEFT_FOR)
                    self.assertTrue(row.left[1].strip())
        self.assertEqual(Counter(row.was or row.bucket for row in PHRASES), HRM05_COUNTS)

    def test_c1_guards(self):
        # C1 / HRM-14: catch an everyday-wording rule that reads too much (an unsure name patched, a digit sent to the
        # mapper, a pinned negative or non-shelf read, a lead-in invented) or a named price set without finance.
        for row in GUARDS:
            with self.subTest(text=row.text):
                self.check_row(row)

    def test_c1_left_rows_still_reach_the_model(self):
        # C1 / HRM-14: a row left to the model still reaches it and its pointed answer is still used, so the model
        # path keeps its coverage now that "swap the maker to Rosa" (test_npp_edits) is read locally.
        def pointing_at(value):
            return Mock(return_value={"action": "patch", "patches": [{"field": "maker", "value": value}], "ask_id": None})

        pointed = pointing_at("Miners")
        row = next(row for row in PHRASES if row.text == "it's Miners' honey")
        self.assertEqual(row.read(self.grammar, mapper=pointed), patch(maker="Miners"))
        pointed.assert_called_once()
        pointed = pointing_at("Rosa")
        self.assertEqual(edits.read(self.grammar, "swap the maker to Rosa", {}, pointed), patch(maker="Rosa"))
        pointed.assert_not_called()

    def test_c1_everyday_wording_rechecks_negatives(self):
        # C1 / HRM-14: a pinned negative must stay unread in its everyday wording too, or the asset is refused.
        # Bug: "make it shorter please" listed as a wording negative but read once "please" is dropped.
        doc = json.loads(self.files[edits.GRAMMAR])
        wording = next(form for form in doc["forms"] if form["id"] == "wording")
        wording["negatives"].append("make it shorter please")
        with self.assertRaisesRegex(ValueError, "edit form wording reads a negative"):
            edits.Grammar({**self.files, edits.GRAMMAR: json.dumps(doc).encode()})

    def test_c2_no_paste(self):
        # C2 / F1: catch an edit accidentally copying owner chatter into any
        # string patch field. Only an explicitly declared field/value is exempt.
        for row in PHRASES + GUARDS:
            owner_spans = four_word_spans(words(row.text))
            for field, value in row.read(self.grammar).patch:
                if not isinstance(value, str):
                    continue
                with self.subTest(text=row.text, field=field):
                    if row.explicit_value:
                        explicit_field, explicit_value = row.explicit_value
                        if field == explicit_field and " ".join(value.casefold().split()) == explicit_value.casefold():
                            continue
                    self.assertFalse(owner_spans & four_word_spans(words(value)), value)

    def test_c3_digits_stay_local(self):
        # C3: catch a new route sending an unmatched amount, photo index or
        # length to the mapper (which would still look like an ask with no mapper).
        digit_rows = [row for row in PHRASES + GUARDS if re.search(r"\d", row.text)]
        self.assertTrue(digit_rows)
        self.assertTrue([row for row in digit_rows if row.was is not None])  # HRM-14 fixed rows are covered too
        for row in digit_rows:
            with self.subTest(text=row.text):
                spy = Mock(return_value=None)
                row.read(self.grammar, mapper=spy)
                spy.assert_not_called()

    def test_c4_report_matches(self):
        # C4: catch stale totals or omitted/mislabelled fallback rows after a
        # fixture change, even when the behavioural expectations are up to date.
        report = (Path(__file__).resolve().parents[2] / "docs/hass/NPP-EDIT-PHRASES.md").read_text(encoding="utf-8")
        counts = re.findall(r"\b(grammar|ask|mapper|unclear|fixed): (\d+)\b", report)
        self.assertEqual(len(counts), 5)
        fixed = sum(row.was is not None for row in PHRASES)
        self.assertEqual({key: int(value) for key, value in counts}, {**Counter(row.bucket for row in PHRASES), "fixed": fixed})
        self.assertIn(f"On {len(PHRASES)} synthetic owner texts", report)
        route = {MAPPER: MAPPER, UNCLEAR: GENERIC_ASK.ask}
        report_left = re.findall(r"^\| `([^`]+)` \| `(mapper|ask_edit_unclear)` \| (HRM-33|model|by design) "
                                 r"\| ([^|`]+?) \|$", report, re.M)
        self.assertCountEqual(report_left, [(row.text, route[row.bucket], *(row.left or ()))
                                            for row in PHRASES if row.bucket in (MAPPER, UNCLEAR)])
        report_fixed = re.findall(r"^\| `([^`]+)` \| `(mapper|ask_edit_unclear)` \| `([^`]+)` \|$", report, re.M)
        self.assertCountEqual(report_fixed, [(row.text, route[row.was], label(row.expected))
                                             for row in PHRASES if row.was is not None])
