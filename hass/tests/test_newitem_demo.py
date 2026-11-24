"""newitem_demo montage: BEFORE/AFTER stay in columns 3/4 whatever the sampled catalog supplies."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Guarded like test_newitem_synthetic.py: Pillow is pinned in CI; the CI planner counts tests before it is installed,
# so an unguarded top-level import would be counted as one failed import there but run as seven tests later.
try:
    from PIL import Image, ImageChops
    from hass import newitem_demo as demo
    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

if HAVE_PIL:
    T, ROW = demo.TILE, demo.TILE + 22
CASE = ("jar-dark-wood", dict(product="jar", background="dark-wood", size=(300, 240), seed=7))
CASE2 = ("bag-red-cloth", dict(product="bag", background="red-cloth", size=(300, 240), seed=8))
COLORS = [(200, 30, 30), (30, 200, 30), (30, 30, 200)]


class Content:
    def __init__(self, products): self.products = products
    def active_products(self): return self.products


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class MontageTest(unittest.TestCase):
    def run_demo(self, products, cases=(CASE,), show=("jar-dark-wood", "bag-red-cloth"), *, missing=None, damaged=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "site").mkdir()
        recs = []
        for i, (cat, color) in enumerate(products):
            photo = root / "site" / f"p{i}.png"
            if i != missing:
                image = Image.new("RGB", (100, 100), color)
                if i == damaged:
                    buf = io.BytesIO()
                    image.save(buf, "JPEG")
                    photo.write_bytes(buf.getvalue()[:-2])  # valid header, truncated pixel data
                else:
                    image.save(photo)
            recs.append({"category": cat, "name": f"Prod {i}", "image": photo.name})
        with mock.patch.object(demo, "load_content", lambda: Content(recs)), mock.patch.object(demo.hs, "SITE", root / "site"), \
                mock.patch.object(demo, "OUT", root / "out"), mock.patch.object(demo.syn, "cases", lambda: list(cases)), \
                mock.patch.object(demo, "SHOW", show), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(demo.main(), 0)
        with Image.open(root / "out" / "before-after.png") as sheet:
            return sheet.convert("RGB")

    def cell(self, sheet, row, col): return sheet.crop((col * T, row * ROW, (col + 1) * T, (row + 1) * ROW))

    def assert_placeholder(self, sheet, row, col):
        cell = self.cell(sheet, row, col)
        blank = Image.new("RGB", (T, T), demo.PAGE)
        self.assertIsNone(ImageChops.difference(cell.crop((0, 0, T, T)), blank).getbbox())
        expected = demo.tile(blank, "catalog: unavailable")
        self.assertIsNone(ImageChops.difference(cell, expected).getbbox())

    def assert_ref(self, sheet, row, col, color):
        self.assertEqual(self.cell(sheet, row, col).getpixel((T // 2, T // 2)), color)

    def assert_cmp(self, sheet, row):
        before, after = self.cell(sheet, row, 2), self.cell(sheet, row, 3)
        self.assertNotEqual(before.getbbox(), None)
        self.assertEqual(before.getpixel((3, T + 10)), demo.PAGE)  # label band background
        self.assertNotEqual(ImageChops.difference(before, after).getbbox(), None)
        self.assertGreater(len(set(before.crop((0, T, T, ROW)).getdata())), 1)  # BEFORE label text drawn

    def test_zero_pantry_references_reserve_two_unavailable_tiles(self):
        for products in ([], [("snacks", COLORS[0])]):
            sheet = self.run_demo(products)
            self.assertEqual(sheet.size, (4 * T, ROW))
            self.assert_placeholder(sheet, 0, 0)
            self.assert_placeholder(sheet, 0, 1)
            self.assert_cmp(sheet, 0)

    def test_one_sample_keeps_second_reference_slot_empty(self):
        for n in (1, 12):
            sheet = self.run_demo([("pantry", COLORS[0])] * n)
            self.assert_ref(sheet, 0, 0, COLORS[0])
            self.assert_placeholder(sheet, 0, 1)
            self.assert_cmp(sheet, 0)
            self.assertEqual(sheet.size, (4 * T, ROW))

    def test_stride_boundary_thirteen_has_two_reference_tiles(self):
        products = [("pantry", COLORS[0])] + [("pantry", (9, 9, 9))] * 11 + [("pantry", COLORS[1])]
        sheet = self.run_demo(products)
        self.assert_ref(sheet, 0, 0, COLORS[0])
        self.assert_ref(sheet, 0, 1, COLORS[1])
        self.assertNotEqual(self.cell(sheet, 0, 1).crop((0, T, T, ROW)).tobytes(), demo.tile(Image.new("RGB", (T, T), demo.PAGE), "catalog: unavailable").crop((0, T, T, ROW)).tobytes())

    def test_extra_sample_does_not_add_a_fifth_column(self):
        products = [("pantry", COLORS[i % 3 if i % 12 == 0 else 0]) for i in range(25)]
        products[0], products[12], products[24] = ("pantry", COLORS[0]), ("pantry", COLORS[1]), ("pantry", COLORS[2])
        sheet = self.run_demo(products)
        self.assertEqual(sheet.size, (4 * T, ROW))
        self.assert_ref(sheet, 0, 0, COLORS[0])
        self.assert_ref(sheet, 0, 1, COLORS[1])
        self.assert_cmp(sheet, 0)

    def test_multiple_show_rows_keep_comparison_columns(self):
        extra = ("jar-unshown", dict(product="jar", background="white-sheet", size=(300, 240), seed=1))
        products = [("pantry", COLORS[0])] + [("pantry", (9, 9, 9))] * 11 + [("pantry", COLORS[1])]
        cases = (CASE, extra, CASE2)
        healthy = self.run_demo(products, cases=cases)
        self.assertEqual(healthy.size, (4 * T, 2 * ROW))  # unshown case is filtered
        for row in (0, 1):
            self.assert_ref(healthy, row, 0, COLORS[0])
            self.assert_ref(healthy, row, 1, COLORS[1])
            self.assert_cmp(healthy, row)

        # An eager open or lazy decode failure must not abort the sheet or shift its slots.
        for fault, index, slot in (("missing", 0, 0), ("damaged", 12, 1)):
            with self.subTest(reference=fault):
                sheet = self.run_demo(products, cases=cases, **{fault: index})
                self.assertEqual(sheet.size, healthy.size)
                for row in (0, 1):
                    self.assert_placeholder(sheet, row, slot)
                    for col in (1 - slot, 2, 3):
                        self.assertIsNone(ImageChops.difference(
                            self.cell(sheet, row, col), self.cell(healthy, row, col)).getbbox())

    def test_placeholder_is_honest_and_not_a_duplicate(self):
        sheet = self.run_demo([("pantry", COLORS[0])])
        ref, ph = self.cell(sheet, 0, 0), self.cell(sheet, 0, 1)
        self.assertNotEqual(ref.getpixel((T // 2, T // 2)), ph.getpixel((T // 2, T // 2)))
        self.assertEqual(set(ph.crop((0, 0, T, T)).getdata()), {demo.PAGE})

    def test_dense_catalog_sheet_unchanged_layout(self):
        sheet = self.run_demo([("pantry", COLORS[0])] + [("pantry", (9, 9, 9))] * 11 + [("pantry", COLORS[1])])
        expected = demo.tile(Image.new("RGB", (100, 100), COLORS[0]), "catalog: Prod 0")
        self.assertIsNone(ImageChops.difference(self.cell(sheet, 0, 0), expected).getbbox())


if __name__ == "__main__":
    unittest.main()
