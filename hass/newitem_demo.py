"""HASS-NEWITEM-1 demo: synthetic photos -> house-style renders -> a before/after sheet next to real catalog pictures.

Writes into reports/hass/newitem-1/: synthetic/<case>.{jpg,png} (the made-up photos), rendered/<case>.jpg, drafts.json (the
draft for each message) and before-after.png. "Before" is what the site would show today for an owner photo: the metadata-
stripped original, fitted in the page's square box on #f5f0e6 (shop.js/style.css: aspect-ratio 1, object-fit contain).
The sheet is supplementary offline evidence, not the real-renderer product gallery.
Run: python3 hass/newitem_demo.py
"""
import io
import json
import sys
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageOps  # noqa: E402

from hass import house_style as hs, newitem, newitem_render, newitem_synthetic as syn  # noqa: E402
from hass.content_model import REPO_ROOT, load_content  # noqa: E402

OUT = REPO_ROOT / "reports" / "hass" / "newitem-1"
PAGE = (245, 240, 230)  # #f5f0e6
TILE = 260
SHOW = ("jar-white-sheet", "bottle-grey-wall-tilted", "jar-phone-rotated", "bag-bench-small", "jar-dark-wood", "bag-red-cloth")
MESSAGES = {"jar-white-sheet": "got in some Cal Poly honey, jar of 8oz, $9",
            "bottle-grey-wall-tilted": "Just got in wildflower hot sauce from Bee Happy Farm in Templeton, California. Great on eggs. They grow the peppers themselves. 6oz bottle $8",
            "bag-bench-small": "got in some coffee from Roast Bros in Cambria, California"}


def _on_page(img):
    """EXIF-transpose, then composite any transparency once over PAGE (not hidden RGB); opaque images convert directly."""
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
        rgba = img.convert("RGBA")
        return Image.alpha_composite(Image.new("RGBA", rgba.size, PAGE + (255,)), rgba).convert("RGB")
    return img.convert("RGB")


def tile(img, label):
    return _page_tile(_on_page(img), label)


def _page_tile(img, label):
    box = Image.new("RGB", (TILE, TILE + 22), PAGE)
    img.thumbnail((TILE, TILE))
    box.paste(img, ((TILE - img.width) // 2, (TILE - img.height) // 2))
    ImageDraw.Draw(box).text((6, TILE + 6), label, fill=(60, 50, 40))
    return box


def _catalog_tile(path, label, unavailable):
    try:
        with Image.open(path) as source:
            img = _on_page(source)  # Pillow decodes lazily; keep that inside the I/O boundary.
    except OSError:
        return unavailable
    return _page_tile(img, label)


def main() -> int:
    content, spec = load_content(), hs.load_spec()
    for sub in ("synthetic", "rendered"): (OUT / sub).mkdir(parents=True, exist_ok=True)
    drafts, rows = {}, []
    catalog = [p for p in content.active_products() if p["category"] == "pantry"][::12][:2]
    refs = None
    for name, kw in syn.cases():
        data = syn.make_photo(**kw)
        (OUT / "synthetic" / f"{name}.{'png' if kw.get('fmt') == 'PNG' else 'jpg'}").write_bytes(data)
        out = newitem_render.render(data, spec)
        (OUT / "rendered" / f"{name}.jpg").write_bytes(out["jpeg"])
        drafts[name] = {"render": out["report"], "check": {"score": out["check"]["score"], "pass": out["check"]["pass"], "failed": [c["name"] for c in out["check"]["checks"] if not c["ok"]]}}
        if name in MESSAGES:
            d = newitem.draft(MESSAGES[name], data, content=content, spec=spec, selection_checked=True)
            drafts[name]["draft"] = {k: d[k] for k in ("status", "question", "ops", "left_off", "reply", "alt") if k in d}
        if name in SHOW:
            if refs is None:
                unavailable = _page_tile(Image.new("RGB", (TILE, TILE), PAGE), "catalog: unavailable")
                refs = [_catalog_tile(hs.SITE / p["image"], "catalog: " + p["name"][:26], unavailable) for p in catalog]
                refs += [unavailable] * (2 - len(refs))  # keep BEFORE/AFTER in columns 3/4
            before = Image.new("RGB", (TILE, TILE), PAGE)  # the page box: square, contain
            raw = _on_page(Image.open(io.BytesIO(data)))
            raw.thumbnail((TILE, TILE))
            before.paste(raw, ((TILE - raw.width) // 2, (TILE - raw.height) // 2))

            rows.append(refs
                        + [tile(before, f"BEFORE: {name[:24]}"), tile(Image.open(io.BytesIO(out["jpeg"])), f"AFTER ({out['report']['isolation']}, {out['check']['score']})")])
    sheet = Image.new("RGB", (4 * TILE, len(rows) * (TILE + 22)), (255, 255, 255))
    for r, row in enumerate(rows):
        for c, t in enumerate(row): sheet.paste(t, (c * TILE, r * (TILE + 22)))
    sheet.save(OUT / "before-after.png")
    (OUT / "drafts.json").write_text(json.dumps(drafts, indent=1, ensure_ascii=False, default=str) + "\n", "utf-8")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
