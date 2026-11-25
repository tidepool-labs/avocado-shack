"""Small label print the whole-edit read misses is read again at its own spot (``photo_polish.spot_words``).

A photo word too small to judge by likeness (under WORD_PX) or only a little like its spot must be read on the edit at
that occurrence's place, or the edit counts as having removed it. The whole 800 px edit is read at twice its size,
where 7-8 px print is often missed even though the edit kept it. ``text_removed`` now reads such a spot again on its
own, enlarged; only the same word, at that place, on print no other occurrence already used, vouches for it. Blank
spots, absent or moved words, a failed read, too many unvouched words and an off-product spot still count as gone.
Label reading is stubbed (CI has no tesseract). Needs Pillow for the picture tests; no network or provider.
"""
import io
import unittest
from unittest import mock

from hass import photo_polish

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

H = (100, 200, 30, 8)  # where a small photo word occurrence maps to on the edit
NEAR = (101, 200, 29, 8)  # the same word read there
FAR = (100, 300, 30, 8)  # the same word read somewhere else on the label


class Reread:
    """reread(where): answers ``reads`` (a list, or None for a failed read) and counts calls."""

    def __init__(self, reads):
        self.reads, self.calls = reads, []

    def __call__(self, where):
        self.calls.append(where)
        return self.reads


class TextRemovedTests(unittest.TestCase):
    def test_small_print_read_again_at_its_spot_is_kept(self):
        again = Reread([("TASTE", NEAR)])
        self.assertFalse(photo_polish.text_removed([("TASTE", None, H)], [], reread=again))
        self.assertEqual(again.calls, [H])
        # a faint likeness the whole read missed is vouched for the same way
        self.assertFalse(photo_polish.text_removed([("TASTE", 0.40, H)], [], reread=Reread([("TASTE", NEAR)])))
        # the usual OCR slip still counts as the same word
        self.assertFalse(photo_polish.text_removed([("TASTE", None, H)], [], reread=Reread([("TAST", NEAR)])))

    def test_without_a_reread_the_old_rule_holds(self):
        self.assertTrue(photo_polish.text_removed([("TASTE", None, H)], []))
        self.assertTrue(photo_polish.text_removed([("TASTE", None, H)], [], reread=None))

    def test_absent_moved_changed_or_unreadable_spot_is_gone(self):
        for name, reads in (("nothing read", []), ("read failed", None), ("read elsewhere", [("TASTE", FAR)]),
                            ("another word", [("TOAST", NEAR)]), ("a fragment", [("TAS", NEAR)])):
            with self.subTest(name):
                self.assertTrue(photo_polish.text_removed([("TASTE", None, H)], [], reread=Reread(reads)))

    def test_a_reread_must_be_the_whole_word(self):
        same = photo_polish._same_word
        for read, word in (("TASTE", "TASTE"), ("TAST", "TASTE"), ("TASTF", "TASTE"), ("HONE", "HONEY"),
                           ("RICH", "RICH")):
            self.assertTrue(same(read, word), (read, word))
        for read, word in (("TOAST", "TASTE"), ("TAS", "TASTE"), ("RICK", "RICH"), ("RIC", "RICH"),
                           ("TASTES", "TAST"), ("SYRU", "SYRUPS")):
            self.assertFalse(same(read, word), (read, word))

    def test_a_blank_spot_is_gone_without_reading_again(self):
        again = Reread([("TASTE", NEAR)])
        self.assertTrue(photo_polish.text_removed([("TASTE", None, H), ("HONEY", -1.0, FAR)], [], reread=again))
        self.assertTrue(photo_polish.text_removed([("HONEY", -1.0, FAR), ("TASTE", None, H)], [], reread=again))
        self.assertEqual(again.calls, [])

    def test_an_off_product_spot_is_gone(self):
        self.assertTrue(photo_polish.text_removed([("TASTE", None, None)], [], reread=Reread([("TASTE", NEAR)])))

    def test_vouched_words_are_not_read_again(self):
        again = Reread([])
        kept = [("HONEY", 0.9, FAR), ("TASTE", None, H), ("RAW", None, H)]
        self.assertFalse(photo_polish.text_removed(kept, [("TASTE", NEAR)], reread=again))
        self.assertEqual(again.calls, [])

    def test_one_printed_word_never_vouches_for_two_occurrences(self):
        """A word printed twice side by side, one erased: the whole read finds the one left, which vouches for one
        occurrence; reading the other spot again finds that same print, which must not vouch a second time,
        whichever occurrence comes first."""
        left, right = (100, 200, 30, 8), (112, 200, 30, 8)  # both spots are near the surviving print
        survivor = ("TASTE", (112, 200, 30, 8))
        for order in ((left, right), (right, left)):
            with self.subTest(order=order):
                kept = [("TASTE", None, order[0]), ("TASTE", None, order[1])]
                self.assertTrue(photo_polish.text_removed(kept, [survivor], reread=Reread([survivor])))
        # nothing read whole, both spots read again: the one surviving print still vouches only once
        kept = [("TASTE", None, left), ("TASTE", None, right)]
        self.assertTrue(photo_polish.text_removed(kept, [], reread=Reread([survivor])))
        # two prints, each read at its own spot: both kept
        both = Reread([("TASTE", (100, 200, 30, 8)), ("TASTE", (140, 200, 30, 8))])
        far_apart = [("TASTE", None, (100, 200, 30, 8)), ("TASTE", None, (140, 200, 30, 8))]
        self.assertFalse(photo_polish.text_removed(far_apart, [], reread=both))

    def test_too_many_unvouched_words_are_gone_without_reading(self):
        again = Reread([("TASTE", NEAR)])
        kept = [("TASTE", None, H)] * (photo_polish.SPOT_READS + 1)
        self.assertTrue(photo_polish.text_removed(kept, [], reread=again))
        self.assertEqual(again.calls, [])


def jpeg(size=(800, 800)):
    out = io.BytesIO()
    Image.new("RGB", size, (250, 246, 238)).save(out, "JPEG")
    return out.getvalue()


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class SpotWordsTests(unittest.TestCase):
    def test_the_spot_is_read_enlarged_and_mapped_back(self):
        seen = []

        def reader(data, scale=2):
            seen.append((Image.open(io.BytesIO(data)).size, scale))
            return [("TASTE", (8, 8, 27, 8))]  # crop px, as ``words`` reports them
        with mock.patch.object(photo_polish, "words", reader):
            found = photo_polish.spot_words(jpeg(), (398, 579, 27, 8))
        self.assertEqual(seen, [((43, 24), 4)])  # padded by one height each way; 8 px word read 4x, about 32 px high
        self.assertEqual(found, [("TASTE", (398, 579, 27, 8))])

    def test_scale_stays_between_two_and_eight(self):
        scales = []

        def reader(data, scale=2):
            scales.append(scale)
            return []
        with mock.patch.object(photo_polish, "words", reader):
            photo_polish.spot_words(jpeg(), (100, 100, 200, 60))
            photo_polish.spot_words(jpeg(), (100, 100, 10, 2))
        self.assertEqual(scales, [2, 8])

    def test_no_read_or_no_spot_is_none(self):
        with mock.patch.object(photo_polish, "words", lambda data, scale=2: None):
            self.assertIsNone(photo_polish.spot_words(jpeg(), (398, 579, 27, 8)))
        with mock.patch.object(photo_polish, "words", lambda data, scale=2: self.fail("read off the picture")):
            self.assertIsNone(photo_polish.spot_words(jpeg(), (900, 900, 27, 8)))
            self.assertIsNone(photo_polish.spot_words(jpeg(), (100, 100, 0, 8)))
            self.assertIsNone(photo_polish.spot_words(jpeg(), (100, 100, 27, 0)))


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class GateTests(unittest.TestCase):
    """``gate`` reads a missed small word again on the framed edit itself."""

    def run_gate(self, spot):
        from hass.tests.test_photo_polish import edit_of, labelled, photo
        data = labelled(photo("jar-white-sheet"))
        asked = []

        def spot_words(framed, where):
            asked.append((Image.open(io.BytesIO(framed)).size, where))
            return spot(where)
        small = lambda original, framed, mapping, read: [("TASTE", None, H)]  # noqa: E731
        with mock.patch.object(photo_polish, "photo_words", lambda original: [("TASTE", (1, 1, 20, 7))]), \
                mock.patch.object(photo_polish, "words", lambda framed, scale=2: []), \
                mock.patch.object(photo_polish, "kept_scores", small), \
                mock.patch.object(photo_polish, "spot_words", spot_words):
            verdict = photo_polish.gate(data, edit_of(data))
        self.assertEqual(asked, [((800, 800), H)])
        return verdict

    def test_kept_small_print_passes(self):
        verdict = self.run_gate(lambda where: [("TASTE", NEAR)])
        self.assertEqual(verdict["code"], "ok", verdict["metrics"])
        self.assertFalse(verdict["metrics"]["text_removed"])

    def test_erased_small_print_is_refused(self):
        for reads in ([], None):
            with self.subTest(reads=reads):
                verdict = self.run_gate(lambda where, reads=reads: reads)
                self.assertEqual(verdict["code"], "text")
                self.assertTrue(verdict["metrics"]["text_removed"])


if __name__ == "__main__":
    unittest.main()
