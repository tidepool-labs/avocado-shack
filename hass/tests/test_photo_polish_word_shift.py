"""A word map that is off as a whole by a few px must not make a small label word look erased (case 6's COMPANY).

``kept_scores`` searches each photo word on the edit around its mapped spot, only as far as the word is high. When
the whole map is a few px off, big words are still found inside their own search, but a small word (11 px) falls
outside its search and looks blank (under WORD_MIN: gone). When at least two surely kept words agree on one shift, a
word that did not look surely kept is searched once more around its spot moved by that shift, the same distance.
Erased, replaced and lone-anchor cases, and anchors that disagree, are unchanged. Synthetic pictures only (no
tesseract, no network or provider); needs Pillow.
"""
import io
import random
import unittest

from hass import photo_polish

try:
    from PIL import Image, ImageDraw
    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

SIZE = (640, 480)
PAPER = 232
BIG_A = ("ACACIA", (120, 90, 220, 30))
BIG_B = ("HONEY", (110, 150, 260, 30))
SMALL = ("COMPANY", (140, 215, 110, 11))
OTHER = ("FARMERS", (140, 215, 110, 11))  # a different small word in the same place
SHIFT = -9  # px the whole edit sits above the map (the small word's own search reaches 0.6 * 11 = 6.6 px)


def strokes(draw, box, seed):
    """Fine dark print filling ``box`` (2 px cells, like small letters seen up close); each seed is a different
    'word', and a copy moved by a quarter of its height no longer looks like it."""
    rng = random.Random(seed)
    left, top, width, height = box
    for y in range(top, top + height, 2):
        for x in range(left, left + width, 2):
            if rng.random() < 0.45:
                draw.rectangle((x, y, x + 1, y + 1), fill=rng.randint(20, 90))


def picture(words, moves=None):
    """PNG bytes of a label with ``words`` [(name, box)], each moved by ``moves[name]`` (dx, dy) px."""
    im = Image.new("L", SIZE, PAPER)
    draw = ImageDraw.Draw(im)
    for name, (left, top, width, height) in words:
        dx, dy = (moves or {}).get(name, (0, 0))
        strokes(draw, (left + dx, top + dy, width, height), seed=sum(map(ord, name)))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "PNG")
    return buf.getvalue()


IDENTITY = (SIZE, (0.0, 0.0, 1.0, 1.0), (0, 0) + SIZE)  # the edit is the photo, same size, same place


def kept(photo_words, edit):
    original = picture(photo_words)
    return {w: (s, where) for w, s, where in photo_polish.kept_scores(original, edit, IDENTITY, photo_words)}


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class SharedShiftTests(unittest.TestCase):
    ALL = [BIG_A, BIG_B, SMALL]
    UP = {name: (2, SHIFT) for name, _box in ALL}

    def test_a_small_word_the_whole_map_missed_is_kept(self):
        before = photo_polish._shared_shift  # what the search alone sees, without the shared shift
        try:
            photo_polish._shared_shift = lambda fits, heights: None
            alone = kept(self.ALL, picture(self.ALL, self.UP))
        finally:
            photo_polish._shared_shift = before
        self.assertLess(alone["COMPANY"][0], photo_polish.WORD_MIN)  # the old verdict: clearly blank, gone
        scores = kept(self.ALL, picture(self.ALL, self.UP))
        for word in ("ACACIA", "HONEY", "COMPANY"):
            self.assertGreaterEqual(scores[word][0], photo_polish.WORD_SURE, word)
        self.assertAlmostEqual(scores["COMPANY"][1][1], SMALL[1][1] + SHIFT, delta=3)  # its spot moved with the map
        self.assertFalse(photo_polish.text_removed([(w, s, where) for w, (s, where) in scores.items()], []))

    def test_an_unmoved_edit_scores_as_before(self):
        edit = picture(self.ALL)
        before = photo_polish._shared_shift
        try:
            photo_polish._shared_shift = lambda fits, heights: None
            alone = kept(self.ALL, edit)
        finally:
            photo_polish._shared_shift = before
        scores = kept(self.ALL, edit)
        self.assertEqual(scores, alone)
        for word, (score, _where) in scores.items():
            self.assertGreaterEqual(score, photo_polish.WORD_SURE, word)
        self.assertEqual(scores["COMPANY"][1][:2], SMALL[1][:2])

    def test_an_erased_small_word_is_still_gone(self):
        erased = [BIG_A, BIG_B]
        scores = kept(self.ALL, picture(erased, self.UP))
        self.assertLess(scores["COMPANY"][0], photo_polish.WORD_MIN)
        self.assertTrue(photo_polish.text_removed([(w, s, where) for w, (s, where) in scores.items()], []))

    def test_another_word_in_its_place_is_still_not_it(self):
        replaced = [BIG_A, BIG_B, OTHER]
        scores = kept(self.ALL, picture(replaced, {**self.UP, "FARMERS": (2, SHIFT)}))
        self.assertLess(scores["COMPANY"][0], photo_polish.WORD_SURE)

    def test_one_sure_word_is_not_enough_to_move_the_map(self):
        two = [BIG_A, SMALL]
        scores = kept(two, picture(two, {"ACACIA": (2, SHIFT), "COMPANY": (2, SHIFT)}))
        self.assertGreaterEqual(scores["ACACIA"][0], photo_polish.WORD_SURE)
        self.assertLess(scores["COMPANY"][0], photo_polish.WORD_MIN)

    def test_sure_words_that_disagree_move_nothing(self):
        scores = kept(self.ALL, picture(self.ALL, {"ACACIA": (0, SHIFT), "HONEY": (0, -SHIFT),
                                                   "COMPANY": (0, SHIFT)}))
        self.assertGreaterEqual(scores["ACACIA"][0], photo_polish.WORD_SURE)
        self.assertGreaterEqual(scores["HONEY"][0], photo_polish.WORD_SURE)
        self.assertLess(scores["COMPANY"][0], photo_polish.WORD_MIN)

    def test_the_shift_needs_agreement(self):
        shift = photo_polish._shared_shift
        self.assertIsNone(shift([(0.9, 1.0, -8.0)], [33.0]))  # one word
        self.assertEqual(shift([(0.9, 0.0, -8.0), (0.9, 2.0, -10.0)], [33.0, 34.0]), (1.0, -9.0))
        self.assertIsNone(shift([(0.9, 0.0, -9.0), (0.9, 0.0, 9.0)], [33.0, 34.0]))  # 9 px apart from the middle
        self.assertIsNone(shift([], []))


if __name__ == "__main__":
    unittest.main()
