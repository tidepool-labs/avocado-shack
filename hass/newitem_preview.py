"""HASS-NEWITEM-1 (Part B evidence): an OFFLINE browser preview of a new-item draft next to existing shelf cards.

``python3 hass/newitem_preview.py`` (needs Pillow, node, Playwright: set PLAYWRIGHT_MODULE=<playwright folder>, optionally CHROMIUM_PATH)
runs the synthetic cases through ``newitem.draft`` and, for each, shows two shelf pages in headless Chromium (phone 390 px and
desktop 1280 px) built by the shop's own pipeline:

* BEFORE: what the shop would show today for the same message and photo: the photo with its metadata taken off
  (``media._jpeg_copy``, the existing web copy), Michael's words as the description, no maker entry.
* AFTER: the draft: the house-style render, the house-voice description, alt text, the maker entry, the shelf and the availability word.

How it uses the existing machinery (nothing is invented here): the draft's typed ops are applied to an in-memory copy of the
catalog by the REAL op handlers (hass.ops.catalog ``_maker_add`` / ``_product_add`` / ``_product_set_availability``; the stored-photo
step, ``photos.install``, is replaced by the picture's own path because there is no media store in an offline run); the site files
come from ``sitegen.render``; ``hass.preview.Previewer`` copies the tracked site, lays the generated files and the picture over it,
serves it on 127.0.0.1 with an empty throwaway database and runs ``hass/newitem_screenshot.cjs`` (only GET/HEAD to that origin).
That script types a search into the page's own box so the new card appears with two existing cards, opens their maker notes,
screenshots the three together and checks the new card against its neighbours (same picture box, same type, same width, text and
picture as drafted). Nothing is published, sent, written to the live site or kept outside reports/hass/newitem-1/preview/.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import house_style as hs, newitem, preview, sitegen  # noqa: E402
from hass.content_model import REPO_ROOT, SHOP_TZ, load_content, shop_today  # noqa: E402
from hass.ops import Refused, catalog  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "newitem_screenshot.cjs"
OUT = REPO_ROOT / "reports" / "hass" / "newitem-1" / "preview"
HANDLERS = {"maker.add": catalog._maker_add, "product.add": catalog._product_add, "product.set_availability": catalog._product_set_availability}
CASES = {  # name -> (search term typed in the page, message, Michael's one-line answer to the single question, if Hass asks one)
    "jar-white-sheet": ("honey", "got in some Cal Poly honey, jar of 8oz, $9", ""),
    "bottle-grey-wall-tilted": ("hot sauce", "Just got in wildflower hot sauce from Bee Happy Farm in Templeton, California. Great on eggs. "
                                             "They grow the peppers themselves. 6oz bottle $8", ""),
    "bag-bench-small": ("coffee", "got in some coffee from Roast Bros in Cambria, California.", "It goes on the drinks shelf.")}


def apply_in_memory(content, ops, image_path, now):
    """A copy of the catalog with the draft's ops applied by the real op handlers; (content, the new product record)."""
    cp, ctx, created = copy.deepcopy(content), SimpleNamespace(now=now, warnings=[]), []
    cp.store["selection_checked_on"] = shop_today(now).isoformat()  # the day's shelf check, so the availability word may show
    for op in ops:
        args = dict(op["args"])
        if op["op"] == "product.add":
            args.pop("photo", None)
            args["image"] = image_path
        out = HANDLERS[op["op"]](cp, args, ctx)
        if isinstance(out, Refused): raise RuntimeError(f"{op['op']} refused: {out}")
        if op["op"] == "product.add": created += [t.key for t in out if t.collection == "products" and t.before is None]
    if len(created) != 1: raise RuntimeError(f"expected exactly one product.add creation, got {len(created)}")
    return cp, next(p for p in cp.products if p["id"] == created[0])  # by the created id: older products may share the image


def before_ops(draft_result, message):
    """What exists today for the same item: the same name and shelf, Michael's own words, no maker entry, no alt text."""
    args = draft_result["ops"][-1 if draft_result["ops"][-1]["op"] == "product.add" else -2]["args"]
    return [{"op": "product.add", "args": {"name": args["name"], "brand": "Producer not identified", "category": args["category"],
                                           "description": message, "photo": args["photo"], "imageAlt": args["name"]}}]


def capture_case(name, term, message, answer, photo, content, spec, env, viewports=("phone", "desktop")):
    """{"before": {...}, "after": {...}, ...} with png paths and the browser's own check results. If Hass asks its one question,
    Michael's one-line answer is added to his message and the draft is made again, as the conversation would."""
    from hass import newitem_render  # noqa: PLC0415 - Pillow
    from hass import media  # noqa: PLC0415
    now = datetime.now(SHOP_TZ)
    first = newitem.draft(message, photo, content=content, spec=spec, selection_checked=True, renderer=newitem_render.render)
    question = first["question"] if first["status"] == "question" else None
    if question:
        message = f"{message} {answer}"
    result = newitem.draft(message, photo, content=content, spec=spec, selection_checked=True, renderer=newitem_render.render)
    assert result["status"] in ("draft", "draft-with-warnings"), result
    after_path = result["image"]["path"]
    web, _removed = media._jpeg_copy(photo) if photo[:2] == b"\xff\xd8" else media._png_copy(photo)
    ext = "jpg" if photo[:2] == b"\xff\xd8" else "png"
    before_sha = hashlib.sha256(web).hexdigest()
    before_path = f"assets/products/photo-{before_sha[:16]}.{ext}"
    runs = {}
    for side, ops, path, picture in (("before", before_ops(result, message), before_path, web), ("after", result["ops"], after_path, result["image"]["bytes"])):
        after_content, product = apply_in_memory(content, ops, path, now)
        files = sitegen.render(after_content, today=shop_today(now))
        maker = after_content.makers.get(product.get("producerKey") or "", None)
        target = {"kind": "compare", "id": product["id"], "term": term, "name": product["name"], "description": product["description"],
                  "alt": product.get("imageAlt"), "image": path, **({"maker": product["displayBrand"], "makerStory": maker["story"]} if maker else {}),
                  "availability": sitegen.availability_label(product, after_content.store, shop_today(now))}
        target = {k: v for k, v in target.items() if v is not None or k == "availability"}
        out_png = OUT / f"{name}-{side}.png"
        old = preview.SCRIPT
        preview.SCRIPT = SCRIPT
        try:
            shot = preview.Previewer(REPO_ROOT, env=env, viewports=viewports).capture(
                files, target, out_png, assets={f"storefront-mockup/{path}": picture})
        finally:
            preview.SCRIPT = old
        runs[side] = {"ok": shot["ok"], "error": shot["error"], "checks": shot["checks"], "phone": out_png.name if shot.get("png") else None,
                      "desktop": Path(shot["desktopPng"]).name if shot.get("desktopPng") else None, "description": product["description"],
                      "name": product["name"], "brand": product["displayBrand"], "shelf": product["category"], "availability": target["availability"]}
    return {**runs, "draft_status": result["status"], "draft_reply": result["reply"], "message": message, "question_asked": question}


def squeeze(path: Path) -> None:
    """Keep the committed captures small: a 256-colour PNG is plenty for a flat web page (the browser's own pixels, only fewer colours)."""
    from PIL import Image  # noqa: PLC0415
    im = Image.open(path).convert("RGB")
    im.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)


def main() -> int:
    from hass import newitem_synthetic as syn  # noqa: PLC0415
    env = dict(os.environ)
    if not env.get("PLAYWRIGHT_MODULE"):
        print("set PLAYWRIGHT_MODULE to the playwright folder (and CHROMIUM_PATH if needed)", file=sys.stderr)
        return 2
    content, spec = load_content(), hs.load_spec()
    OUT.mkdir(parents=True, exist_ok=True)
    kw = dict(syn.cases())
    summary = {}
    for name, (term, message, answer) in CASES.items():
        photo = syn.make_photo(**kw[name])
        summary[name] = capture_case(name, term, message, answer, photo, content, spec, env)
        for side in ("before", "after"):
            run = summary[name][side]
            for key in ("phone", "desktop"):
                if run.get(key): squeeze(OUT / run[key])
            print(name, side, "ok" if run["ok"] else "NOT OK: " + str(run["error"]))
    # the committed JSON never holds the machine's paths or a time; only names, checks and the draft's words
    (OUT / "preview.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, sort_keys=True) + "\n", "utf-8")
    return 0 if all(summary[n][side]["ok"] for n in summary for side in ("before", "after")) else 1


if __name__ == "__main__":
    sys.exit(main())
