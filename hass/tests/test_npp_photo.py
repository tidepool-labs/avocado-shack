"""S6 qualification against stored fixture photos and the unchanged install/editor boundaries."""
import hashlib
import io
import subprocess
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image, ImageFilter

from hass import media, photo_polish
from hass.npp import picture
from hass.ops import photos
from hass.tests.test_catalog_ops import _req
from hass.tests.test_photo_polish import ALT, NO_LABEL, Bare, Stub, edit_of, photo
from hass.tests.test_product_add_photo import _add
from hass.tests.test_set_photo import PhotoRepo, _settings


def choose(bare, sha, **kw):
    defaults = dict(has_person_or_screen=False, private_numbers_clear=lambda text, allowed: True,
                    ocr=lambda data: "HONEY")
    return picture.choose(bare.settings, sha, **{**defaults, **kw})


class PictureTests(unittest.TestCase):
    def test_exact_variant_path_and_bytes_match_legacy_install(self):
        # Flipping precedence or using the rejected render instead of web bytes breaks this matrix.
        clean = photo("jar-white-sheet")
        cluttered = photo("jar-dark-wood")
        polished = edit_of(clean)
        for name, data, polish, fallback, want, note in (
            ("verified edit", clean, True, True, "polished", ""),
            ("enabled polish skips house", clean, True, True, "raw", "picture: your own photo"),
            ("fallback off renders house even with polish", clean, True, False, "house", "picture: house style"),
            ("polish off renders house", clean, False, True, "house", "picture: house style"),
            ("polish off and house refused", cluttered, False, True, "raw", "picture: your own photo"),
            ("no fallback", cluttered, False, False, "none", ""),
        ):
            with self.subTest(name=name):
                bare = Bare(self, photo_polish=polish, itemIntake=fallback)
                sha = bare.store(data)
                if want == "polished":
                    with patch.object(photo_polish, "words", NO_LABEL):
                        self.assertEqual(photo_polish.run(bare.media, sha, transport=Stub(polished)), "ok")
                out = choose(bare, sha)
                ctx = bare.ctx()
                target = photos.install(ctx, sha, ALT, owner_fallback=fallback)
                if want == "none":
                    self.assertIsInstance(target, photos.Retake)
                    self.assertEqual(out, target)
                    self.assertEqual(ctx.assets, {})
                    continue
                assert isinstance(out, picture.FrozenPicture)
                self.assertEqual((out.variant, out.note, out.image_path), (want, note, target))
                self.assertEqual(target, f"assets/products/photo-{sha[:16]}.jpg")
                self.assertEqual(out.image_sha256, hashlib.sha256(ctx.assets[target]).hexdigest())
                if want == "raw":
                    path = media.web_copy(bare.media, sha)["path"]
                    self.assertEqual(ctx.assets[target], Path(path).read_bytes())

    def test_raw_retakes_for_sticker_screen_contact_or_failed_read_without_legacy_change(self):
        # A permissive S2 flag, OCR failure, or punctuation-stripping would otherwise allow a private picture.
        bare = Bare(self, itemIntake=True)
        sha = bare.store(photo("jar-white-sheet"))
        for name, flag, text in (
            ("screen", True, ""), ("unknown screen evidence", None, ""), ("no read", False, None),
            ("sticker", False, "$4"), ("price-shaped", False, "4.25"), ("cent sign", False, "4¢"),
            ("spoken money shape", False, "four bucks"),
            ("email", False, "sample" + "@example.net"),
            ("phone", False, "(212) " + "555-0101"), ("private path", False, "/" + "home/fixture/"),
        ):
            with self.subTest(name=name):
                got = choose(bare, sha, has_person_or_screen=flag, ocr=lambda data: text)
                self.assertEqual(got, photos.Retake(photos.RETAKE["style"], ("style",)))
        blank = choose(bare, sha, ocr=lambda data: "")
        assert isinstance(blank, picture.FrozenPicture)
        self.assertEqual(blank.variant, "raw")
        ctx = bare.ctx()
        self.assertIn(photos.install(ctx, sha, ALT, owner_fallback=True), ctx.assets)

    def test_raw_sharpness_applies_to_the_exact_web_copy(self):
        # Legacy skips house for live fallback; that must not bypass S6's blur check.
        bare = Bare(self, itemIntake=True)
        data = photo("jar-white-sheet")
        buf = io.BytesIO()
        with Image.open(io.BytesIO(data)) as im:
            im.filter(ImageFilter.GaussianBlur(8)).save(buf, "JPEG")
        sha = bare.store(buf.getvalue())
        self.assertEqual(choose(bare, sha), photos.Retake(photos.RETAKE["blurry"], ("blurry",)))

    def test_private_number_exception_requires_both_reads_of_the_label(self):
        # S6 must not bless a private value just because one reader saw it.
        bare = Bare(self, itemIntake=True)
        sha = bare.store(photo("jar-white-sheet"))
        def numbers_clear(text, allowed):
            return "12" not in text or "12" in allowed
        for model, source, accepted in (((), ("12",), False), (("12",), (), False), (("12",), ("12",), True)):
            with self.subTest(model=model, source=source):
                got = choose(bare, sha, ocr=lambda data: "Net wt 12 oz", private_numbers_clear=numbers_clear,
                             label_words=model, source_label_words=source)
                self.assertEqual(isinstance(got, picture.FrozenPicture), accepted)
        got = choose(bare, sha, private_numbers_clear=lambda text, allowed: None)
        self.assertIsInstance(got, photos.Retake)

    def test_s6_settles_raw_before_a_pending_edit_can_replace_it(self):
        # A late edit from B's worker cannot change already-selected raw bytes or start another edit.
        bare = Bare(self, itemIntake=True)
        sha = bare.store(photo("jar-white-sheet"))
        with patch.object(photo_polish, "_running", {sha}):
            out = choose(bare, sha)
        assert isinstance(out, picture.FrozenPicture)
        self.assertEqual(out.variant, "raw")
        decision = photo_polish.decision(bare.media, sha)
        assert decision is not None
        self.assertEqual(decision["code"], "late")
        self.assertFalse(photo_polish._settle(bare.media, sha, "polished", "ok", jpeg=b"late pixels"))
        transport = Mock(side_effect=AssertionError("settled decision must not rerun"))
        self.assertIsNone(photo_polish.start(bare.media, sha, transport=transport))
        transport.assert_not_called()
        self.assertEqual(choose(bare, sha), out)

    def test_editor_digest_binds_s6_and_apply_rejects_a_changed_picture(self):
        # A same-path replacement after settings change is stale, not a different image silently committed.
        repo = PhotoRepo()
        self.addCleanup(repo.cleanup)
        settings = {"mediaRoot": str(repo.media), "houseRender": True, "itemIntake": True, "photo_polish": True}
        _settings(repo, **settings)
        sha = repo.store(photo("jar-white-sheet"))
        req = _req(_add(photo=sha, imageAlt=ALT))
        bare = SimpleNamespace(settings=settings)
        frozen = choose(bare, sha)
        assert isinstance(frozen, picture.FrozenPicture)
        self.assertEqual(frozen.variant, "raw")
        with self.assertRaises(FrozenInstanceError):
            setattr(frozen, "variant", "house")
        draft = repo.prepare(req)["draft"]
        self.assertIs(frozen.matches_draft(draft), True)
        # Only the exact path and prefixed digest bind; unchecked .get() would raise on null/list.
        without_assets = {key: value for key, value in draft.items() if key != "assets"}
        exact_digest = draft["assets"][frozen.image_path]
        for case, candidate in (
            ("missing assets", without_assets),
            ("null assets", {**draft, "assets": None}),
            ("list assets", {**draft, "assets": [draft["assets"]]}),
            ("null draft", None),
            ("list draft", [draft]),
            ("wrong digest", {**draft, "assets": {frozen.image_path: "sha256:" + "0" * 64}}),
            ("missing prefix", {**draft, "assets": {frozen.image_path: frozen.image_sha256}}),
            ("wrong path", {**draft, "assets": {frozen.image_path + ".other": exact_digest}}),
        ):
            with self.subTest(case=case):
                self.assertIs(frozen.matches_draft(candidate), False)
        head = repo.head()
        _settings(repo, **{**settings, "photo_polish": False})
        self.assertEqual(repo.apply(draft)["result"], "stale")
        self.assertEqual(repo.head(), head)
        fresh = repo.prepare(req)["draft"]
        self.assertFalse(frozen.matches_draft(fresh))
        fresh_picture = choose(SimpleNamespace(settings={**settings, "photo_polish": False}), sha)
        assert isinstance(fresh_picture, picture.FrozenPicture)
        self.assertTrue(fresh_picture.matches_draft(fresh))
        self.assertEqual(repo.apply(fresh)["result"], "applied")
        committed = (repo.wt / "storefront-mockup" / frozen.image_path).read_bytes()
        self.assertEqual(fresh["assets"][frozen.image_path], "sha256:" + hashlib.sha256(committed).hexdigest())

    def test_raw_reader_preserves_symbols_and_distinguishes_failure_from_blank(self):
        # The second view must keep sticker tokens the normal read missed; failed reads are not blank.
        buf = io.BytesIO()
        Image.new("RGB", (1, 1), (242, 178, 14)).save(buf, "PNG")
        data = buf.getvalue()
        for code, stdout, want in ((0, b"$4\n", "$4"), (0, b"", ""), (1, b"", None), (0, b"\xff", None)):
            with self.subTest(code=code, stdout=stdout), patch.object(picture.subprocess, "run") as run:
                run.side_effect = [subprocess.CompletedProcess([], 0, stdout=b""),
                                   subprocess.CompletedProcess([], code, stdout=stdout)]
                self.assertEqual(picture.read_text(data), want)
                normal, sticker = [call.kwargs["input"] for call in run.call_args_list]
                self.assertEqual(normal, data)
                with Image.open(io.BytesIO(sticker)) as channel:
                    self.assertEqual((channel.mode, channel.getpixel((0, 0))), ("L", 242))
        with patch.object(picture.subprocess, "run", side_effect=subprocess.TimeoutExpired("tesseract", 1)):
            self.assertIsNone(picture.read_text(data, timeout=1))
