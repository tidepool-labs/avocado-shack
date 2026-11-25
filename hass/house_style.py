"""HASS-NEWITEM-1 (H10/H13 gap): the measured Avocado Shack house style, as a machine-usable spec plus checks.

``hass/style/house-style.json`` is MEASURED from the repo's live content (hass/content/*.json and the product pictures
under storefront-mockup/assets/products/), never hand-tuned. ``python3 hass/house_style.py measure`` rebuilds it;
``verify`` says whether the committed file still matches the content. ``check_image``, ``check_description``,
``check_maker`` and ``check_product`` score a NEW item against it: {"score": 0-100, "pass": bool, "checks": [...]}.
A check is hard (a failure fails the item whatever the score) or soft (it only lowers the score).

Text, record and spec code is standard library only. Reading or measuring a picture needs Pillow (already used by
inventory-intake/import_photos.py and the logo steps in storefront-mockup/README.md); without it the image functions raise
``PillowMissing`` and nothing else is affected. ``check-image FILE`` exits 0/1 on a scored pass/fail, and 2 with one fixed path-free stderr line when the picture cannot
be read, decoded or assessed (no Pillow). Reads only; the one write is ``measure --out FILE`` on request.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import claims  # noqa: E402
from hass.content_model import (CATEGORIES, FORBIDDEN_TEXT, MAKER_FIELDS, PRODUCT_INTERNAL_FIELDS,  # noqa: E402
                                PRODUCT_OPTIONAL_PUBLIC, PRODUCT_PUBLIC_FIELDS, REPO_ROOT, SHELF_LABELS, TEXT_LIMITS,
                                _https, _text, load_content)

SPEC_PATH = REPO_ROOT / "hass" / "style" / "house-style.json"
SITE = REPO_ROOT / "storefront-mockup"
WORK = 160  # pictures are measured on a 160x160 box-averaged copy: deterministic, fast, noise-tolerant
RING, SUBJECT_DELTA, MIN_LINE = 6, 30, 3  # border ring px, colour distance that counts as "not background", px per row/col
CATALOG_IMAGE_RE = re.compile(r"assets/products/photo-product-\d{3}\.webp")
OWNER_IMAGE_RE = re.compile(r"assets/products/photo-[0-9a-f]{16}\.(jpg|png)")  # shop.js installedImage + HOME_IMAGE_RE
HYPE_SEED = ("amazing", "best", "delicious", "perfect", "incredible", "awesome", "finest", "premium", "luxury", "gourmet",
             "must-try", "unbelievable", "world-class", "famous", "authentic", "tasty", "yummy", "mouthwatering",
             "irresistible", "ultimate", "healthy", "natural", "fresh-picked", "farm-fresh", "artisanal", "limited edition")
MAKER_PLACE_RE = re.compile(r"[A-Z][\w’' .-]+, [A-Z][\w’' .-]+|California’s Central Coast|Northern California")


class PillowMissing(RuntimeError):
    """Pictures cannot be read or measured without Pillow."""


def _pil():
    try:
        from PIL import Image, ImageOps  # noqa: F401
    except ImportError:  # pragma: no cover - exercised only where Pillow is absent
        raise PillowMissing("Pillow is needed to read pictures (python3 -m pip install Pillow)") from None
    return Image, ImageOps


# ---------------------------------------------------------------- numbers
def percentiles(values) -> dict:
    vals = sorted(values)
    n = len(vals)
    pick = lambda q: vals[min(n - 1, int(q * n))]  # noqa: E731
    return {"min": round(vals[0], 4), "p05": round(pick(.05), 4), "p25": round(pick(.25), 4), "p50": round(vals[n // 2], 4),
            "p75": round(pick(.75), 4), "p95": round(pick(.95), 4), "max": round(vals[-1], 4)}


def _luma(c) -> float:
    return .299 * c[0] + .587 * c[1] + .114 * c[2]


def _sat(c) -> float:
    hi, lo = max(c), min(c)
    return 0.0 if hi == 0 else (hi - lo) / hi


# ---------------------------------------------------------------- pictures
MIN_PATCH = 12  # px (of the 160x160 working copy) a background-coloured patch needs to count


def _enclosed_patches(mask) -> tuple:
    """(count, share of the frame) of background-coloured patches that do not reach the picture's edge: air inside a handle
    or between grouped goods in a catalog picture, but dozens of them where a patterned photo background (a checkered cloth,
    a plank table) is still around the product, because its pale squares look like the ivory."""
    n = len(mask)
    seen = [[False] * n for _ in range(n)]
    sizes = []
    for y0 in range(n):
        for x0 in range(n):
            if mask[y0][x0] or seen[y0][x0]: continue
            seen[y0][x0], stack, cells, edge = True, [(x0, y0)], 0, False
            while stack:
                x, y = stack.pop()
                cells += 1
                edge = edge or x in (0, n - 1) or y in (0, n - 1)
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < n and 0 <= ny < n and not mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if not edge and cells >= MIN_PATCH: sizes.append(cells)
    return len(sizes), round(sum(sizes) / (n * n), 4)


def image_metrics(im) -> dict:
    """Measured facts of one PIL image: size, background, uniformity, subject box, centring, shadow, light, colour."""
    Image, _ = _pil()
    resample = getattr(Image, "Resampling", Image).BOX
    out = {"width": im.width, "height": im.height, "aspect": round(im.width / im.height, 4), "mode": im.mode,
           "has_exif": bool(im.info.get("exif")) or bool(getattr(im, "getexif", lambda: {})())}
    px = list(im.convert("RGB").resize((WORK, WORK), resample).getdata())
    at = lambda x, y: px[y * WORK + x]  # noqa: E731
    ring = [at(x, y) for y in range(WORK) for x in range(WORK) if x < RING or y < RING or x >= WORK - RING or y >= WORK - RING]
    bg = tuple(int(statistics.median(c[i] for c in ring)) for i in range(3))
    dist = lambda c: max(abs(c[0] - bg[0]), abs(c[1] - bg[1]), abs(c[2] - bg[2]))  # noqa: E731
    out["bg_rgb"] = list(bg)
    out["bg_spread"] = round(sum(dist(c) for c in ring) / len(ring), 3)
    cols, rows, mask = [0] * WORK, [0] * WORK, [[False] * WORK for _ in range(WORK)]
    for y in range(WORK):
        for x in range(WORK):
            if dist(at(x, y)) > SUBJECT_DELTA:
                cols[x] += 1
                rows[y] += 1
                mask[y][x] = True
    xs, ys = [x for x in range(WORK) if cols[x] >= MIN_LINE], [y for y in range(WORK) if rows[y] >= MIN_LINE]
    band = round(WORK * .08)
    frame = [at(x, y) for y in range(WORK) for x in range(WORK) if x < band or y < band or x >= WORK - band or y >= WORK - band]
    out["frame_clean"] = round(sum(1 for c in frame if dist(c) <= SUBJECT_DELTA) / len(frame), 4)  # outer 8% still background-coloured
    if not xs or not ys:  # nothing differs from the background: an empty picture
        return {**out, "subject_found": False}
    x0, x1, y0, y1 = xs[0], xs[-1] + 1, ys[0], ys[-1] + 1
    area = sum(map(sum, mask))
    out["holes"], out["hole_area"] = _enclosed_patches(mask)
    subject = [at(x, y) for y in range(y0, y1) for x in range(x0, x1) if mask[y][x]]
    below = [_luma(bg) - _luma(at(x, y)) for y in range(y1, min(WORK, y1 + 10))
             for x in range(x0 + (x1 - x0) // 4, x1 - (x1 - x0) // 4) if not mask[y][x]]
    out.update(subject_found=True, fill_w=round((x1 - x0) / WORK, 4), fill_h=round((y1 - y0) / WORK, 4),
               fill_max=round(max(x1 - x0, y1 - y0) / WORK, 4), center_x=round((x0 + x1) / 2 / WORK - .5, 4),
               center_y=round((y0 + y1) / 2 / WORK - .5, 4), margin_top=round(y0 / WORK, 4),
               margin_bottom=round((WORK - y1) / WORK, 4), margin_left=round(x0 / WORK, 4),
               margin_right=round((WORK - x1) / WORK, 4), area_ratio=round(area / (WORK * WORK), 4),
               subject_luma=round(statistics.fmean(_luma(c) for c in subject), 2),
               subject_sat=round(statistics.fmean(_sat(c) for c in subject), 4),
               shadow_depth=round(statistics.fmean(below), 2) if below else None, bg_luma=round(_luma(bg), 2),
               corner_vs_edge=round(statistics.fmean(_luma(at(x, y)) for x, y in ((3, 3), (WORK - 4, 3), (3, WORK - 4), (WORK - 4, WORK - 4)))
                                    - statistics.fmean(_luma(at(x, y)) for x, y in ((WORK // 2, 3), (WORK // 2, WORK - 4), (3, WORK // 2), (WORK - 4, WORK // 2))), 2))
    return out


def open_image(data: bytes):
    Image, ImageOps = _pil()
    im = Image.open(io.BytesIO(data))
    im.load()
    return im, ImageOps


def measure_images(products, site=SITE) -> dict:
    """Per-metric percentiles over every active product picture, plus file facts and 12 real examples."""
    Image, _ = _pil()
    rows, sizes, fmts, modes, exif, names = [], Counter(), Counter(), Counter(), 0, Counter()
    for p in sorted(products, key=lambda r: r["id"]):
        if p.get("status") != "active": continue
        f = Path(site) / p["image"]
        data = f.read_bytes()
        im = Image.open(io.BytesIO(data))
        m = image_metrics(im)
        m.update(id=p["id"], bytes=len(data))
        rows.append(m)
        sizes[f"{im.width}x{im.height}"] += 1
        fmts[im.format] += 1
        modes[im.mode] += 1
        exif += m["has_exif"]
        names["catalog" if CATALOG_IMAGE_RE.fullmatch(p["image"]) else "owner" if OWNER_IMAGE_RE.fullmatch(p["image"]) else "other"] += 1
    keys = ("bg_spread", "fill_w", "fill_h", "fill_max", "center_x", "center_y", "margin_top", "margin_bottom", "margin_left",
            "margin_right", "area_ratio", "subject_luma", "subject_sat", "shadow_depth", "bg_luma", "corner_vs_edge", "frame_clean", "holes", "hole_area", "bytes")
    found = [r for r in rows if r.get("subject_found")]
    stats = {k: percentiles([r[k] for r in found if r.get(k) is not None]) for k in keys}
    stats["bg_r"], stats["bg_g"], stats["bg_b"] = (percentiles([r["bg_rgb"][i] for r in found]) for i in range(3))
    pick = [found[i * len(found) // 12] for i in range(12)]
    return {"count": len(rows), "sizes": dict(sizes), "formats": dict(fmts), "modes": dict(modes), "with_exif": exif,
            "naming": dict(names), "metrics": stats,
            "examples": [{k: r[k] for k in ("id", "fill_w", "fill_h", "center_x", "center_y", "shadow_depth", "bytes")}
                         | {"bg_rgb": r["bg_rgb"], "path": next(p["image"] for p in products if p["id"] == r["id"])} for r in pick]}


# ---------------------------------------------------------------- text
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"‘'])")


def sentences(text: str) -> list:
    return [s for s in _SENT_SPLIT.split(text.strip()) if s]


def _words(text: str) -> list:
    return re.findall(r"[\w’'-]+", text)


def description_metrics(text: str) -> dict:
    sents = sentences(text)
    first = _words(sents[0])[0].casefold() if sents and _words(sents[0]) else ""
    return {"chars": len(text), "words": len(_words(text)), "sentences": len(sents),
            "words_per_sentence": round(len(_words(text)) / max(1, len(sents)), 2),
            "colons": text.count(":"), "semicolons": text.count(";"), "dashes": text.count("—") + text.count("–"),
            "digits": sum(c.isdigit() for c in text), "exclaims": text.count("!"), "questions": text.count("?"),
            "curly_apostrophes": text.count("’"), "straight_apostrophes": text.count("'"),
            "non_bmp": sum(ord(c) > 0xFFFF for c in text), "first_word": first,
            "later_openers": [(_words(s)[0].casefold() if _words(s) else "") for s in sents[1:]],
            "ends_with_period": text.rstrip().endswith("."), "all_caps_words": sum(1 for w in _words(text) if len(w) >= 3 and w.isupper())}


def _text_stats(texts) -> dict:
    ms = [description_metrics(t) for t in texts]
    num = lambda k: percentiles([m[k] for m in ms])  # noqa: E731
    openers = Counter(w for m in ms for w in m["later_openers"] if w)
    firsts = Counter(m["first_word"] for m in ms)
    corpus = " ".join(texts)
    folded = claims.fold(corpus)
    return {"count": len(ms), "chars": num("chars"), "words": num("words"), "sentences": num("sentences"),
            "words_per_sentence": num("words_per_sentence"),
            "sentence_count_histogram": dict(sorted(Counter(m["sentences"] for m in ms).items())),
            "texts_with": {k: sum(1 for m in ms if m[k]) for k in ("colons", "semicolons", "dashes", "digits", "exclaims", "questions",
                                                                    "curly_apostrophes", "straight_apostrophes", "non_bmp", "all_caps_words")},
            "ends_with_period": sum(m["ends_with_period"] for m in ms),
            "common_first_words": firsts.most_common(15), "common_later_openers": openers.most_common(40),
            "hype_words_absent": [w for w in HYPE_SEED if not re.search(rf"(?<!\w){re.escape(w)}(?!\w)", folded)],
            "hype_words_present": [w for w in HYPE_SEED if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", folded)]}


def measure_descriptions(products, makers) -> dict:
    active = [p for p in products if p.get("status") == "active"]
    named = [p for p in active if p.get("producerKey")]
    unnamed = [p for p in active if not p.get("producerKey")]
    out = _text_stats([p["description"] for p in active])
    mention = lambda p: claims.fold(p["displayBrand"]) in claims.fold(p["description"])  # noqa: E731
    out["maker_named_in_description"] = {"products_with_maker": len(named), "mention_maker": sum(mention(p) for p in named),
                                         "products_without_maker": len(unnamed), "mention_brand_anyway": sum(mention(p) for p in unnamed)}
    out["term_hits"] = {t: sum(1 for p in active if claims._pattern(t).search(claims.fold(p["description"])))
                        for t in claims.TERMS + claims.FARM_TERMS + claims.HEALTH_AWARD_TERMS}
    out["examples"] = [{"id": p["id"], "name": p["name"], "category": p["category"], "description": p["description"]}
                       for p in (active[i * len(active) // 14] for i in range(14))]
    out["limit_chars"] = TEXT_LIMITS["product"]["description"]
    return out


def measure_makers(makers) -> dict:
    shown = {k: m for k, m in makers.items() if not m.get("hidden")}
    stories = [m["story"] for m in shown.values()]
    out = _text_stats(stories)
    out.update(count=len(shown), key_equals_name=sum(1 for k, m in shown.items() if k == m["name"]), with_url=sum(1 for m in shown.values() if m.get("url")),
               url_scheme_https=sum(1 for m in shown.values() if str(m.get("url", "")).startswith("https://")),
               places=Counter(m["place"] for m in shown.values()).most_common(30),
               place_pattern_fit=sum(1 for m in shown.values() if MAKER_PLACE_RE.fullmatch(m["place"])),
               name_chars=percentiles([len(m["name"]) for m in shown.values()]), place_chars=percentiles([len(m["place"]) for m in shown.values()]),
               limits=TEXT_LIMITS["maker"], fields=list(MAKER_FIELDS) + ["hidden (optional, true only)"])
    out["examples"] = [{"key": k, **{f: m.get(f) for f in MAKER_FIELDS}} for k, m in list(shown.items())[::2][:13]]
    return out


def measure_records(products, makers, store) -> dict:
    active = [p for p in products if p.get("status") == "active"]
    ids = [int(m.group(1)) for p in products if (m := re.fullmatch(r"photo-product-(\d+)", p["id"]))]
    brand_rule = Counter(("market" if p["brand"] == "Producer not identified" else "maker" if p.get("producerKey") else "own-brand")
                         + ":" + ("ok" if p["displayBrand"] == ("From the market" if p["brand"] == "Producer not identified" else p["brand"]) else "differs")
                         for p in active)
    return {"product_public_fields": list(PRODUCT_PUBLIC_FIELDS), "product_optional_public": list(PRODUCT_OPTIONAL_PUBLIC),
            "product_internal_fields": list(PRODUCT_INTERNAL_FIELDS), "categories": list(CATEGORIES), "shelf_labels": SHELF_LABELS,
            "products_per_shelf": dict(Counter(p["category"] for p in active)), "id_pattern": "photo-product-NNN (next = highest + 1)",
            "highest_id_number": max(ids), "key_orders": [list(k) for k, _ in Counter(tuple(p.keys()) for p in active).most_common(3)],
            "brand_rule_counts": dict(brand_rule), "unknown_producer": {"brand": "Producer not identified", "displayBrand": "From the market", "producerKey": None},
            "products_with_maker_key": sum(1 for p in active if p.get("producerKey")), "products_without_maker_key": sum(1 for p in active if not p.get("producerKey")),
            "name_chars": percentiles([len(p["name"]) for p in active]), "limits": TEXT_LIMITS["product"],
            "name_style": {"sentence_case": sum(1 for p in active if p["name"][:1].isupper()), "ends_with_period": sum(1 for p in active if p["name"].endswith("."))},
            "maker_fields": list(MAKER_FIELDS), "store_fields": sorted(store),
            "product_example": {k: v for k, v in next(p for p in active if p.get("producerKey")).items()},
            "maker_example": {"key": next(iter(makers)), **next(iter(makers.values()))}}


def build_spec(root=REPO_ROOT) -> dict:
    root = Path(root)
    content = load_content(root / "hass" / "content")
    prod, makers = content.products, content.makers
    return {"schema": 1, "source": "measured from hass/content/*.json and storefront-mockup/assets/products/ by hass/house_style.py measure",
            "pictures": {"catalog": measure_images(prod, root / "storefront-mockup"),
                         "frame": {"width": 800, "height": 800, "aspect": 1.0, "format_catalog": "WEBP (quality ~84, sharp fit inside 800x800)",
                                   "format_owner_photo": "JPEG or PNG named photo-<16 hex>.<ext> (the only names shop.js treats as an owner photo)",
                                   "page_box": "square (aspect-ratio 1), object-fit contain, page colour #f5f0e6 behind the picture",
                                   "alt_text": {"catalog_illustration": "<product name> (illustration), added by shop.js",
                                                "owner_photo": "imageAlt as written, no suffix; names what the photo shows, 3..200 chars, not a file name"},
                                   "look": "one real product or group, large and centred on a smooth warm-ivory seamless background, soft diffuse top-left light, "
                                           "soft contact shadow, true packaging and label colours, no props, hands, text overlays, prices or borders"}},
            "descriptions": measure_descriptions(prod, makers), "makers": measure_makers(makers),
            "records": measure_records(prod, makers, content.store)}


# ---------------------------------------------------------------- spec io
def load_spec(path=SPEC_PATH) -> dict:
    return json.loads(Path(path).read_text("utf-8"))


def _dump(spec) -> str:
    return json.dumps(spec, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


# ---------------------------------------------------------------- scoring
def _result(checks) -> dict:
    total = sum(c["weight"] for c in checks)
    got = sum(c["weight"] for c in checks if c["ok"])
    score = round(100 * got / total) if total else 0
    hard = [c["name"] for c in checks if c["hard"] and not c["ok"]]
    return {"score": score, "pass": not hard and score >= 80, "hard_failures": hard, "checks": checks}


def _c(name, ok, detail, weight=1, hard=False) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail, "weight": weight, "hard": hard}


def _within(value, stat, slack=0.0, scale=0.0):
    """value inside [p05, p95] widened by an absolute slack and a fraction of the range (the spread of real items)."""
    lo, hi = stat["p05"], stat["p95"]
    pad = slack + scale * (hi - lo)
    return value is not None and lo - pad <= value <= hi + pad


def check_image(data: bytes, spec=None, *, enclosed_background=None) -> dict:
    """Score picture bytes (JPEG/PNG/WEBP) against the measured catalog look.

    ``enclosed_background`` is the renderer's own measure (share of its analysis frame) of the enclosed pockets of its
    cut-out it could not show to be product (a pocket is product only when printed and off the background plane).
    ``None`` (any picture we did not cut out ourselves) keeps the full check. When it is 0, every ivory-coloured patch
    inside the product is a printed label, so only the patch count limit applies."""
    spec = spec or load_spec()
    m_spec = spec["pictures"]["catalog"]["metrics"]
    im, _ = open_image(data)
    fmt = im.format
    m = image_metrics(im)
    product_only = enclosed_background is not None and enclosed_background == 0
    checks = [_c("size 800x800", (m["width"], m["height"]) == (800, 800), f"{m['width']}x{m['height']}", 3, True),
              _c("mode RGB", m["mode"] == "RGB", m["mode"], 1, True),
              _c("format webp/jpeg/png", fmt in ("WEBP", "JPEG", "PNG"), fmt, 1, True),
              _c("no metadata (EXIF/GPS)", not m["has_exif"], "EXIF present" if m["has_exif"] else "none", 2, True)]
    if not m["subject_found"]:
        return _result(checks + [_c("subject visible", False, "nothing differs from the background", 3, True)])
    bg = m["bg_rgb"]
    checks += [
        _c("background colour (warm ivory)", all(m_spec[f"bg_{'rgb'[i]}"]["min"] - 6 <= bg[i] <= m_spec[f"bg_{'rgb'[i]}"]["max"] + 6 for i in range(3)), f"rgb{tuple(bg)}", 4, True),
        _c("background even", m["bg_spread"] <= m_spec["bg_spread"]["p95"] * 1.5 + 1, f"spread {m['bg_spread']}", 2),
        _c("clean ivory around the product (no photo background left)", m["frame_clean"] >= m_spec["frame_clean"]["min"] * .97,
           f"{m['frame_clean']:.2f} of the outer frame (catalog lowest {m_spec['frame_clean']['min']:.2f})", 3, True),
        _c("no photo background left inside the product (patterned cloth, planks)", m["holes"] <= m_spec["holes"]["max"] + 6 and (product_only or m["hole_area"] <= m_spec["hole_area"]["max"] * 1.5),
           f"{m['holes']} background patches covering {m['hole_area']:.3f} (catalog most {m_spec['holes']['max']:.0f}, {m_spec['hole_area']['max']:.3f})"
           + ("; the cut-out shows them as product, not photo background" if product_only else ""), 3, True),
        _c("subject size in frame", _within(m["fill_max"], m_spec["fill_max"], scale=.25) and m["fill_max"] <= 1.0, f"{m['fill_max']:.2f} of the frame", 3),
        _c("subject area", m_spec["area_ratio"]["min"] * .85 <= m["area_ratio"] <= m_spec["area_ratio"]["max"] * 1.1, f"{m['area_ratio']:.2f} of the frame", 2),
        _c("centred sideways", abs(m["center_x"]) <= m_spec["center_x"]["p95"] + .04, f"{m['center_x']:+.3f}", 2),
        _c("centred up/down", _within(m["center_y"], m_spec["center_y"], slack=.04), f"{m['center_y']:+.3f}", 2),
        _c("room below subject", m["margin_bottom"] >= m_spec["margin_bottom"]["p05"] * .5, f"{m['margin_bottom']:.3f}", 1),
        _c("soft shadow under subject", m["shadow_depth"] is not None and _within(m["shadow_depth"], m_spec["shadow_depth"], slack=3, scale=.5),
           f"{m['shadow_depth']}", 2),
        _c("brightness of subject", _within(m["subject_luma"], m_spec["subject_luma"], scale=.25), f"{m['subject_luma']}", 1),
        _c("colour strength of subject", _within(m["subject_sat"], m_spec["subject_sat"], scale=.25), f"{m['subject_sat']}", 1),
        _c("file size", len(data) <= m_spec["bytes"]["p95"] * 1.6, f"{len(data)} bytes", 1)]
    return _result(checks)


def _has_term(text: str, term: str) -> bool:
    return bool(claims._pattern(term).search(claims.fold(text)))


def check_description(text: str, spec=None, *, name=None, maker_name=None, owner_text="") -> dict:  # name/maker_name: kept for callers; the house voice does not require either
    """Score a product description against the measured voice. A claim term (organic, local, estate ...) passes only when
    the owner's own words (``owner_text``) contain it, the same rule as hass/claims.py."""
    spec = spec or load_spec()
    d = spec["descriptions"]
    m = description_metrics(text)
    owner = "\n".join(claims.fold(line) for line in str(owner_text or "").splitlines())  # same projection as claims.unstated: fold() collapses newlines, which are clause breaks
    terms = [t for t in claims.TERMS + claims.FARM_TERMS + claims.HEALTH_AWARD_TERMS if _has_term(text, t) and not claims._affirmed(claims._pattern(t), owner)]
    hype = [w for w in d["hype_words_absent"] if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", claims.fold(text))]
    bad_text = [b for b in FORBIDDEN_TEXT if b in text]
    checks = [
        _c("plain text, no $ < > {{ }}", not bad_text, f"found {bad_text}" if bad_text else "ok", 3, True),
        _c("within the 600 character limit", m["chars"] <= d["limit_chars"] and text == text.strip(), f"{m['chars']} chars", 3, True),
        _c("no unstated claim term", not terms, f"unstated: {terms}" if terms else "none", 4, True),
        _c("no price or number", m["digits"] == 0 or d["texts_with"]["digits"] > 0, f"{m['digits']} digits", 2, d["texts_with"]["digits"] == 0),
        _c("no hype words", not hype, f"{hype}" if hype else "none", 2),
        _c("length like the others", d["chars"]["min"] * .9 <= m["chars"] <= d["chars"]["max"] * 1.25, f"{m['chars']} chars (usual {d['chars']['p05']:.0f}-{d['chars']['p95']:.0f})", 3, True),
        _c("sentence count like the others", d["sentences"]["min"] <= m["sentences"] <= d["sentences"]["max"], f"{m['sentences']} sentences", 2, True),
        _c("sentence length like the others", d["words_per_sentence"]["min"] * .8 <= m["words_per_sentence"] <= d["words_per_sentence"]["max"] * 1.3,
           f"{m['words_per_sentence']} words each", 1),
        _c("no exclamation or question marks", not (m["exclaims"] or m["questions"]) or d["texts_with"]["exclaims"] + d["texts_with"]["questions"] > 0,
           f"{m['exclaims']} ! {m['questions']} ?", 2),
        _c("no emoji or ALL CAPS shouting", not m["non_bmp"] and not m["all_caps_words"], "ok", 1),
        _c("ends with a full stop", m["ends_with_period"], "ok" if m["ends_with_period"] else "no full stop", 1),
        _c("curly apostrophes like the others", not m["straight_apostrophes"] or d["texts_with"]["straight_apostrophes"] > 0.3 * d["count"], f"{m['straight_apostrophes']} straight", 1)]
    return _result(checks)


def check_maker(rec: dict, spec=None, *, key=None) -> dict:
    spec = spec or load_spec()
    mk = spec["makers"]
    # Text fields are validated as the ORIGINAL values with the content validator (blank, outer space, control/invisible,
    # forbidden text, over-limit, nonstring all fail); measurements use a local string, empty for a nonstring/missing value.
    text_problems: list = []
    for field in ("name", "place", "story"):
        _text(text_problems, field, rec.get(field), limit=TEXT_LIMITS["maker"][field])
    name, place, story = (rec[f] if isinstance(rec.get(f), str) else "" for f in ("name", "place", "story"))
    m = description_metrics(story) if story else {"sentences": 0, "chars": 0}
    fields_ok = set(rec) - {"hidden"} <= set(MAKER_FIELDS) and {"name", "place", "story"} <= set(rec)
    url = rec.get("url")
    url_problems: list = []  # absent is fine; a present value (even null) gets the content validator's full public-https test
    if "url" in rec:
        _https(url_problems, "url", url)
    checks = [_c("fields name, place, story (+url)", fields_ok, sorted(rec), 3, True),
              _c("plain text", not text_problems, "invalid maker text" if text_problems else "ok", 2, True),
              _c("limits", len(name) <= 80 and len(place) <= 60 and m["chars"] <= 600, f"story {m['chars']} chars", 2, True),
              _c("url is public https or absent", not url_problems, str(url), 2, True),
              _c("place like 'Town, California'", bool(MAKER_PLACE_RE.fullmatch(place)), place, 2),
              _c("key equals name", key is None or key == rec.get("name"), str(key), 1),
              _c("story length like the others", mk["chars"]["p05"] * .35 <= m["chars"] <= mk["chars"]["p95"] * 1.25,
                 f"{m['chars']} chars (usual {mk['chars']['p05']:.0f}-{mk['chars']['p95']:.0f})", 1),
              _c("story ends with a full stop", story.rstrip().endswith("."), "ok", 1)]
    return _result(checks)


def check_product(rec: dict, makers: dict, spec=None) -> dict:
    """Shape of one product record: fields, id, shelf, brand rules, maker link and picture path."""
    spec = spec or load_spec()
    need = {"id", "name", "brand", "category", "image", "description", "producerKey", "displayBrand", "status"}
    allowed = set(PRODUCT_PUBLIC_FIELDS) | set(PRODUCT_OPTIONAL_PUBLIC) | set(PRODUCT_INTERNAL_FIELDS)
    key = rec.get("producerKey")
    unknown = rec.get("brand") == "Producer not identified"
    shown_ok = rec.get("displayBrand") == ("From the market" if unknown else rec.get("brand"))
    img = rec.get("image", "")
    pid = rec.get("id", "")  # nontext ids fail the id check instead of raising in re.fullmatch
    text_problems: list = []  # same validator the content loader uses; never raises on odd value types
    for field in ("name", "brand"):
        _text(text_problems, field, rec.get(field), limit=TEXT_LIMITS["product"][field])
    checks = [_c("fields", need <= set(rec) <= allowed, sorted(set(rec) ^ need), 3, True),
              _c("shelf is one of the nine", rec.get("category") in CATEGORIES, str(rec.get("category")), 3, True),
              _c("id photo-product-NNN", isinstance(pid, str) and re.fullmatch(r"photo-product-\d{3,}", pid) is not None, pid, 1),
              _c("displayBrand follows brand", shown_ok, f"{rec.get('brand')} -> {rec.get('displayBrand')}", 2),
              _c("maker link", key is None or (isinstance(key, str) and key in makers), str(key), 3, True),  # nontext keys fail, never hashed
              _c("unknown producer has no maker key", not (unknown and key), str(key), 1),
              _c("picture path", isinstance(img, str) and bool(CATALOG_IMAGE_RE.fullmatch(img) or OWNER_IMAGE_RE.fullmatch(img)), img, 2, True),
              _c("name and brand text", not text_problems, "invalid name or brand" if text_problems else "ok", 1, True)]
    return _result(checks)


# ---------------------------------------------------------------- cli
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="hass/house_style.py", description="Measure and check the Avocado Shack house style.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("measure").add_argument("--out", help="write the spec here (default: print to stdout)")
    sub.add_parser("verify", help="exit 1 when the committed spec no longer matches the content")
    sub.add_parser("check-image").add_argument("file")
    t = sub.add_parser("check-text")
    t.add_argument("text")
    t.add_argument("--owner", default="")
    a = ap.parse_args(argv)
    if a.cmd == "measure":
        text = _dump(build_spec())
        if a.out: Path(a.out).write_text(text, "utf-8")
        else: sys.stdout.write(text)
        return 0
    if a.cmd == "verify":
        same = _dump(build_spec()) == SPEC_PATH.read_text("utf-8")
        print("house-style.json matches the content" if same else "house-style.json is out of date: run measure --out")
        return 0 if same else 1
    if a.cmd == "check-image":
        try: out = check_image(Path(a.file).read_bytes())
        except (OSError, PillowMissing):  # unreadable/undecodable picture or no Pillow: fixed, path-free, no score
            sys.stderr.write("house_style: image could not be checked\n")
            return 2
    else:
        out = check_description(a.text, owner_text=a.owner)
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
