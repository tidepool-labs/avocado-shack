"""RF0345-11: apply_in_memory returns the product the real product.add created, never an older record sharing its image."""
import copy
import hashlib
import io
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from PIL import Image, PngImagePlugin

from hass import newitem, newitem_preview as preview
from hass.content_model import SHOP_TZ, load_content

SHARED = "assets/products/shared.jpg"
NOW = datetime.now(SHOP_TZ)
NEW = {"name": "New jar", "brand": "New maker", "category": "pantry", "description": "A new jar.", "imageAlt": "New jar"}


def base_content():
    """The real catalog plus two older products that already use the shared image (synthetic, in memory only)."""
    content = load_content()
    template = next(p for p in content.products if p["status"] == "active")
    for n, name in enumerate(("Old jar", "Older jar")):
        content.products.append({**copy.deepcopy(template), "id": f"zz-old-{n}", "name": name, "brand": f"Old maker {n}",
                                 "image": SHARED, "description": f"{name}."})
    return content


def add(**kw):
    return {"op": "product.add", "args": {**NEW, **kw}}


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.content = base_content()
        self.olds = [p for p in self.content.products if p["id"].startswith("zz-old-")]

    def test_shared_image_returns_created_product(self):
        after, product = preview.apply_in_memory(self.content, [add()], SHARED, NOW)
        self.assertEqual((product["name"], product["description"]), ("New jar", "A new jar."))
        self.assertNotIn(product["id"], {p["id"] for p in self.olds})
        self.assertTrue(any(p is product for p in after.products))
        self.assertTrue(all(product is not p for p in after.products if p["id"] != product["id"]))
        self.assertEqual(sum(p["image"] == SHARED for p in after.products), 3)

    def test_shared_image_final_availability_is_visible(self):
        ops = [add(), {"op": "product.set_availability", "args": {"id": "x", "available": "limited"}}]
        probe = preview.apply_in_memory(self.content, [add()], SHARED, NOW)[1]
        ops[1]["args"]["id"] = probe["id"]
        after, product = preview.apply_in_memory(self.content, ops, SHARED, NOW)
        self.assertEqual((product["available"], product["available_on"]), ("limited", after.store["selection_checked_on"]))
        self.assertTrue(any(p is product for p in after.products))

    def test_unique_image_control_and_maker_prefix(self):
        maker = {"op": "maker.add", "args": {"key": "New maker", "name": "New maker", "place": "Templeton, California", "story": "They make jars."}}
        after, product = preview.apply_in_memory(self.content, [maker, add(producerKey="New maker")], "assets/products/unique.jpg", NOW)
        self.assertEqual((product["name"], product["image"], product["producerKey"]), ("New jar", "assets/products/unique.jpg", "New maker"))
        self.assertIn("New maker", after.makers)

    def test_input_and_old_shared_records_unchanged(self):
        ops = [add()]
        before_content, before_ops = copy.deepcopy(self.content), copy.deepcopy(ops)
        after, _ = preview.apply_in_memory(self.content, ops, SHARED, NOW)
        self.assertEqual(self.content.products, before_content.products)
        self.assertEqual(self.content.store, before_content.store)
        self.assertEqual(ops, before_ops)
        self.assertEqual([p for p in after.products if p["id"].startswith("zz-old-")], self.olds)

    def test_no_creation_or_two_creations_refuse_internal_contract(self):
        second = add(name="Second jar", brand="Second maker")
        for ops, count in (([], 0), ([add(), second], 2)):
            with self.subTest(count=count):
                before = copy.deepcopy(self.content.products)
                with self.assertRaisesRegex(RuntimeError, f"exactly one product.add creation, got {count}"):
                    preview.apply_in_memory(self.content, ops, SHARED, NOW)
                self.assertEqual(self.content.products, before)

    def test_handler_refusal_stays_refusal(self):
        twin = add(name=self.olds[0]["name"], brand=self.olds[0]["brand"])
        before = copy.deepcopy(self.content.products)
        with self.assertRaisesRegex(RuntimeError, "product.add refused"):
            preview.apply_in_memory(self.content, [twin], SHARED, NOW)
        self.assertEqual(self.content.products, before)

    def test_capture_targets_use_created_id_and_displayed_image_bytes(self):
        # The two sides use the same new listing, but the before URL must hash
        # its stripped bytes, not the draft render or the metadata-bearing input.
        with io.BytesIO() as buf:
            Image.new("RGB", (4, 4), "blue").save(buf, "JPEG")
            after_bytes = buf.getvalue()
        draft = {"status": "draft", "reply": "r", "question": None,
                 "image": {"sha256": hashlib.sha256(after_bytes).hexdigest(), "path": SHARED, "bytes": after_bytes},
                 "ops": [add(photo=after_bytes)]}
        created = preview.apply_in_memory(self.content, [add()], SHARED, NOW)[1]
        captures = []
        viewports_seen = []

        class FakePreviewer:
            def __init__(self, repo, *, env, viewports):
                viewports_seen.append(viewports)

            def capture(self, files, target, out_png, assets=None):
                captures.append((target, files, assets))
                return {"ok": True, "error": None, "checks": {}, "png": None}

        png_info = PngImagePlugin.PngInfo()
        png_info.add_text("Comment", "fixture")
        with (tempfile.TemporaryDirectory() as tmp, mock.patch.object(preview, "OUT", Path(tmp)),
              mock.patch.object(newitem, "draft", return_value=draft),
              mock.patch.object(preview.preview, "Previewer", FakePreviewer)):
            for fmt, ext, metadata in (("JPEG", "jpg", {"comment": b"fixture"}),
                                       ("PNG", "png", {"pnginfo": png_info})):
                with self.subTest(format=fmt):
                    with Image.new("RGB", (4, 4), "red") as image, io.BytesIO() as clean, io.BytesIO() as tagged:
                        image.save(clean, fmt)
                        image.save(tagged, fmt, **metadata)
                        stripped, original = clean.getvalue(), tagged.getvalue()
                    self.assertNotEqual(original, stripped)
                    self.assertNotEqual(stripped, after_bytes)
                    captures.clear()
                    viewports_seen.clear()
                    preview.capture_case("case", "jar", "msg", "", original, self.content, {}, {})
                    (before, _, before_assets), (after, files, after_assets) = captures
                    self.assertEqual(viewports_seen, [("phone", "desktop")] * 2)
                    self.assertEqual((before["id"], after["id"]), (created["id"], created["id"]))
                    self.assertNotIn(created["id"], {p["id"] for p in self.olds})
                    self.assertEqual((after["image"], after["description"]), (SHARED, "A new jar."))
                    self.assertEqual(after_assets, {f"storefront-mockup/{SHARED}": after_bytes})
                    self.assertIn("A new jar.", files["storefront-mockup/catalog-products.js"].decode("utf-8"))
                    self.assertEqual(before_assets, {f"storefront-mockup/{before['image']}": stripped})
                    expected_before = f"assets/products/photo-{hashlib.sha256(stripped).hexdigest()[:16]}.{ext}"
                    self.assertEqual(before["image"], expected_before)


if __name__ == "__main__":
    unittest.main()
