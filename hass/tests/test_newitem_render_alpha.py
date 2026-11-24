"""RF0415-11: invisible RGB under a supplied alpha channel cannot tint the rendered product edge. Synthetic in-memory PNGs only."""
import io
import unittest

from hass import newitem_render as nr

try:
    from PIL import Image, ImageDraw
    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

BROWN = (150, 100, 50)


def _png(hidden, size=(400, 500), rect=(100, 80, 300, 430), angle=0, fringe=False):
    """Brown subject over alpha; only RGB at alpha 0 is `hidden`. Optionally a native fractional-alpha ring around it."""
    im = Image.new("RGBA", size, hidden + (0,))
    alpha = Image.new("L", size, 0)
    d = ImageDraw.Draw(alpha)
    if fringe:
        d.rectangle((rect[0] - 3, rect[1] - 3, rect[2] + 3, rect[3] + 3), fill=128)
    d.rectangle(rect, fill=255)
    if angle:
        alpha = alpha.rotate(angle, expand=False)
    solid = Image.new("RGB", size, BROWN)
    mask = alpha.point(lambda v: 255 if v else 0)
    im.paste(Image.merge("RGBA", (*solid.split(), alpha)), (0, 0), mask)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


@unittest.skipUnless(HAVE_PIL, "Pillow required")
class AlphaRender(unittest.TestCase):
    HIDDEN = [(0, 0, 0), (255, 0, 255), (0, 255, 0)]

    def _same(self, **kw):
        outs = [nr.render(_png(h, **kw)) for h in self.HIDDEN]
        for o in outs[1:]:
            self.assertEqual(o["jpeg"], outs[0]["jpeg"])
            self.assertEqual(o["report"], outs[0]["report"])
            self.assertEqual(o["check"], outs[0]["check"])
        return outs[0]

    def test_invisible_rgb_cannot_change_render(self):
        out = self._same()
        self.assertEqual(out["report"]["source"], "alpha channel")
        self.assertEqual(nr.render(_png((0, 0, 0)))["jpeg"], out["jpeg"])

    def test_hidden_rgb_invariant_through_straightening_and_resize(self):
        tilted = self._same(size=(500, 700), rect=(200, 60, 260, 640), angle=8)
        self.assertIn("straightened_degrees", tilted["report"])
        big = self._same(size=(2000, 2400), rect=(400, 300, 1500, 2100))
        self.assertLess(big["report"]["scale"], 1)
        small = self._same(size=(200, 200), rect=(80, 60, 120, 140))
        self.assertGreater(small["report"]["scale"], 1)

    def test_partial_alpha_preserves_visible_colour(self):
        out = self._same(fringe=True)
        im = Image.open(io.BytesIO(out["jpeg"])).convert("RGB")
        x0, y0, x1, y1 = out["report"]["box"]
        mid = im.getpixel(((x0 + x1) // 2, (y0 + y1) // 2))
        for got, want in zip(mid, BROWN):  # solid core is the brown, not a hidden colour (JPEG tolerance)
            self.assertLess(abs(got - want), 30)

    def test_native_alpha_edges_do_not_acquire_hidden_colour(self):
        for h in ((255, 0, 255), (0, 255, 0)):
            out = nr.render(_png(h, fringe=True))
            im = Image.open(io.BytesIO(out["jpeg"])).convert("RGB")
            x0, y0, x1, y1 = out["report"]["box"]
            for x in range(x0, x1, 7):
                for y in (y0, y0 + 1, y1 - 2, y1 - 1):
                    r, g, b = im.getpixel((x, y))
                    # ivory/shadow/brown blends only: hidden magenta or green would push g far from r,b mix
                    self.assertLess(abs(g - (r + b) / 2), 60, (h, x, y, (r, g, b)))

    def test_alpha_empty_and_pure_black_keep_contract(self):
        buf = io.BytesIO()
        Image.new("RGBA", (400, 500), (255, 0, 255, 0)).save(buf, "PNG")
        with self.assertRaises(nr.Refused):
            nr.render(buf.getvalue())
        im = Image.new("RGBA", (400, 500), (255, 0, 255, 0))
        im.paste((0, 0, 0, 255), (100, 80, 300, 430))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        out = nr.render(buf.getvalue())
        self.assertEqual(out["report"]["subject_luma"], 0)
        self.assertLessEqual(out["report"]["exposure_gain"], 1.25)

    def test_opaque_input_metadata_free_and_deterministic(self):
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (400, 500), (240, 238, 230)).save(buf, "PNG")
        a, b = nr.render(buf.getvalue()), nr.render(buf.getvalue())
        self.assertEqual(a["jpeg"], b["jpeg"])
        im = Image.open(io.BytesIO(a["jpeg"]))
        self.assertEqual((im.mode, im.size), ("RGB", (800, 800)))
        self.assertFalse(im.getexif())
        self.assertNotIn("icc_profile", im.info)

        # Only exact opacity may take the RGB path; a near-opaque cutoff
        # would send the 254 case to background isolation instead.
        for coverage in (255, 254, 200):
            with self.subTest(coverage=coverage):
                rgba = Image.new("RGBA", (400, 500), (240, 238, 230, 255 if coverage == 200 else coverage))
                if coverage == 200:
                    rgba.putpixel((200, 250), (240, 238, 230, 200))
                buf = io.BytesIO()
                rgba.save(buf, "PNG")
                out = nr.render(buf.getvalue())
                if coverage == 255:
                    self.assertEqual(out, a)
                else:
                    self.assertEqual(out["report"].get("source"), "alpha channel")


if __name__ == "__main__":
    unittest.main()
