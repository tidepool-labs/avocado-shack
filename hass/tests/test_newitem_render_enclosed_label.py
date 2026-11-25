"""NPP case 27a: a pale label inside a cleanly cut-out product is product, not photo background left inside it.

The renderer fills every enclosed pocket of its cut-out into the product. A pocket counts as a label only with positive
evidence: print on it and no patch on the background plane. A plain pale pocket (the counter seen through a handle, lit
brighter or not), a counter-coloured one or one with a counter-coloured patch still hits the area limit. A printed cream
label (a few levels from the house ivory) no longer turns a clean photo into a retake. Pictures we did not cut out
ourselves (catalog files, a supplied alpha, a busy-background fallback) keep the full check.
"""
from __future__ import annotations

import io
import unittest
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None

from hass import house_style as hs, newitem_render as nr
from hass.ops import photos

PHOTOS = Path(__file__).resolve().parent / "npp" / "cases" / "photos"
COUNTER, CREAM, TAN = "#e9e4da", "#fbf6ee", "#d8c8a8"
INSIDE = "no photo background left inside the product (patterned cloth, planks)"


def _jpg(img):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _jar(label, words=True):
    """The case-27 drawing: plum jar on a plain counter, label colour ``label`` (None = no label)."""
    img = Image.new("RGB", (640, 640), COUNTER)
    pen = ImageDraw.Draw(img)
    pen.rectangle((180, 200, 460, 560), fill="#a3213b", outline="#4a0d1a", width=4)
    pen.rectangle((170, 160, 470, 210), fill="#caa24a")
    if label:
        pen.rectangle((205, 280, 435, 480), fill=label)
        if words:  # anti-aliased letters pass through the counter colour at their edges
            font = ImageFont.load_default(size=24)
            for i, line in enumerate(("QUARRY LANE", "Plum", "Preserves", "Net wt 9 oz")):
                pen.text((220, 300 + i * 28), line, fill="#111111", font=font, stroke_width=1, stroke_fill="#111111")
    return _jpg(img)


def _frame(inner, words=False):
    """A dark open frame (basket handle, picture frame) whose middle shows ``inner``; ``words`` prints on it."""
    img = Image.new("RGB", (640, 640), COUNTER)
    pen = ImageDraw.Draw(img)
    pen.rectangle((150, 150, 490, 540), fill="#3b2a1a")
    pen.rectangle((185, 185, 455, 505), fill=inner)
    if words:
        font = ImageFont.load_default(size=24)
        for i, line in enumerate(("HARBOR GOODS", "Sea Salt", "Net wt 4 oz")):
            pen.text((205, 220 + i * 28), line, fill="#111111", font=font, stroke_width=1, stroke_fill="#111111")
    return _jpg(img)


def _inside(check):
    return next(c for c in check["checks"] if c["name"] == INSIDE)


@unittest.skipUnless(Image is not None, "Pillow is not installed")
class EnclosedLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = hs.load_spec()

    def render(self, data):
        return nr.render(data, self.spec)

    def test_case27_clean_jar_fixture_gets_the_house_render(self):
        data = (PHOTOS / "clean-jar-plain.jpg").read_bytes()
        out = self.render(data)
        self.assertEqual(out["report"]["isolation"], "cutout")
        self.assertGreater(out["report"]["enclosed"], 0.05)  # the label pocket was filled into the product
        self.assertEqual(out["report"]["enclosed_background"], 0)
        self.assertTrue(out["check"]["pass"], out["check"]["hard_failures"])
        self.assertTrue(_inside(out["check"])["ok"])
        verdict = photos.house_picture(data)
        self.assertTrue(verdict["ok"], verdict["problems"])
        self.assertEqual(verdict["problems"], [])

    def test_same_render_bytes_without_renderer_evidence_keep_the_full_check(self):
        out = self.render((PHOTOS / "clean-jar-plain.jpg").read_bytes())
        plain = hs.check_image(out["jpeg"], self.spec)  # a catalog file or any picture we did not cut out
        self.assertFalse(plain["pass"])
        self.assertEqual(plain["hard_failures"], [INSIDE])
        self.assertFalse(hs.check_image(out["jpeg"], self.spec, enclosed_background=0.0005)["pass"])
        self.assertTrue(hs.check_image(out["jpeg"], self.spec, enclosed_background=0)["pass"])

    def test_busy_fixture_still_refused_and_count_limit_still_applies(self):
        data = (PHOTOS / "clean-jar-busy.jpg").read_bytes()
        out = self.render(data)
        self.assertEqual(out["report"]["isolation"], "fallback")
        self.assertNotIn("enclosed_background", out["report"])
        self.assertIn(INSIDE, out["check"]["hard_failures"])
        self.assertEqual(photos.house_picture(data)["problems"], ["busy"])
        # dozens of patches fail on their count even if a caller claimed no background was measured
        self.assertIn(INSIDE, hs.check_image(out["jpeg"], self.spec, enclosed_background=0)["hard_failures"])

    def test_counter_seen_through_an_opening_is_still_background(self):
        # exactly the counter, 4 levels off it, and lit 18-20 levels brighter than the border plane (RETURN t_7be375f7):
        # a plain pale pocket carries no evidence that it is a label, whatever its light
        for inner in (COUNTER, "#ede8de", CREAM):
            with self.subTest(inner=inner):
                out = self.render(_frame(inner))
                self.assertEqual(out["report"]["isolation"], "cutout")
                self.assertGreater(out["report"]["enclosed_background"], 0.1)
                self.assertFalse(_inside(out["check"])["ok"])
                self.assertEqual(photos.house_picture(_frame(inner))["problems"], ["style"])

    def test_counter_coloured_opening_with_print_is_still_background(self):
        out = self.render(_frame(COUNTER, words=True))
        self.assertGreater(out["report"]["enclosed_background"], 0.1)
        self.assertFalse(_inside(out["check"])["ok"])

    def test_printed_cream_inside_the_same_opening_is_product(self):
        out = self.render(_frame(CREAM, words=True))
        self.assertEqual(out["report"]["enclosed_background"], 0)
        self.assertTrue(_inside(out["check"])["ok"])

    def test_label_controls(self):
        for label, words, product in ((CREAM, True, True), (TAN, True, True), (None, False, True), (CREAM, False, False)):
            with self.subTest(label=label, words=words):
                out = self.render(_jar(label, words))
                self.assertEqual(out["report"]["enclosed_background"] == 0, product)
                self.assertEqual(out["check"]["pass"], product, out["check"]["hard_failures"])

    def test_supplied_cutout_gets_no_renderer_exemption(self):
        img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        pen = ImageDraw.Draw(img)
        pen.rectangle((100, 80, 300, 340), fill=(163, 33, 59, 255))
        pen.rectangle((130, 150, 270, 270), fill=(251, 246, 238, 255))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        out = self.render(buf.getvalue())
        self.assertEqual(out["report"].get("source"), "alpha channel")
        self.assertNotIn("enclosed_background", out["report"])
        self.assertEqual(out["check"], hs.check_image(out["jpeg"], self.spec))


if __name__ == "__main__":
    unittest.main()
