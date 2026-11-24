"""HASS-NEWITEM-1 (H10 gap): render an owner photo the way the catalog pictures look. Deterministic; Pillow only.

``render(data)`` takes JPEG/PNG bytes and returns the picture as it would sit on the site: upright (EXIF rotation applied
to the pixels, a leaning product straightened), the product isolated from a plain background and set large and centred on
the catalog's warm ivory with a soft contact shadow, 800x800, RGB, JPEG with no metadata at all (no EXIF, GPS, time,
device or colour profile). Every number comes from ``hass/style/house-style.json`` (measured); only the shadow recipe,
tuned against the measured ``shadow_depth``, is typed in here.

What it can and cannot do (nothing here uses a model):
* A plain or smoothly graded background (a sheet, a wall, a bench top) is separated reliably: the border colours are
  fitted as a plane, anything that differs from it is the subject, stray blobs and the photo's own cast shadow are dropped.
* A busy background (wood grain, cloth, a shelf of other goods) is NOT separated. ``report["isolation"]`` is then "fallback":
  the whole photo is fitted inside the frame on the ivory and ``report["review"]`` says it will not match the catalog.
  Cutting a subject out of clutter needs a vision/image-edit model (that is how the catalog pictures were made, see the
  generation log in storefront-mockup/image-generation-log.json); a hand-off card covers it. hass/label_reader.py only
  reads the label text, it does not isolate anything.
The same bytes in always give the same bytes out, so photos.install can compare an existing file with a re-render.
"""
from __future__ import annotations

import io
import math
import statistics
import warnings
from collections import deque

from hass import house_style as hs, media

SIZE = 800
MAX_PIXELS = 50_000_000  # header width x height; a 48 MP phone photo fits. Larger is refused before a pixel is decoded
FORMATS = {"jpeg": "JPEG", "png": "PNG"}  # Pillow may only open the kind media.check_photo found in the bytes
REPLIES = {
    "unreadable": media.REPLIES["unreadable"],
    "too-many-pixels": "That photo is too big for me to open (more than 50 megapixels), so nothing was drafted. "
                       "Please send a smaller copy or a screenshot of it.",
    "blank": "I could not find the item in that photo (the picture is empty or see-through), so nothing was drafted. "
             "Please send another photo of it.",
    "too-narrow": "That photo is a very thin strip (more than 40 times longer than it is wide), so nothing was drafted. "
                  "Please send an ordinary photo of the item.",
}


class Refused(ValueError):
    """A photo the renderer will not draw from; .code is one of REPLIES and .reply is the fixed owner text for it."""
    def __init__(self, code: str):
        super().__init__(code)
        self.code, self.reply = code, REPLIES[code]
ANALYSIS = 320  # long side of the working copy the coarse mask is found on
MIN_WORKING = 8  # short side (px) the working copy needs: the border ring and the mask maths need real rows and columns
JPEG_QUALITIES = (90, 85, 80, 74)
SHADOW = {"colour": (70, 55, 40), "alpha": 0.055, "blur": 11, "width": 0.8, "height": 0.055, "lift": 0.012}  # tuned to the measured shadow_depth
MAX_UPSCALE = 2.5
NOISY = 12  # border variation (levels) above which the background is called busy
STRAIGHTEN = (3.0, 20.0, 1.4)  # tilt range in degrees corrected, and the elongation a subject needs before its axis means anything


def _modules():
    Image, ImageOps = hs._pil()
    from PIL import ImageChops, ImageDraw, ImageEnhance, ImageFilter  # noqa: PLC0415 - Pillow is optional
    return Image, ImageOps, ImageChops, ImageDraw, ImageEnhance, ImageFilter


def _resample(Image, name):
    return getattr(getattr(Image, "Resampling", Image), name)


def _bg_plane(px, w, h, ring):
    """Per-side median colours of the border ring, fitted as ONE additive affine plane (x, y) -> (r, g, b) through the
    ring centroids, so a smooth light gradient is background, not subject. Also the border noise: the mean largest
    channel residual of the sampled outer border against that plane (unexplained texture, not explained illumination)."""
    side = lambda pts: tuple(int(statistics.median(p[i] for p in pts)) for i in range(3))  # noqa: E731
    top = side([px[y * w + x] for y in range(ring) for x in range(w)])
    bottom = side([px[y * w + x] for y in range(h - ring, h) for x in range(w)])
    left = side([px[y * w + x] for y in range(h) for x in range(ring)])
    right = side([px[y * w + x] for y in range(h) for x in range(w - ring, w)])
    cx, cy = (w - 1) / 2, (h - 1) / 2
    xl, yt = (ring - 1) / 2, (ring - 1) / 2
    xr, yb = w - 1 - xl, h - 1 - yt
    gx = [(right[i] - left[i]) / (xr - xl) for i in range(3)]
    gy = [(bottom[i] - top[i]) / (yb - yt) for i in range(3)]
    mid = [(left[i] + right[i] + top[i] + bottom[i]) / 4 for i in range(3)]

    def plane(x, y):
        return tuple(mid[i] + gx[i] * (x - cx) + gy[i] * (y - cy) for i in range(3))
    edge = ([(0, x) for x in range(0, w, 2)] + [(h - 1, x) for x in range(0, w, 2)]
            + [(y, 0) for y in range(0, h, 2)] + [(y, w - 1) for y in range(0, h, 2)])
    mad = statistics.fmean(max(abs(px[y * w + x][i] - r[i]) for i in range(3)) for y, x in edge for r in (plane(x, y),))
    return plane, mad


def _components(mask, w, h):
    """Connected areas of non-zero cells (4-neighbour), largest first: [(size, [index, ...])]."""
    seen, out = bytearray(w * h), []
    for start in range(w * h):
        if not mask[start] or seen[start]: continue
        seen[start] = 1
        queue, cells = deque([start]), []
        while queue:
            i = queue.popleft()
            cells.append(i)
            x, y = i % w, i // w
            for j in ((i - 1) if x else -1, (i + 1) if x < w - 1 else -1, i - w if y else -1, i + w if y < h - 1 else -1):
                if j >= 0 and mask[j] and not seen[j]:
                    seen[j] = 1
                    queue.append(j)
        out.append((len(cells), cells))
    return sorted(out, key=lambda c: -c[0])


def _shadowlike(c, ref) -> bool:
    """A pixel that is the background made darker (same colour, scaled): the photo's own cast shadow, not the product."""
    lc, lr = hs._luma(c), hs._luma(ref)
    if lr < 40: return False
    k = lc / lr
    return .35 < k < .98 and max(abs(c[i] - ref[i] * k) for i in range(3)) <= 12


def _continues(c, body) -> bool:
    """True when c is within 12 levels on every channel of the same column's body colour above it (None: no body)."""
    return body is not None and max(abs(c[i] - body[i]) for i in range(3)) <= 12


def _too_thin(size) -> bool:
    """True for a strip: scaled so its long side is ANALYSIS, its short side would be under MIN_WORKING px (over about 40:1)."""
    return round(min(size) * ANALYSIS / max(size)) < MIN_WORKING


def _fill_holes(m):
    """Binary L mask with its enclosed holes filled: background (0) that no four-neighbour path reaches from ANY border
    cell is the subject. Every border-connected background region stays background, however many there are."""
    _, _, ImageChops, ImageDraw, _, _ = _modules()
    inv = ImageChops.invert(m)
    w, h = inv.size
    border = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(1, h - 1) for x in (0, w - 1)]
    for seed in border:  # a region already flooded (128) is skipped, so each is traversed once
        if inv.getpixel(seed) == 255: ImageDraw.floodfill(inv, seed, 128)
    return inv.point(lambda v: 0 if v == 128 else 255)


def _coarse(img):
    """(coarse L mask, plane image, cast-shadow L mask, (w, h), delta, report) at analysis size, or (None, ..., report).
    Raises Refused("too-narrow") for a strip (a 1000x1 image has no border ring to measure)."""
    Image, _, _, _, _, ImageFilter = _modules()
    if _too_thin(img.size): raise Refused("too-narrow")
    scale = ANALYSIS / max(img.size)
    small = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), _resample(Image, "BOX"))
    w, h = small.size
    px = list(small.getdata())
    plane, mad = _bg_plane(px, w, h, max(2, round(min(w, h) * .03)))
    report = {"background_noise": round(mad, 1)}
    if mad > NOISY:
        return None, None, None, (w, h), 0, {**report, "isolation": "fallback", "reason": f"the background is not plain (its border varies by {mad:.0f} levels)"}
    delta = max(26.0, 3.2 * mad)
    refs = [plane(i % w, i // w) for i in range(w * h)]
    mask = bytearray(w * h)
    for i, (c, ref) in enumerate(zip(px, refs)):
        mask[i] = 1 if max(abs(c[0] - ref[0]), abs(c[1] - ref[1]), abs(c[2] - ref[2])) > delta else 0
    if not any(mask):
        return None, None, None, (w, h), delta, {**report, "isolation": "fallback", "reason": "nothing differs from the border colour"}
    rows = [y for y in range(h) if sum(mask[y * w:(y + 1) * w]) >= 2]
    shade = bytearray(w * h)
    if rows:  # the photo's own cast shadow: background-coloured but darker, in the foot of the subject only
        top, foot = rows[0], rows[-1]
        start = foot - max(2, round(.16 * (foot - top)))
        # each column's nearest ORIGINAL subject pixel above the foot band, taken before anything is removed: a foot
        # pixel matching it is the product carrying on down (a grey body), not its shadow
        body = [next((px[y * w + x] for y in range(start - 1, top - 1, -1) if mask[y * w + x]), None) for x in range(w)]
        for y in range(start, foot + 1):
            for x in range(w):
                if mask[y * w + x] and _shadowlike(px[y * w + x], refs[y * w + x]) and not _continues(px[y * w + x], body[x]):
                    mask[y * w + x], shade[y * w + x] = 0, 255
    comps = _components(mask, w, h)
    if not comps:
        return None, None, None, (w, h), delta, {**report, "isolation": "fallback", "reason": "no clear subject"}
    keep = [c for c in comps if c[0] >= max(0.12 * comps[0][0], 12)]
    flat = bytearray(w * h)
    for _size, cells in keep:
        for i in cells: flat[i] = 255
    m = Image.frombytes("L", (w, h), bytes(flat)).filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))  # close pin-holes
    m = _fill_holes(m)
    data = list(m.getdata())
    area = sum(1 for v in data if v) / (w * h)
    sides = ([data[x] for x in range(w)], [data[(h - 1) * w + x] for x in range(w)], [data[y * w] for y in range(h)], [data[y * w + w - 1] for y in range(h)])
    touching = sum(sum(1 for v in side if v) / len(side) > .6 for side in sides)
    report.update(area=round(area, 3), edges_touched=touching)
    if not .03 <= area <= .85 or touching >= 3:
        why = "the subject covers almost the whole photo" if area > .85 or touching >= 3 else "no clear subject"
        return None, None, None, (w, h), delta, {**report, "isolation": "fallback", "reason": why}
    plane_img = Image.new("RGB", (w, h))
    plane_img.putdata([tuple(round(v) for v in ref) for ref in refs])
    return m, plane_img, Image.frombytes("L", (w, h), bytes(shade)), (w, h), delta, {**report, "isolation": "cutout"}


def isolate(img):
    """(mask, report): mask is an L image at the photo's size, 255 on the subject, soft at the edge; None when the
    background is not plain enough (report["isolation"] == "fallback" and report["reason"])."""
    Image, _, ImageChops, _, _, ImageFilter = _modules()
    coarse, plane_img, shade, (w, h), delta, report = _coarse(img)
    if coarse is None: return None, report
    bil, size = _resample(Image, "BILINEAR"), img.size
    near = coarse.filter(ImageFilter.MaxFilter(5)).resize(size, bil).point(lambda v: 255 if v > 40 else 0)  # where the edge may lie
    core = coarse.filter(ImageFilter.MinFilter(9)).resize(size, bil).point(lambda v: 255 if v > 200 else 0)  # surely subject
    diff = ImageChops.difference(img, plane_img.resize(size, bil))
    r, g, b = diff.split()
    strongest = ImageChops.lighter(ImageChops.lighter(r, g), b)
    fine = strongest.point(lambda v: 255 if v > delta else 0)
    fine = ImageChops.subtract(fine, shade.filter(ImageFilter.MaxFilter(3)).resize(size, bil).point(lambda v: 255 if v > 60 else 0))  # not the cast shadow
    mask = ImageChops.lighter(ImageChops.darker(fine, near), core).filter(ImageFilter.MedianFilter(7))
    return mask.filter(ImageFilter.GaussianBlur(.9)), report


def _lean(mask):
    """Degrees the subject leans from the nearer of vertical/horizontal, from its second moments; None unless elongated enough."""
    Image, *_ = _modules()
    small = mask.resize((96, round(96 * mask.height / mask.width)) if mask.width >= mask.height else (round(96 * mask.width / mask.height), 96))
    w, h = small.size
    pts = [(i % w, i // w) for i, v in enumerate(small.getdata()) if v > 128]
    if len(pts) < 50: return None
    mx, my = statistics.fmean(p[0] for p in pts), statistics.fmean(p[1] for p in pts)
    sxx = statistics.fmean((p[0] - mx) ** 2 for p in pts)
    syy = statistics.fmean((p[1] - my) ** 2 for p in pts)
    sxy = statistics.fmean((p[0] - mx) * (p[1] - my) for p in pts)
    root = math.sqrt(((sxx - syy) / 2) ** 2 + sxy ** 2)
    long_, short = (sxx + syy) / 2 + root, (sxx + syy) / 2 - root
    if short <= 0 or math.sqrt(long_ / short) < STRAIGHTEN[2]: return None
    axis = math.degrees(0.5 * math.atan2(2 * sxy, sxx - syy))  # long-axis angle from the x axis, image coordinates
    off = axis - 90 if axis > 45 else axis + 90 if axis < -45 else axis  # clockwise lean from the nearer of vertical/horizontal
    return off if STRAIGHTEN[0] <= abs(off) <= STRAIGHTEN[1] else None


def _shadow_layer(canvas_size, box):
    """A blurred ellipse under the subject's foot, on an L layer: the catalog's soft contact shadow."""
    Image, _, _, ImageDraw, _, ImageFilter = _modules()
    layer = Image.new("L", canvas_size, 0)
    x0, y0, x1, y1 = box
    width, height = (x1 - x0) * SHADOW["width"], (y1 - y0) * SHADOW["height"]
    cx, foot = (x0 + x1) / 2, y1 - (y1 - y0) * SHADOW["lift"]
    ImageDraw.Draw(layer).ellipse((cx - width / 2, foot - height, cx + width / 2, foot + height), fill=255)
    return layer.filter(ImageFilter.GaussianBlur(SHADOW["blur"]))


def _decode(data):
    """The photo opened and decoded, after the store's own byte gate (media.check_photo: empty, 20 MB, JPEG/PNG only, structure)
    and a pixel budget read from the header BEFORE any pixel is decoded. Pillow's decompression-bomb warning is an error here.
    Anything that still fails to decode is Refused("unreadable"); nothing is returned half-read."""
    Image, *_ = _modules()
    kind = media.check_photo(data)  # raises media.Refused with the store's fixed reply
    bomb = (Image.DecompressionBombWarning, Image.DecompressionBombError)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            im = Image.open(io.BytesIO(data), formats=(FORMATS[kind],))
            w, h = im.size
            if not w or not h or w * h > MAX_PIXELS: raise Refused("too-many-pixels")
            im.load()
    except Refused:
        raise
    except bomb:
        raise Refused("too-many-pixels") from None
    except Exception:  # noqa: BLE001 - any decode failure of untrusted bytes is one fixed refusal, never a crash
        raise Refused("unreadable") from None
    return im


GRAY16_MODES = ("I", "I;16", "I;16L", "I;16B", "I;16N")  # how Pillow versions decode a 16-bit grayscale PNG


def _gray16(im, key):
    """PNG unsigned 16-bit grayscale only: (RGB, alpha or None). Each sample s (0..65535) becomes the fixed full-range gray
    (s*255+32767)//65535 repeated in RGB: no clipping, no per-image stretch. A tRNS key makes alpha 0 exactly where the ORIGINAL
    16-bit sample equals it (not the rounded gray), 255 elsewhere; no match means None."""
    Image, *_ = _modules()
    lut = bytes((s * 255 + 32767) // 65535 for s in range(65536))
    gray = Image.frombytes("L", im.size, bytes(lut[s] for s in im.getdata()))
    alpha = None
    if isinstance(key, int):
        cover = bytes(0 if s == key else 255 for s in im.getdata())
        if min(cover) == 0: alpha = Image.frombytes("L", im.size, cover)
    return gray.convert("RGB"), alpha


def _upright(data):
    """(RGB image with the EXIF rotation applied to the pixels, alpha channel or None, whether a rotation tag was present)."""
    _, ImageOps, *_ = _modules()
    im = _decode(data)
    turned = im.getexif().get(0x0112, 1) not in (None, 1)
    high, key = im.format == "PNG" and im.mode in GRAY16_MODES, im.info.get("transparency")
    im = ImageOps.exif_transpose(im)
    if high:
        rgb, alpha = _gray16(im, key)
        return rgb, alpha, turned
    alpha = None
    if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
        alpha = im.convert("RGBA").getchannel("A")
        if alpha.getextrema()[0] == 255: alpha = None  # fully opaque: no cutout supplied
    return im.convert("RGB"), alpha, turned


def _visible_luma(gray, cover):
    """Coverage-weighted mean grey of a cut-out with no nearly opaque pixel; nothing visible at all is a blank photo."""
    total = weight = 0
    for v, m in zip(gray, cover):
        total, weight = total + v * m, weight + m
    if not weight: raise Refused("blank")
    return total / weight


def render(data: bytes, spec=None) -> dict:
    """{"jpeg": bytes, "report": {...}, "check": house_style.check_image(...)} for one owner photo."""
    Image, _, ImageChops, ImageDraw, ImageEnhance, ImageFilter = _modules()
    spec = spec or hs.load_spec()
    stats = spec["pictures"]["catalog"]["metrics"]
    ivory = tuple(int(stats[f"bg_{c}"]["p50"]) for c in "rgb")
    lanczos = _resample(Image, "LANCZOS")
    img, alpha, turned = _upright(data)
    if _too_thin(img.size): raise Refused("too-narrow")  # also a supplied cut-out: the straightening maths needs width and height
    report = {"input": f"{img.width}x{img.height}", "rotation_applied": turned}
    if alpha is not None:
        # supplied coverage stays coupled to colour: premultiplied RGB, so invisible pixels' RGB never reaches a visible sample
        mask, found = alpha, {"isolation": "cutout", "source": "alpha channel"}
        img = Image.merge("RGB", [ImageChops.multiply(band, alpha) for band in img.split()])
    else:
        mask, found = isolate(img)
    report.update(found)
    review = []
    if mask is None:
        scaled = img.copy()
        scaled.thumbnail((round(SIZE * .94), round(SIZE * .94)), lanczos)
        canvas = Image.new("RGB", (SIZE, SIZE), ivory)
        canvas.paste(scaled, ((SIZE - scaled.width) // 2, (SIZE - scaled.height) // 2))
        review.append(f"Could not cut the product out ({found['reason']}); it will not look like the catalog pictures.")
    else:
        lean = _lean(mask)
        if lean is not None:  # straighten a leaning product; the corners the turn opens are never inside the mask
            img = img.rotate(lean, resample=_resample(Image, "BICUBIC"), expand=True, fillcolor=(0, 0, 0) if alpha is not None else img.getpixel((0, 0)))
            mask = mask.rotate(lean, resample=_resample(Image, "BICUBIC"), expand=True, fillcolor=0)
            report["straightened_degrees"] = round(lean, 1)
        box = mask.point(lambda v: 255 if v > 100 else 0).getbbox()
        if box is None: raise Refused("blank")  # e.g. an entirely transparent PNG: no subject to place
        pad = round(.012 * max(box[2] - box[0], box[3] - box[1]))
        box = (max(0, box[0] - pad), max(0, box[1] - pad), min(img.width, box[2] + pad), min(img.height, box[3] + pad))
        subject, cut = img.crop(box), mask.crop(box)
        target = min(stats["fill_max"]["p50"], .90) * SIZE
        factor = target / max(subject.size)
        report["scale"] = round(factor, 3)  # the REQUESTED frame-filling factor, before the cap: ops/photos.py and house_render read it for the small retake
        if factor > MAX_UPSCALE:
            review.append(f"The photo is small (product only {max(subject.size)} px); filling the frame would need {factor:.1f} times enlargement. I limited it to {MAX_UPSCALE:.1f} times; it may still look soft.")
            factor = MAX_UPSCALE
        size = (max(1, round(subject.width * factor)), max(1, round(subject.height * factor)))
        subject, cut = subject.resize(size, lanczos), cut.resize(size, lanczos)
        if alpha is not None:  # back to straight colour for the final source-over paste
            subject = Image.frombytes("RGBa", size, Image.merge("RGBA", (*subject.split(), cut)).tobytes()).convert("RGBA").convert("RGB")
        gray = subject.convert("L").getdata()
        solid = [v for v, m in zip(gray, cut.getdata()) if m > 200]
        luma = statistics.fmean(solid) if solid else _visible_luma(gray, cut.getdata())  # translucent all over: measure it, never a made-up grey
        lo, hi = stats["subject_luma"]["p05"], stats["subject_luma"]["p95"]
        if luma < lo or luma > hi:  # exposure only, within a gentle range: never recolour a label
            gain = max(.8, min(1.25, (lo if luma < lo else hi) / max(luma, 1.0)))  # a pure-black subject: the full lift, no zero divide
            subject = ImageEnhance.Brightness(subject).enhance(gain)
            report["exposure_gain"] = round(gain, 2)
        report["subject_luma"] = round(luma, 1)
        left, top = (SIZE - size[0]) // 2, round((SIZE - size[1]) / 2 + .006 * SIZE)
        top = max(round(.03 * SIZE), min(top, SIZE - size[1] - round(.045 * SIZE)))
        canvas = Image.new("RGB", (SIZE, SIZE), ivory)
        placed = (left, top, left + size[0], top + size[1])
        shade = _shadow_layer((SIZE, SIZE), placed).point(lambda v: round(v * SHADOW["alpha"]))
        canvas = Image.composite(Image.new("RGB", (SIZE, SIZE), SHADOW["colour"]), canvas, shade)
        canvas.paste(subject, (left, top), cut)
        report["box"] = list(placed)
    jpeg = b""
    for quality in JPEG_QUALITIES:  # the first that is not heavier than the catalog's heavier pictures
        buf = io.BytesIO()
        canvas.save(buf, "JPEG", quality=quality, optimize=True, subsampling=2)
        jpeg = buf.getvalue()
        report["jpeg_quality"] = quality
        if len(jpeg) <= stats["bytes"]["p95"] * 1.3: break
    check = hs.check_image(jpeg, spec)
    if not check["pass"]: review.append("The picture does not pass the house-style check: " + ", ".join(check["hard_failures"] or ["score %d" % check["score"]]))
    report["review"] = review
    return {"jpeg": jpeg, "report": report, "check": check}
