"""HASS-IMAGE-1 tests: the background photo clean-up (``photo_polish``) behind an injectable transport.

Every path ends in a published picture or the existing fallback, and the interview never waits:
* a faithful edit is published (house-framed 800x800 JPEG, no metadata), the same bytes at every install;
* it also rescues a busy-background photo the house render alone would ask to retake;
* timeout, refusal, wrong size, wrong type, huge file, a changed product, a changed, blanked or partly erased label,
  an unreadable label (no tesseract, a failed or timed-out read), no Hermes: the fallback, and one short
  ``polish-<code>`` row in the correspondence log;
* ``start`` returns at once; an install that comes first settles the fallback and a late answer is dropped;
* the switch defaults off, is validated, and needs ``houseRender``.

The stub transport writes its picture where the Hermes runner would. Label reading is stubbed (CI has no tesseract):
``NO_LABEL`` is a read that worked and found no words; None is a read that did not work.
Needs Pillow; no network, no Hermes, no live service.
"""
import hashlib
import io
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hass import media, photo_polish

try:
    from PIL import Image
    from hass import newitem_synthetic as syn
    from hass.ops import photos
    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

ALT = "Cal Poly honey in a jar"
CASES = dict(syn.cases()) if HAVE_PIL else {}


def photo(name, **change):
    return syn.make_photo(**{**CASES[name], **change})


def png(im):
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def edit_of(data, size=1024, change=None):
    """What a faithful image edit looks like: the product on a plain ivory background, square, PNG."""
    im = Image.open(io.BytesIO(photos.house_picture(data)["jpeg"])).convert("RGB").resize((size, size))
    return png(change(im) if change else im)


NO_LABEL = lambda framed, scale=2: []  # noqa: E731 - tesseract read the picture and found no label words
REAL_WORDS = photo_polish.words  # the real reader, kept before the class-wide stubs replace it
TSV_HEAD = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"


def label_box(im):
    """(left, top, right, bottom) of the synthetic jar's cream label, from its amber body, on a photo or an edit."""
    r, g, b = im.convert("RGB").split()
    mask = Image.merge("RGB", (r.point(lambda v: 255 if v > 160 else 0), g.point(lambda v: 255 if 80 < v < 185 else 0),
                               b.point(lambda v: 255 if v < 90 else 0))).convert("L").point(lambda v: 255 if v > 254 else 0)
    x0, by0, x1, y1 = mask.getbbox()
    w, h = x1 - x0, (y1 - by0) / 0.86  # the body starts 14% down the jar (under the lid)
    top = y1 - h
    return round(x0 + .14 * w), round(top + .40 * h), round(x0 + .86 * w), round(top + .72 * h)


LABEL_WORDS = (("WILD", .04, .40), ("HONEY", .60, .96))  # two "words" across the label (shares of its width)


def labelled(data):
    """The synthetic jar photo with two clear printed words on its label: rows of dark strokes, a different rhythm
    for each word, in the middle quarter of the label's height (``LABEL_WORDS``)."""
    from PIL import ImageDraw
    im = Image.open(io.BytesIO(data)).convert("RGB")
    x0, y0, x1, y1 = label_box(im)
    w, h, d = x1 - x0, y1 - y0, ImageDraw.Draw(im)
    for n, (_word, a, b) in enumerate(LABEL_WORDS):
        x, end, top, bottom = x0 + a * w, x0 + b * w, y0 + .38 * h, y0 + .62 * h
        for i in range(99):
            stroke = (3, 7, 4, 2, 6)[(i + 2 * n) % 5]
            if x + stroke > end:
                break
            d.rectangle((x, top if i % 3 else top + (bottom - top) / 2, x + stroke, bottom), fill=(40, 30, 20))
            x += stroke + (4, 9, 5)[(i + n) % 3]
    out = io.BytesIO()
    im.save(out, "JPEG", quality=92)
    return out.getvalue()


class Stub:
    """transport(src, out, timeout): writes ``data`` to out (or answers ``said``), after ``wait`` seconds."""

    def __init__(self, data=None, said=None, wait=0.0):
        self.data, self.said, self.wait, self.calls = data, said, wait, 0

    def __call__(self, src, out, timeout):
        self.calls += 1
        time.sleep(self.wait)
        if self.said is not None:
            return self.said
        Path(out).write_bytes(self.data)
        return {"ok": True, "code": "ok"}


class Log:
    def __init__(self):
        self.rows = []

    def record(self, kind, reason, **kw):
        self.rows.append((kind, reason))
        return True


class Bare:
    def __init__(self, test, **settings):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.media, self.site = Path(tmp.name) / "media", Path(tmp.name) / "site"
        (self.site / "assets" / "products").mkdir(parents=True)
        self.settings = {"mediaRoot": str(self.media), "houseRender": True, "photo_polish": True, **settings}

    def ctx(self):
        return SimpleNamespace(settings=self.settings, site_dir=self.site, assets={})

    def store(self, data):
        return media.store_original(self.media, data, received_at="2026-11-16T10:00:00+00:00", source="fixture")["sha256"]

    def install(self, sha):
        ctx = self.ctx()
        out = photos.install(ctx, sha, ALT)
        return out, ctx.assets.get(out) if isinstance(out, str) else None


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
@mock.patch.object(photo_polish, "words", NO_LABEL)
class ContractTests(unittest.TestCase):
    def polish(self, bare, sha, stub):
        log = Log()
        code = photo_polish.run(bare.media, sha, log=log, transport=stub)
        return code, log.rows

    def test_a_faithful_edit_is_published_the_same_every_time(self):
        bare = Bare(self)
        data = photo("jar-white-sheet")
        sha = bare.store(data)
        code, rows = self.polish(bare, sha, Stub(edit_of(data)))
        self.assertEqual((code, rows), ("ok", []))
        target, first = bare.install(sha)
        self.assertEqual(target, f"assets/products/photo-{sha[:16]}.jpg")
        im = Image.open(io.BytesIO(first))
        self.assertEqual((im.format, im.size, im.mode), ("JPEG", (800, 800), "RGB"))
        self.assertFalse(im.getexif() or im.info.get("exif") or im.info.get("icc_profile"))
        self.assertNotEqual(first, photos.house_picture(data)["jpeg"])  # the edit, not the fallback
        self.assertEqual(bare.install(sha), (target, first))  # prepare, apply, verify: the same bytes
        self.assertEqual(photo_polish.decision(bare.media, sha)["use"], "polished")
        self.assertEqual(media.verify_store(bare.media)["result"], "ok")

    def test_a_busy_photo_is_rescued_by_a_faithful_edit(self):
        bare = Bare(self)
        busy = photo("jar-dark-wood")
        sha = bare.store(busy)
        alone = Bare(self, photo_polish=False)
        self.assertIsInstance(alone.install(alone.store(busy))[0], photos.Retake)  # the house render alone asks to retake
        plain = photo("jar-dark-wood", background="white-sheet")  # the same jar, as a clean edit would show it
        code, _ = self.polish(bare, sha, Stub(edit_of(plain)))
        self.assertEqual(code, "ok")
        target, data = bare.install(sha)
        self.assertEqual(target, f"assets/products/photo-{sha[:16]}.jpg")
        self.assertEqual(Image.open(io.BytesIO(data)).size, (800, 800))

    def test_fidelity_search_covers_a_product_filling_a_portrait_frame(self):
        edited = edit_of(photo("jar-white-sheet"))
        framed = photo_polish.frame(edited)["jpeg"]
        im = Image.open(io.BytesIO(framed))
        _, _, (x0, y0, x1, y1) = photo_polish._product(framed)
        portrait = im.crop((max(0, x0 * 2 - 8), max(0, y0 * 2 - 8),
                            min(im.width, x1 * 2 + 8), min(im.height, y1 * 2 + 8)))
        self.assertGreater(portrait.height, portrait.width)
        verdict = photo_polish.gate(png(portrait), edited)
        self.assertTrue(verdict["ok"], verdict["code"])
        self.assertGreater(verdict["metrics"]["where"][3], .85)  # matched the full jar, not just its label

    def assertFallback(self, stub, code, photo_name="jar-white-sheet", data=None):
        bare = Bare(self)
        data = data or photo(photo_name)
        sha = bare.store(data)
        got, rows = self.polish(bare, sha, stub)
        self.assertEqual(got, code)
        self.assertEqual(rows, [("error", f"polish-{code}")])
        target, published = bare.install(sha)
        self.assertEqual(published, photos.house_picture(bare_web(bare, sha))["jpeg"])  # exactly the old behaviour
        self.assertEqual(photo_polish.decision(bare.media, sha)["use"], "house")
        self.assertFalse((bare.media / "polish" / sha[:2] / f"{sha}.jpg").exists())
        return target

    def test_timeout_refusal_and_failures_use_the_fallback(self):
        for said in ({"ok": False, "code": "timeout"}, {"ok": False, "code": "api"}, {"ok": False, "code": "auth"}):
            with self.subTest(said=said):
                self.assertFallback(Stub(said=said), said["code"])
        self.assertFallback(Stub(said="garbage"), "failed")

    def test_a_transport_that_raises_uses_the_fallback(self):
        def boom(src, out, timeout):
            raise RuntimeError("no network")
        self.assertFallback(boom, "transport")

    def test_wrong_size_wrong_type_huge_and_empty_use_the_fallback(self):
        data = photo("jar-white-sheet")
        wide = Image.new("RGB", (1024, 600), (245, 240, 230))
        self.assertFallback(Stub(png(wide)), "size")
        self.assertFallback(Stub(png(Image.new("RGB", (300, 300), (245, 240, 230)))), "size")
        self.assertFallback(Stub(b"GIF89a" + bytes(2000)), "type")
        self.assertFallback(Stub(b"<html>no picture</html>"), "type")
        self.assertFallback(Stub(edit_of(data) + bytes(photo_polish.MAX_OUTPUT_BYTES)), "huge")
        self.assertFallback(Stub(b""), "empty")

    def test_a_changed_product_is_rejected(self):
        data = photo("jar-white-sheet")
        def recoloured(im):  # the jar turns another colour; the ivory background stays as it is
            from PIL import ImageChops
            bg = Image.new("RGB", im.size, im.getpixel((4, 4)))
            diff = ImageChops.difference(im, bg).convert("L").point(lambda v: 255 if v > 30 else 0)
            return Image.composite(Image.merge("RGB", im.split()[::-1]), im, diff)
        self.assertFallback(Stub(edit_of(data, change=recoloured)), "colour")
        swapped = lambda im: Image.merge("RGB", im.split()[::-1])  # noqa: E731 - background and all: not ivory any more
        self.assertFallback(Stub(edit_of(data, change=swapped)), "style")
        other = photo("bottle-bench-png")
        self.assertFallback(Stub(edit_of(other)), "colour")  # another product altogether: its colour gives it away first

    def test_changed_label_words_are_rejected(self):
        def centre_word(framed):  # "reads" one word across the middle of the product, wherever the render put it
            _rgb, _mask, box = photo_polish._product(framed)
            x0, y0, x1, y1 = (v * 2 for v in box)
            w, h = (x1 - x0) // 2, max(12, (y1 - y0) // 8)
            return [("SUNNY", ((x0 + x1) // 2 - w // 2, (y0 + y1) // 2 - h // 2, w, h))]

        def stamped(im):  # a new word painted across the label
            from PIL import ImageDraw
            d, (w, h) = ImageDraw.Draw(im), im.size
            d.rectangle((w * .3, h * .45, w * .7, h * .55), fill=(20, 20, 20))
            for i in range(5):
                d.rectangle((w * (.33 + i * .075), h * .47, w * (.36 + i * .075), h * .53), fill=(240, 240, 240))
            return im
        data = photo("jar-white-sheet")
        with mock.patch.object(photo_polish, "words", centre_word), mock.patch.object(photo_polish, "photo_words",
                                                                                      lambda _original: []):
            ok = Bare(self)
            self.assertEqual(self.polish(ok, ok.store(data), Stub(edit_of(data))), ("ok", []))  # the same marks: kept
            bad = Bare(self)
            code, rows = self.polish(bad, bad.store(data), Stub(edit_of(data, change=stamped)))
        self.assertEqual((code, rows), ("text", [("error", "polish-text")]))

    def test_unreadable_label_uses_the_fallback(self):
        """No tesseract, a failed or timed-out read, on either picture: the edit is unverified, so the fallback."""
        data = photo("jar-white-sheet")
        for edit_read, photo_read in ((lambda framed, scale=2: None, None), (None, lambda _original: None)):
            with self.subTest(edit=edit_read is not None), \
                    mock.patch.object(photo_polish, "words", edit_read or NO_LABEL), \
                    mock.patch.object(photo_polish, "photo_words", photo_read or (lambda _original: [])):
                self.assertFallback(Stub(edit_of(data)), "ocr")

    def test_words_is_none_whenever_tesseract_does_not_read(self):
        jpeg = photos.house_picture(photo("jar-white-sheet"))["jpeg"]
        with mock.patch.object(photo_polish.shutil, "which", return_value=None):
            self.assertIsNone(REAL_WORDS(jpeg))  # not installed
        with mock.patch.object(photo_polish.shutil, "which", return_value="/usr/bin/tesseract"):
            for effect in (OSError("cannot start"), photo_polish.subprocess.TimeoutExpired("tesseract", 30)):
                with self.subTest(effect=type(effect).__name__), \
                        mock.patch.object(photo_polish.subprocess, "run", side_effect=effect):
                    self.assertIsNone(REAL_WORDS(jpeg))
            for done in (SimpleNamespace(returncode=1, stdout=TSV_HEAD), SimpleNamespace(returncode=0, stdout="")):
                with self.subTest(done=done), mock.patch.object(photo_polish.subprocess, "run", return_value=done):
                    self.assertIsNone(REAL_WORDS(jpeg))  # a failed read is not an empty label
            row = "5\t1\t1\t1\t1\t1\t10\t20\t80\t24\t91\tHoney\n"
            with mock.patch.object(photo_polish.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=TSV_HEAD + row)):
                self.assertEqual(REAL_WORDS(jpeg), [("HONEY", (5, 10, 40, 12))])
            with mock.patch.object(photo_polish.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=TSV_HEAD)):
                self.assertEqual(REAL_WORDS(jpeg), [])  # read fine, no words: an empty label

    def test_a_removed_label_or_word_is_rejected(self):
        """The photo's label words must still be on the edit at that spot: a blank label or one erased word is caught."""
        def word_boxes(im):  # (word, (left, top, width, height)) of the two words drawn on the label, on any copy
            x0, y0, x1, y1 = label_box(im)
            w, h = x1 - x0, y1 - y0
            return [(word, (round(x0 + a * w), round(y0 + .38 * h), round((b - a) * w), round(.24 * h)))
                    for word, a, b in LABEL_WORDS]

        def cover(words):
            def change(im):
                from PIL import ImageDraw
                for word, (left, top, width, height) in word_boxes(im):
                    if word in words:
                        ImageDraw.Draw(im).rectangle((left - 3, top - 3, left + width + 3, top + height + 3),
                                                     fill=(246, 238, 214))
                return im
            return change
        data = labelled(photo("jar-white-sheet"))
        reads = lambda original: word_boxes(Image.open(io.BytesIO(original)).convert("RGB"))  # noqa: E731
        with mock.patch.object(photo_polish, "photo_words", reads):
            ok = Bare(self)
            self.assertEqual(self.polish(ok, ok.store(data), Stub(edit_of(data))), ("ok", []))  # all kept
            for name, gone in (("blank label", {"WILD", "HONEY"}), ("one word removed", {"HONEY"})):
                with self.subTest(name):
                    self.assertFallback(Stub(edit_of(data, change=cover(gone))), "text", data=data)
        H = (10, 10, 50, 12)  # where a photo word occurrence maps to on the edit; FAR is somewhere else on the label
        FAR = (10, 60, 50, 12)
        self.assertTrue(photo_polish.text_removed([("WILD", 0.8, H), ("HONEY", -1.0, H)], []))
        self.assertTrue(photo_polish.text_removed([("WILD", 0.8, H), ("HONEY", -1.0, H)], [("HONEY", H)]))  # blank spot
        self.assertTrue(photo_polish.text_removed([("HONEY", 0.42, H)], []))  # faint likeness, never read: gone
        self.assertFalse(photo_polish.text_removed([("HONEY", 0.42, H)], [("HONEY", (12, 11, 48, 12))]))  # read there
        self.assertTrue(photo_polish.text_removed([("HONEY", 0.42, H)], [("HONEY", FAR)]))  # read, but elsewhere
        self.assertFalse(photo_polish.text_removed([("RAW", 0.42, H), ("HONEY", 0.6, H)], []))  # short word / same
        self.assertTrue(photo_polish.text_removed([("HONEY", None, H)], [("TEA", H)]))  # cannot be judged, not read
        self.assertFalse(photo_polish.text_removed([("HONEY", None, H), ("RAW", None, H)], [("HONE", H)]))  # OCR slip
        self.assertTrue(photo_polish.text_removed([("HONEY", None, None)], [("HONEY", H)]))  # off the product: unproven

    def test_one_of_a_repeated_word_removed_is_rejected(self):
        """A word printed twice: erasing one occurrence is caught even though the edit still reads the word elsewhere.
        Each occurrence must be kept at its own spot (one edit read vouches for one occurrence, nearby only)."""
        def boxes(im):
            x0, y0, x1, y1 = label_box(im)
            w, h = x1 - x0, y1 - y0
            return [("HONEY", (round(x0 + a * w), round(y0 + .38 * h), round((b - a) * w), round(.24 * h)))
                    for _word, a, b in LABEL_WORDS]

        def erase_first(im):
            from PIL import ImageDraw
            left, top, width, height = boxes(im)[0][1]
            ImageDraw.Draw(im).rectangle((left - 3, top - 3, left + width + 3, top + height + 3), fill=(246, 238, 214))
            return im
        data = labelled(photo("jar-white-sheet"))
        reads = lambda original: boxes(Image.open(io.BytesIO(original)).convert("RGB"))  # noqa: E731
        edit_reads = lambda framed, scale=2: boxes(Image.open(io.BytesIO(framed)).convert("RGB"))  # noqa: E731
        with mock.patch.object(photo_polish, "photo_words", reads), mock.patch.object(photo_polish, "words", edit_reads):
            self.assertTrue(photo_polish.gate(data, edit_of(data))["ok"])  # both kept
            result = photo_polish.gate(data, edit_of(data, change=erase_first))
        self.assertEqual(result["code"], "text")
        self.assertTrue(result["metrics"]["text_removed"])
        self.assertLess(result["metrics"]["kept"][0][1], photo_polish.WORD_MIN)

    def test_a_plausible_new_word_must_be_read_on_the_photo(self):
        known = {"HONE", "ILDFLOWER", "RIDGE", "ROAS"}  # what tesseract reads on Mike's photo, slips included
        self.assertFalse(photo_polish.text_changed([("HONEY", 0.5), ("WILDFLOWER", 0.4), ("ROAST", 0.45)], known))
        self.assertTrue(photo_polish.text_changed([("SUNNY", 0.40)], known))  # looks a little like it, never read
        self.assertFalse(photo_polish.text_changed([("SUNNY", 0.7)], known))  # looks like that spot: kept
        self.assertFalse(photo_polish.text_changed([("SUNNY", 0.40)], set()))  # the photo reads nothing: marks only
        self.assertFalse(photo_polish.text_changed([("SUN", 0.40), ("SUNNY", None)], known))  # too short / too small
        self.assertTrue(photo_polish.text_changed([("HONEY", 0.2)], known))  # unlike that spot, read or not

    def test_no_hermes_uses_the_fallback(self):
        transport = photo_polish.HermesTransport(launcher="/nonexistent/hermes")
        self.assertFallback(transport, "no-hermes")


def bare_web(bare, sha):
    return Path(media.web_copy(bare.media, sha)["path"]).read_bytes()


def label_words(im):
    """(word, (left, top, width, height)) of the two stroke words ``labelled`` draws, on a photo or any copy of it."""
    x0, y0, x1, y1 = label_box(im)
    w, h = x1 - x0, y1 - y0
    return [(word, (round(x0 + a * w), round(y0 + .38 * h), round((b - a) * w), round(.24 * h)))
            for word, a, b in LABEL_WORDS]


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
@mock.patch.object(photo_polish, "words", NO_LABEL)
class WordMapTests(unittest.TestCase):
    """The label words are judged where they really are on the edit. ``match`` finds the product in 11 % size steps
    and five stretches; on this jar the best coarse place is a size step too tall and a stretch too narrow, so on the
    coarse place alone an unchanged word looked erased (both under WORD_SURE, nothing read on the edit: ``text``).
    The word map is refined on the product's own correlation, never on the words."""

    def jar(self):
        return labelled(syn.make_photo(background="white-sheet", size=(1024, 1024), seed=2, fmt="PNG"))

    def reads(self, original):
        return label_words(Image.open(io.BytesIO(original)).convert("RGB"))

    def test_an_unchanged_label_is_kept(self):
        data = self.jar()
        with mock.patch.object(photo_polish, "photo_words", self.reads):
            for name, edited in (("the photo itself", data), ("a faithful edit", edit_of(data))):
                with self.subTest(name):
                    verdict = photo_polish.gate(data, edited)
                    self.assertEqual(verdict["code"], "ok", verdict["metrics"].get("kept"))
                    for word, score in verdict["metrics"]["kept"]:
                        self.assertGreaterEqual(score, photo_polish.WORD_SURE, word)

    def test_the_word_map_lands_on_the_words(self):
        data = self.jar()
        made = photo_polish.frame(data)["jpeg"]
        m = photo_polish.match(data, made)
        (fw, fh), (rx, ry, rw, rh), (bx0, by0, bx1, by1) = m["_map"]
        sx, sy = rw * fw / (bx1 - bx0), rh * fh / (by1 - by0)
        self.assertAlmostEqual(sx / sy, 1.0, delta=0.03)  # the edit is the photo, scaled the same both ways
        truth = label_words(Image.open(io.BytesIO(made)).convert("RGB"))
        kept = photo_polish.kept_scores(data, made, m["_map"], self.reads(data))
        for (word, _score, (left, top, width, height)), (_w, (tl, tt, tw, th)) in zip(kept, truth):
            with self.subTest(word):  # within a quarter of the word's height of where it really is, both ways
                self.assertLess(abs(left - tl), th / 4)
                self.assertLess(abs(top - tt), th / 4)
                self.assertLess(abs(width - tw), th / 4)

    def test_the_match_verdict_is_still_the_coarse_one(self):
        data = self.jar()
        made = photo_polish.frame(data)["jpeg"]
        m = photo_polish.match(data, made)
        self.assertIn("map_fit", m)
        with mock.patch.object(photo_polish, "_register", side_effect=lambda *a, **k: (0.0, a[2])):
            coarse = photo_polish.match(data, made)  # the refinement switched off: start place, no climb
        for key in ("match", "hue_shift", "chroma", "where"):
            self.assertEqual(m[key], coarse[key], key)

    def test_an_erased_word_is_still_caught(self):
        def cover(words):
            def change(im):
                from PIL import ImageDraw
                for word, (left, top, width, height) in label_words(im):
                    if word in words:
                        ImageDraw.Draw(im).rectangle((left - 3, top - 3, left + width + 3, top + height + 3),
                                                     fill=(246, 238, 214))
                return im
            return change
        data = self.jar()
        with mock.patch.object(photo_polish, "photo_words", self.reads):
            for name, gone in (("blank label", {"WILD", "HONEY"}), ("one word removed", {"HONEY"}),
                               ("the other word removed", {"WILD"})):
                with self.subTest(name):
                    verdict = photo_polish.gate(data, edit_of(data, change=cover(gone)))
                    self.assertEqual(verdict["code"], "text")
                    self.assertTrue(verdict["metrics"]["text_removed"])
                    scores = dict(verdict["metrics"]["kept"])
                    for word in gone:
                        self.assertLess(scores[word], photo_polish.WORD_MIN, word)


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class OCRFailureTests(unittest.TestCase):
    """The real ``words`` reader through ``run``: a read that does not work settles the house fallback (``ocr``)."""

    def test_unavailable_ocr_uses_the_house_fallback(self):
        data = photo("jar-white-sheet")
        edited = edit_of(data)
        failures = (
            (None, None, None),  # executable absent
            ("tesseract", OSError("unavailable"), None),
            ("tesseract", photo_polish.subprocess.TimeoutExpired("tesseract", 30), None),
            ("tesseract", None, SimpleNamespace(returncode=1, stdout="")),
        )
        for executable, error, done in failures:
            with self.subTest(executable=executable, error=error, done=done):
                bare = Bare(self)
                sha = bare.store(data)
                log = Log()
                with mock.patch.object(photo_polish.shutil, "which", return_value=executable), mock.patch.object(
                    photo_polish.subprocess, "run", side_effect=error, return_value=done
                ):
                    code = photo_polish.run(bare.media, sha, log=log, transport=Stub(edited))
                self.assertEqual(code, "ocr")
                self.assertEqual(log.rows, [("error", "polish-ocr")])
                self.assertEqual(bare.install(sha)[1], photos.house_picture(bare_web(bare, sha))["jpeg"])
                self.assertEqual(photo_polish.decision(bare.media, sha)["use"], "house")
                self.assertFalse((bare.media / "polish" / sha[:2] / f"{sha}.jpg").exists())

    def test_unavailable_source_ocr_also_uses_the_house_fallback(self):
        data = photo("jar-white-sheet")
        bare = Bare(self)
        sha = bare.store(data)
        log = Log()
        found = [("HONEY", (250, 300, 100, 20))]
        with mock.patch.object(photo_polish, "words", side_effect=[found, None]):  # the edit reads, the photo does not
            code = photo_polish.run(bare.media, sha, log=log, transport=Stub(edit_of(data)))
        self.assertEqual(code, "ocr")
        self.assertEqual(log.rows, [("error", "polish-ocr")])
        self.assertEqual(bare.install(sha)[1], photos.house_picture(bare_web(bare, sha))["jpeg"])
        self.assertEqual(photo_polish.decision(bare.media, sha)["use"], "house")


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
@mock.patch.object(photo_polish, "words", NO_LABEL)
class BackgroundTests(unittest.TestCase):
    def test_start_never_waits_and_a_late_answer_is_dropped(self):
        bare = Bare(self)
        data = photo("jar-white-sheet")
        sha = bare.store(data)
        gate = threading.Event()

        def slow(src, out, timeout):
            gate.wait(10)
            Path(out).write_bytes(edit_of(data))
            return {"ok": True, "code": "ok"}
        log = Log()
        began = time.monotonic()
        worker = photo_polish.start(bare.media, sha, log=log, transport=slow)
        self.assertLess(time.monotonic() - began, 0.5)  # the interview goes on at once
        self.assertIsNone(photo_polish.start(bare.media, sha, transport=slow))  # one job per photo
        target, first = bare.install(sha)  # the preview comes before the answer: the fallback is settled now
        self.assertIsInstance(target, str, target)
        self.assertEqual(first, photos.house_picture(bare_web(bare, sha))["jpeg"])
        gate.set()
        worker.join(30)
        self.assertEqual(log.rows, [("error", "polish-late")])
        self.assertEqual(bare.install(sha), (target, first))  # still the same bytes at apply and verify
        self.assertEqual(photo_polish.decision(bare.media, sha)["code"], "late")

    def test_a_settled_photo_is_not_sent_again(self):
        from PIL import Image
        from hass.ops import photos

        bare = Bare(self)
        data = photo("jar-white-sheet")
        sha = bare.store(data)
        stub = Stub(said={"ok": False, "code": "api"})
        photo_polish.run(bare.media, sha, transport=stub)
        self.assertIsNone(photo_polish.start(bare.media, sha, transport=stub))
        self.assertEqual(stub.calls, 1)

        house = photos.house_picture(bare_web(bare, sha))["jpeg"]
        out = io.BytesIO()
        with Image.open(io.BytesIO(house)) as image:
            image.save(out, "JPEG", quality=84)
        jpeg = out.getvalue()
        self.assertNotEqual(jpeg, house)
        saved = {"use": "polished", "jpeg_sha256": hashlib.sha256(jpeg).hexdigest()}
        single = json.dumps(saved).encode("utf-8")
        # Last-key-wins would select the polished bytes despite the conflicting house decision.
        for raw, decision, picture in (
            (single, saved, jpeg),
            (b'{"use":"house",' + single[1:], {"use": "house", "code": "bad-record"}, house),
        ):
            with self.subTest(decision=decision):
                bare = Bare(self)
                sha = bare.store(data)
                folder = photo_polish._folder(bare.media, sha)
                record = folder / f"{sha}.json"
                media._write_new(record, raw)
                media._write_new(folder / f"{sha}.jpg", jpeg)
                before = record.stat()
                transport = mock.Mock(side_effect=AssertionError("settled photo sent again"))
                self.assertIsNone(photo_polish.start(bare.media, sha, transport=transport))
                transport.assert_not_called()
                target, installed = bare.install(sha)
                self.assertEqual(target, f"assets/products/photo-{sha[:16]}.jpg")
                self.assertTrue(installed == picture, "installer selected different JPEG bytes")
                self.assertEqual(photo_polish.decision(bare.media, sha), decision)
                self.assertEqual(record.read_bytes(), raw)
                after = record.stat()
                self.assertEqual((after.st_ino, after.st_mtime_ns), (before.st_ino, before.st_mtime_ns))

    def test_switch_off_or_without_house_render_installs_as_before(self):
        data = photo("jar-white-sheet")
        for settings in ({"photo_polish": False}, {"photo_polish": "true"}, {"houseRender": False}):
            with self.subTest(settings=settings):
                bare = Bare(self, **settings)
                sha = bare.store(data)
                photo_polish.run(bare.media, sha, transport=Stub(edit_of(data)))
                ctx = SimpleNamespace(settings=bare.settings, site_dir=bare.site, assets={})
                target = photos.install(ctx, sha, ALT)
                house = bare.settings["houseRender"] is True
                want = photos.house_picture(bare_web(bare, sha))["jpeg"] if house else bare_web(bare, sha)
                self.assertEqual(ctx.assets[target], want)


class SettingTests(unittest.TestCase):
    def test_enabled_needs_both_switches_as_json_true(self):
        self.assertTrue(photo_polish.enabled({"photo_polish": True, "houseRender": True}))
        for settings in ({}, {"photo_polish": True}, {"photo_polish": 1, "houseRender": True},
                         {"photo_polish": "true", "houseRender": True}, {"photo_polish": True, "houseRender": False}):
            self.assertFalse(photo_polish.enabled(settings), settings)

    def test_the_model_is_one_line(self):
        source = Path(photo_polish.__file__).read_text("utf-8")
        self.assertEqual(sum(1 for line in source.splitlines() if "gpt-image-2-high" in line), 1)
        self.assertEqual(photo_polish.MODEL, "openai-codex:gpt-image-2-high")

    def test_find_hermes_reads_the_launcher_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, py = Path(tmp) / "release", Path(tmp) / "python3"
            (root / ".hermes" / "bin").mkdir(parents=True)
            py.write_text("")
            (root / ".hermes" / "bin" / "hermes").write_text(
                f"#!/bin/sh\nexec {py} -I -c 'import os\nsys.path.insert(0, '\"'\"'{root}'\"'\"')\n'\n")
            link = Path(tmp) / "current"
            link.symlink_to(root)
            outer = Path(tmp) / "hermes"
            outer.write_text(f"#!/usr/bin/env bash\nrelease_root=$(readlink -f {link})\nexec x\n")
            self.assertEqual(photo_polish.find_hermes(str(outer)), (str(py), str(root)))
            self.assertIsNone(photo_polish.find_hermes(str(Path(tmp) / "missing")))

    def test_transport_timeout_is_a_short_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            sleeper = Path(tmp) / "sleep.py"
            sleeper.write_text("import time\ntime.sleep(5)\n")
            transport = photo_polish.HermesTransport(python=sys.executable, root=tmp)
            with mock.patch.object(photo_polish.subprocess, "run", side_effect=photo_polish.subprocess.TimeoutExpired("x", 1)):
                self.assertEqual(transport(Path(tmp) / "in.png", Path(tmp) / "out.img", 1), {"ok": False, "code": "timeout"})
            done = SimpleNamespace(stdout=json.dumps({"ok": False, "code": "api"}) + "\n")
            with mock.patch.object(photo_polish.subprocess, "run", return_value=done):
                self.assertEqual(transport(Path(tmp) / "in.png", Path(tmp) / "out.img", 1), {"ok": False, "code": "api"})
            done = SimpleNamespace(stdout=json.dumps({"ok": False, "code": "Bearer abc/def"}) + "\n")
            with mock.patch.object(photo_polish.subprocess, "run", return_value=done):  # never a free text through
                self.assertEqual(transport(Path(tmp) / "in.png", Path(tmp) / "out.img", 1), {"ok": False, "code": "failed"})
            self.assertEqual(list(Path(tmp).glob("*.txt")), [])  # the prompt file is gone

    def test_load_settings_defaults_off_and_validates(self):
        from hass import conversation
        base = {"ownerSenders": ["+15555550100"], "ownerChat": "iMessage;-;+15555550100", "approvalTtlSeconds": 600}
        with tempfile.TemporaryDirectory() as tmp:
            def load(**extra):
                (Path(tmp) / "config.json").write_text(json.dumps({"settings": {**base, **extra}}))
                return conversation.load_settings(tmp)
            self.assertNotIn("photo_polish", load())  # absent = off; the settings dict is unchanged for everyone else
            self.assertIs(load(houseRender=True, photo_polish=True)["photo_polish"], True)
            for bad in ({"photo_polish": "true", "houseRender": True}, {"photo_polish": 1, "houseRender": True},
                        {"photo_polish": True}, {"photo_polish": True, "houseRender": False}):
                with self.subTest(settings=bad), self.assertRaisesRegex(conversation.ConfigError, "photo_polish must be"):
                    load(**bad)


if __name__ == "__main__":
    unittest.main()
