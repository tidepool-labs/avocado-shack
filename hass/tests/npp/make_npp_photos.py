"""HASS-NPP-A: draw the synthetic owner photos, deliberate bad picture edits and good picture edits the NPP eval cases use.

    python3 hass/tests/npp/make_npp_photos.py [OUT_DIR]            write photos/ and edits/ under OUT_DIR
    python3 hass/tests/npp/make_npp_photos.py --verify-gate        also run photo_polish.gate on the good and bad edits (needs tesseract)

Writes into hass/tests/npp/cases/ (or OUT_DIR): ``photos/*.jpg`` (owner photos), ``edits/*.png`` (stand-ins for the taped
gpt-image-2 answers). Deterministic: a fixed seed and the same Pillow version give the same bytes, and the committed
copies are what the recorded tapes are made from, so re-running only matters when adding a photo.

* The twelve golden photos are the live gallery's own product pictures (storefront-mockup/assets/products, public site
  assets, product only) cut out and pasted onto a cluttered phone-like background. Their good edit is the gallery
  picture itself, so no copy is stored (the cases name it as ``gallery:<id>``).
* Every other product is drawn here (Pillow only): no real product, no person, no chat. The one phone-screen photo
  (case 28b) shows a drawn screen with generic chat bubbles of invented words.
* ``edits/<name>-good.png`` is the same drawn product on the warm ivory background; ``-bad-relabel`` paints a different
  brand over the label and ``-bad-recolour`` swaps the product's colours (the HASS-IMAGE-1 T3 deliberate-bad classes), so
  the real fidelity gate has something to reject.
"""
import argparse
import random
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DEFAULT_OUT = HERE / "cases"
GALLERY = ROOT / "storefront-mockup" / "assets" / "products"
GOLDEN_IDS = ("018", "024", "025", "015", "002", "042", "044", "052", "138", "021", "007", "006")  # case 1..12 order
IVORY = (245, 240, 230)  # the edit prompt's background, about RGB 245 240 230
SIZE = 640
SEED = 20261118


def canvas(bg, size=SIZE):
    return Image.new("RGB", (size, size), bg)


FONT = ImageFont.load_default(size=24)  # large enough that tesseract reads the label the way a phone photo would


def text_block(pen, x, y, lines, fill="#111111", step=28):
    for i, line in enumerate(lines):
        pen.text((x, y + i * step), line, fill=fill, font=FONT, stroke_width=1, stroke_fill=fill)


# ----------------------------------------------------------------------------------------------------- products
# Each product draws itself on a canvas that already holds its background. PRODUCTS gives the label box (relabel edit).
def honey(im):  # a glass jar of honey: invented brand
    pen = ImageDraw.Draw(im)
    pen.rectangle((180, 200, 460, 560), fill="#d88a12", outline="#6b4206", width=4)
    pen.rectangle((170, 160, 470, 210), fill="#3a3a3a")
    pen.rectangle((205, 270, 435, 480), fill="#fbf6ee")
    text_block(pen, 222, 285, ["SALT FLAT", "HONEY", "Wildflower", "Net wt 12 oz"])


def elderberry(im):  # a syrup whose label carries a health claim
    pen = ImageDraw.Draw(im)
    pen.rectangle((190, 190, 450, 570), fill="#3b1c3f", outline="#1b0a1d", width=4)
    pen.rectangle((260, 120, 380, 195), fill="#2a2a2a")
    pen.rectangle((205, 260, 435, 500), fill="#f3eadf")
    text_block(pen, 218, 272, ["BRAMBLE", "ELDERBERRY", "SYRUP", "immune support", "4 fl oz"])


def coffee(im):  # a coffee bag
    pen = ImageDraw.Draw(im)
    pen.polygon([(180, 130), (460, 130), (480, 570), (160, 570)], fill="#5a3a22", outline="#2b190b")
    pen.rectangle((195, 120, 445, 150), fill="#d9c9a8")
    pen.rectangle((200, 250, 440, 470), fill="#f2e8d5")
    text_block(pen, 214, 268, ["RIDGE ROAST", "Dark roast", "whole beans", "12 oz"])


def coffee_size(im):  # independent net-weight evidence for the equal-value case
    coffee(im)
    pen = ImageDraw.Draw(im)
    pen.rectangle((207, 351, 431, 459), fill="#f2e8d5")
    font = ImageFont.load_default(size=52)
    pen.text((214, 359), "12", fill="#111111", font=font)
    pen.text((299, 359), "OZ", fill="#111111", font=font)


def figs(im):  # dried figs in a pouch for the maker-research cases
    pen = ImageDraw.Draw(im)
    pen.polygon([(180, 150), (460, 150), (480, 570), (160, 570)], fill="#7b8f4e", outline="#3b4a1f")
    pen.rectangle((195, 140, 445, 170), fill="#e6dcc0")
    pen.rectangle((205, 270, 435, 470), fill="#f7f1e2")
    text_block(pen, 222, 290, ["MINERS", "Dried Figs", "Net wt 8 oz"])


def jam_back(im):  # the back of a jam jar: small print, no price
    pen = ImageDraw.Draw(im)
    pen.rectangle((170, 200, 470, 580), fill="#7a1230", outline="#3a0a18", width=4)
    pen.rectangle((160, 160, 480, 210), fill="#c9a24a")
    pen.rectangle((190, 240, 450, 550), fill="#fbf6ee")
    text_block(pen, 200, 252, ["INGREDIENTS:", "raspberries,", "sugar, lemon", "juice, pectin", "", "Keep chilled", "after opening", "", "Hillside Kitchen"])


def clean_jar(im):  # a plain jar of preserves for the clean house-render case
    pen = ImageDraw.Draw(im)
    pen.rectangle((180, 200, 460, 560), fill="#a3213b", outline="#4a0d1a", width=4)
    pen.rectangle((170, 160, 470, 210), fill="#caa24a")
    pen.rectangle((205, 280, 435, 480), fill="#fbf6ee")
    text_block(pen, 220, 300, ["QUARRY LANE", "Plum", "Preserves", "Net wt 9 oz"])


PRODUCTS = {"honey": (honey, (205, 270, 435, 480)), "elderberry": (elderberry, (205, 260, 435, 500)),
            "coffee": (coffee, (200, 250, 440, 470)), "figs": (figs, (205, 270, 435, 470)),
            "jam-back": (jam_back, (190, 240, 450, 550)), "clean-jar": (clean_jar, (205, 280, 435, 480))}


# ------------------------------------------------------------------------------------------------ backgrounds
def clutter(rng, size=SIZE):
    """A messy counter: planks, a cloth, a few random objects. Busy on purpose; no text, no person."""
    im = canvas((rng.randint(150, 190), rng.randint(120, 150), rng.randint(90, 120)), size)
    pen = ImageDraw.Draw(im)
    for y in range(0, size, 34):
        shade = rng.randint(-14, 14)
        pen.rectangle((0, y, size, y + 31), fill=(140 + shade, 108 + shade, 76 + shade))
    for _ in range(9):
        x, y = rng.randint(0, size - 90), rng.randint(0, size - 90)
        w, h = rng.randint(40, 150), rng.randint(30, 120)
        colour = tuple(rng.randint(40, 230) for _ in range(3))
        if rng.random() < .5:
            pen.rectangle((x, y, x + w, y + h), fill=colour)
        else:
            pen.ellipse((x, y, x + w, y + h), fill=colour)
    return im.filter(ImageFilter.GaussianBlur(1.2))


def busy_cloth(size=SIZE):
    """A strongly patterned cloth: the 'busy' retake defect when the polish is off."""
    im = canvas("#e8e2d6", size)
    pen = ImageDraw.Draw(im)
    for y in range(0, size, 40):
        for x in range(0, size, 40):
            if (x // 40 + y // 40) % 2:
                pen.rectangle((x, y, x + 39, y + 39), fill="#b5382e" if (x // 40) % 3 else "#2f5d8a")
    return im


def plain_counter(size=SIZE):
    return canvas("#e9e4da", size)


def photo(name, background):
    im = background
    PRODUCTS[name][0](im)
    return im


# ------------------------------------------------------------------------------------------- special photos
def sticker_photo(rng):  # 28a: a cost-like sticker on the product
    im = photo("honey", plain_counter())
    pen = ImageDraw.Draw(im)
    pen.rectangle((330, 500, 430, 545), fill="#ffe14a", outline="#b08d00", width=2)
    pen.text((344, 510), "$3.25", fill="#111111", font=FONT)
    return im


def screen_photo(rng):  # 28b: a phone screen in the frame, with invented chat words
    im = canvas("#cfd6dd")
    pen = ImageDraw.Draw(im)
    pen.rounded_rectangle((120, 40, 520, 600), radius=34, fill="#161616")
    pen.rectangle((140, 90, 500, 560), fill="#f4f6f8")
    for i, (side, words) in enumerate([("l", "hello there"), ("r", "sounds good"), ("l", "see you soon")]):
        y = 120 + i * 120
        x0, x1 = (155, 330) if side == "l" else (300, 485)
        pen.rounded_rectangle((x0, y, x1, y + 70), radius=18, fill="#dfe7ee" if side == "l" else "#cfe9d3")
        pen.text((x0 + 14, y + 22), words, fill="#222222", font=FONT)
    return im


def blurry_busy(rng):  # an extra blurry photo for case 28c, independent of the chaos set
    return photo("honey", plain_counter()).filter(ImageFilter.GaussianBlur(14))


# ---------------------------------------------------------------------------------------------------- goldens
def corner_bg(im):
    px = [im.getpixel(p) for p in ((2, 2), (im.width - 3, 2), (2, im.height - 3), (im.width - 3, im.height - 3))]
    return tuple(sum(c[i] for c in px) // 4 for i in range(3))


def golden_photo(pid, rng):
    """The live gallery picture cut out of its ivory background and pasted on a cluttered counter."""
    src = Image.open(GALLERY / f"photo-product-{pid}.webp").convert("RGB")
    bg = corner_bg(src)
    diff = ImageChops.difference(src, Image.new("RGB", src.size, bg)).split()
    mask = ImageChops.lighter(ImageChops.lighter(diff[0], diff[1]), diff[2]).point(lambda v: 255 if v > 26 else 0)
    mask = mask.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(5))  # seal small gaps
    outside = mask.copy()
    ImageDraw.floodfill(outside, (0, 0), 128)  # background reachable from the corner
    mask = outside.point(lambda v: 0 if v == 128 else 255).filter(ImageFilter.GaussianBlur(1.2))  # solid silhouette: label print stays inside
    box = mask.getbbox()
    product, mask = src.crop(box), mask.crop(box)
    side = 800  # big enough that the label print stays readable, as a phone photo would
    scale = min(0.84 * side / product.width, 0.84 * side / product.height)
    product = product.resize((round(product.width * scale), round(product.height * scale)), Image.Resampling.LANCZOS)
    mask = mask.resize(product.size, Image.Resampling.LANCZOS)
    im = clutter(rng, side)
    at = ((side - product.width) // 2 + rng.randint(-20, 20), (side - product.height) // 2 + rng.randint(-10, 20))
    shadow = Image.new("L", im.size, 0)
    shadow.paste(mask.point(lambda v: v // 3), (at[0] + 10, at[1] + 14))
    im.paste(Image.new("RGB", im.size, (40, 30, 20)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(8)))
    im.paste(product, at, mask)
    return im


# ------------------------------------------------------------------------------------------------------ edits
def good_edit(name):
    """The same drawn product on the warm ivory background, upright, as an 800 x 800 picture."""
    return photo(name, canvas(IVORY)).resize((800, 800), Image.Resampling.LANCZOS)


def bad_relabel(name):
    """HASS-IMAGE-1 T3 class 'painted relabel': another brand is painted over the label."""
    im = good_edit(name)
    pen = ImageDraw.Draw(im)
    x0, y0, x1, y1 = (round(v * 800 / SIZE) for v in PRODUCTS[name][1])
    pen.rectangle((x0, y0, x1, y1), fill="#fbf6ee")
    pen.text((x0 + 18, y0 + 40), "SUNNY BRAND", fill="#111111", font=FONT)
    pen.text((x0 + 18, y0 + 76), "Strawberry", fill="#111111", font=FONT)
    return im


def bad_recolour(name):
    """HASS-IMAGE-1 T3 class 'product recolour': the product's colours move, the background does not."""
    im = good_edit(name)
    r, g, b = im.split()
    swapped = Image.merge("RGB", (b, r, g))
    diff = ImageChops.difference(im, Image.new("RGB", im.size, IVORY)).split()
    mask = ImageChops.lighter(ImageChops.lighter(diff[0], diff[1]), diff[2]).point(lambda v: 255 if v > 30 else 0)
    return Image.composite(swapped, im, mask)


def build(out):
    rng = random.Random(SEED)
    photos, edits = out / "photos", out / "edits"
    photos.mkdir(parents=True, exist_ok=True)
    edits.mkdir(parents=True, exist_ok=True)
    written = []

    def save_jpg(im, name):
        im.save(photos / name, "JPEG", quality=90)
        written.append(photos / name)

    for pid in GOLDEN_IDS:
        save_jpg(golden_photo(pid, rng), f"golden-{pid}.jpg")
    for name in PRODUCTS:
        save_jpg(photo(name, clutter(rng)), f"{name}.jpg")
    save_jpg(photo("honey", clutter(rng)), "honey-busy-counter.jpg")
    save_jpg(photo("clean-jar", plain_counter()), "clean-jar-plain.jpg")
    save_jpg(photo("clean-jar", busy_cloth()), "clean-jar-busy.jpg")
    save_jpg(sticker_photo(rng), "honey-cost-sticker.jpg")
    save_jpg(screen_photo(rng), "phone-screen.jpg")
    save_jpg(blurry_busy(rng), "honey-blurry.jpg")
    for name in ("honey", "elderberry", "coffee", "figs"):
        for label, make in (("good", good_edit), ("bad-relabel", bad_relabel), ("bad-recolour", bad_recolour)):
            path = edits / f"{name}-{label}.png"
            make(name).save(path, "PNG")
            written.append(path)
    raw = plain_counter()
    coffee_size(raw)
    save_jpg(raw, "coffee-size.jpg")
    house = canvas(IVORY)
    coffee_size(house)
    path = edits / "coffee-size-good.png"
    house.save(path, "PNG")
    written.append(path)
    return written


def verify_gate(out):
    """Run the real fidelity gate over the drawn good edits (expected ok) and bad edits (expected rejected)."""
    sys.path.insert(0, str(ROOT))
    from hass import photo_polish  # noqa: PLC0415
    results = []
    for name in ("honey", "elderberry", "coffee", "figs"):
        original = (out / "photos" / f"{name}.jpg").read_bytes()
        for label, want in (("good", True), ("bad-relabel", False), ("bad-recolour", False)):
            edited = (out / "edits" / f"{name}-{label}.png").read_bytes()
            got = photo_polish.gate(original, edited)
            results.append((name, label, want, got["ok"], got["code"]))
            print(f"{name:11s} {label:13s} expected {'ok' if want else 'rejected'}: gate ok={got['ok']} code={got['code']}")
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out", nargs="?", default=str(DEFAULT_OUT))
    ap.add_argument("--verify-gate", action="store_true")
    args = ap.parse_args(argv)
    out = Path(args.out)
    for path in build(out):
        print(path)
    if args.verify_gate:
        bad = [r for r in verify_gate(out) if r[2] != r[3]]
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
