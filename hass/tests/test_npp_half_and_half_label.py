"""H69: golden case 3 (Straus half-and-half) on the saved recording.

1. The picture number screen refused the polished card because OCR read "™" (NFKC -> "TM") next to a printed digit and
   read the label's ampersand as "»". It now refuses normalization only when it changes a number reading, and accepts
   "Half » Half" / "Half « Half" only in a picture read. Every refusal the screen exists for still holds.
2. The owner's "made by Straus, Straus half-and-half" did not agree with the confident "Half & Half" photo read because
   the hyphenated word was compared whole; a hyphenated word made only of the photo's words now reads as its parts.
"""
import unittest

from hass.npp import private_numbers as pn
from hass.npp.missing import _photo_compounds, agrees_with_photo, keeps_photo_product
from hass.tests.test_npp_owner_after_maker import _Decide

CASE3 = "made by Straus, Straus half-and-half, $7 each"


class NormalizationScreenTests(unittest.TestCase):
    def test_a_trademark_mark_next_to_a_printed_digit_is_screened_like_plain_text(self):
        # Before H69 any NFKC change plus any digit anywhere was 'number-unclear'; "™" -> "TM" changes no number.
        self.assertIsNone(pn.problem("ORGANIC™ Half & Half 7", digits_allowed=True))
        self.assertIsNone(pn.picture_problem("STRAUS ORGANIC™ 7", "STRAUS ORGANIC™", []))
        # The ordinary checks still run on the original text after the mark.
        self.assertEqual(pn.problem("ORGANIC™ 7"), "unsupported-number")
        self.assertEqual(pn.problem("ORGANIC™ 7", {7}, digits_allowed=True), "private-number")
        self.assertEqual(pn.problem("ORGANIC™ maybe 7", digits_allowed=True), "number-unclear")
        self.assertEqual(pn.problem("ORGANIC™ half a crate", digits_allowed=True), "number-unclear")
        self.assertEqual(pn.problem("ORGANIC™ ＄7", digits_allowed=True), "money")

    def test_normalization_that_makes_or_hides_a_number_still_fails_closed(self):
        # Superscript, circled, fullwidth and fraction characters become numerals; a ligature can hide a number word
        # ("ﬁve" -> "five") or a hedge. Each is refused even beside a "™", and even when no digit is present.
        for text in ("Jam ⁷", "Jam ⑦", "Jam ７", "Jam ½", "Jam ﬁve", "Jam ﬁfty", "Jam ﬁve™", "Jam 7™ ⁷",
                     "Jam ﬁfteen jars", "Ｆｏｏ１２"):
            with self.subTest(text=text):
                self.assertEqual(pn.problem(text, digits_allowed=True), "number-unclear")
                self.assertEqual(pn.picture_problem(text, text, []), "number-unclear")

    def test_a_plain_ligature_with_no_number_is_harmless(self):
        self.assertIsNone(pn.problem("Oﬃcial Maple Valley syrup™"))


class OcrAmpersandTests(unittest.TestCase):
    def test_a_picture_read_of_the_label_ampersand_as_a_guillemet_is_the_product_name(self):
        for read in ("ORGANIC Half » Half", "Half«Half", "TORGANIC Half » Half wal",
                     "ORGANIC Half & Half IRGAN TORGANIC Half » Half"):
            with self.subTest(read=read):
                self.assertIsNone(pn.picture_problem(read, "ORGANIC Half & Half", []))

    def test_only_the_picture_screen_and_only_between_two_halves(self):
        # Captions and other public text keep the strict idiom.
        self.assertEqual(pn.problem("Half » Half", digits_allowed=True), "number-unclear")
        for read in ("Half / Half", "Half + Half", "Half » Half » half", "half » price", "Half »» Half",
                     "Half » Half half", "half x half"):
            with self.subTest(read=read):
                self.assertEqual(pn.picture_problem(read, "Half & Half", []), "number-unclear")
        self.assertEqual(pn.picture_problem("Half » Half $7", "Half & Half", []), "money")
        self.assertEqual(pn.picture_problem("Half » Half 12", "Half & Half", [], {12}), "private-number")

    def test_the_case3_card_read_shape_passes_and_the_source_shape_is_unchanged(self):
        # Shape of the saved case 3 reads (label words only, no owner text): a mark, a stray printed digit, both
        # spellings of the ampersand. Digits are allowed in a picture unless private.
        card = 'STRAUS FAMILY CREAMERY ORGANIC Half & Half "Se DIFFERENCE TORGANIC Half » Half S 7 TORGANIC™ TASTE'
        source = "ORGANIC Half & Half STRAUS TASTE THE DIFFERENCE TORGANIC™ TASTE"
        self.assertIsNone(pn.picture_problem(card, source, ["STRAUS", "TASTE", "THE", "DIFFERENCE"]))
        self.assertEqual(pn.picture_problem(card, source, ["STRAUS"], {7}), "private-number")


class HyphenatedNameTests(unittest.TestCase):
    def test_a_hyphenated_spelling_of_the_photo_name_agrees(self):
        for name, photo in (("half-and-half", "Half & Half"), ("Half-n-Half", "half and half"),
                            ("organic half-and-half", "Half & Half"), ("half-and-half", "organic half & half")):
            with self.subTest(name=name, photo=photo):
                self.assertTrue(agrees_with_photo(name, photo))

    def test_other_hyphenated_words_stay_whole(self):
        photo = {"maple", "syrup"}
        self.assertEqual(_photo_compounds(["hand-poured", "maple", "syrup"], photo), ["hand-poured", "maple", "syrup"])
        self.assertEqual(_photo_compounds(["and-n"], photo), ["and-n"])
        self.assertEqual(_photo_compounds(["maple-syrup"], photo), ["maple", "syrup"])
        # A compound that names another product still disagrees, and a different head still fails.
        self.assertFalse(agrees_with_photo("peanut-butter", "almond butter"))
        self.assertFalse(agrees_with_photo("half-and-half creamer", "Half & Half"))
        self.assertFalse(agrees_with_photo("whole-milk", "Half & Half"))

    def test_the_after_maker_clause_still_must_keep_every_photo_word(self):
        self.assertTrue(keeps_photo_product("half-and-half", "Half & Half"))
        self.assertFalse(keeps_photo_product("peanut-butter", "almond butter"))


class DecideCase3Tests(_Decide):
    def test_case3_caption_names_the_confident_half_and_half_read_without_a_note(self):
        reading = dict(self.reading, item="Half & Half", kind="food", category_guess="dairy", brand_on_label="Straus")
        decision = self.decide(CASE3, reading)
        self.assertEqual(decision.item.casefold(), "half-and-half")
        self.assertFalse(decision.name_from_photo)
        self.assertTrue(decision.ready)

    def test_a_disagreeing_hyphenated_name_still_keeps_the_photo_and_says_so(self):
        reading = dict(self.reading, item="Half & Half", kind="food", category_guess="dairy", brand_on_label="Straus")
        decision = self.decide("made by Straus, Straus whole-milk yogurt, $7 each", reading)
        self.assertEqual(decision.item, "Half & Half")
        self.assertTrue(decision.name_from_photo)


if __name__ == "__main__":
    unittest.main()
