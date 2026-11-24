#!/usr/bin/env python3
"""Check catalog picture formats and header dimensions in local copies."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model


HEADER_LIMIT = 1024 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
EXTENSIONS = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".webp": "webp"}
SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error can echo an unrecognized argument's value.
        super().error("invalid arguments; see --help")


def jpeg_size(data):
    pos = 2  # Skip SOI; walk segments without searching inside their payloads.
    while pos < len(data) and data[pos] == 0xFF:
        while pos < len(data) and data[pos] == 0xFF:
            pos += 1
        if pos == len(data):
            break
        marker = data[pos]
        pos += 1
        if marker in (0, 0xD9, 0xDA):  # Stuffed byte, end of image, or start of scan.
            break
        if 0xD0 <= marker <= 0xD9 or marker == 1:
            continue
        if pos + 2 > len(data):
            break
        length = int.from_bytes(data[pos:pos + 2], "big")
        if length < 2 or pos + length > len(data):
            break
        if marker in SOF:
            if length >= 8:
                height = int.from_bytes(data[pos + 3:pos + 5], "big")
                width = int.from_bytes(data[pos + 5:pos + 7], "big")
                return width, height
            break
        pos += length
    return None


def png_size(data):
    if len(data) >= 24 and data[8:16] == b"\x00\x00\x00\rIHDR":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    return None


def webp_size(data):
    def le(start, end):
        return int.from_bytes(data[start:end], "little")

    chunk = data[12:16]
    # Only require the dimension-bearing prefix, not the rest of the frame.
    available = min(len(data) - 20, le(16, 20), le(4, 8) - 12)
    if chunk == b"VP8 " and available >= 10 and data[23:26] == b"\x9d\x01\x2a":
        return le(26, 28) & 0x3FFF, le(28, 30) & 0x3FFF
    if chunk == b"VP8L" and available >= 5 and data[20] == 0x2F:
        bits = le(21, 25)
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8X" and available >= 10:
        return le(24, 27) + 1, le(27, 30) + 1
    return None


def identify(data):
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg", jpeg_size(data)
    if data.startswith(PNG_MAGIC):
        return "png", png_size(data)
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp", webp_size(data)
    return None, None


def picture_references(content):
    pictures = defaultdict(set)
    malformed = 0
    for product in content.products:
        if not isinstance(product, dict):
            malformed += 1
            continue
        if product.get("status") not in ("active", "hidden"):
            continue
        image = product.get("image")
        if isinstance(image, str) and content_model.IMAGE_RE.fullmatch(image):
            ids = pictures[Path(image)]
            product_id = product.get("id")
            if isinstance(product_id, str) and content_model.ID_RE.fullmatch(product_id):
                ids.add(product_id)
    if "homeImage" in content.store:
        home = content.store["homeImage"]
        if not isinstance(home, dict):
            malformed += 1
        elif isinstance(image := home.get("image"), str) and content_model.HOME_IMAGE_RE.fullmatch(image):
            pictures[Path(image)].add("store.homeImage")
    return pictures, malformed


def regular_picture(site, relative):
    # References have already matched a catalog path pattern. Do not follow
    # links in either the asset directories or the final file.
    path = site / relative
    try:
        return (all(stat.S_ISDIR((site / parent).lstat().st_mode)
                    for parent in reversed(relative.parents))
                and stat.S_ISREG(path.lstat().st_mode))
    except OSError:
        return False


def check(site, pictures, malformed):
    formats = Counter()
    findings = Counter()
    affected = defaultdict(set)
    sizes = []
    missing = 0
    for relative, ids in pictures.items():
        if not regular_picture(site, relative):
            missing += 1
            continue
        try:
            with (site / relative).open("rb", buffering=0) as image:
                kind, size = identify(image.read(HEADER_LIMIT))
        except OSError:
            kind, size = None, None
        if kind:
            formats[kind] += 1
            if kind != EXTENSIONS[relative.suffix]:
                findings["ext-mismatch"] += 1
                affected["ext-mismatch"].update(ids)
        if size and all(size):
            sizes.append(size)
        else:
            findings["unreadable"] += 1
            affected["unreadable"].update(ids)

    print(f"checked {len(pictures) - missing}")
    for kind, count in sorted(formats.items()):
        print(f"format {kind} {count}")
    if sizes:
        widths, heights = zip(*sizes)
        for name, values in (("width", widths), ("height", heights)):
            print(f"{name}-min {min(values)}")
            print(f"{name}-max {max(values)}")
    if missing:
        print(f"note missing {missing}")
    if malformed:
        print(f"note malformed {malformed}")
    for reason, label in (("ext-mismatch", "mismatch"), ("unreadable", "unreadable")):
        if findings[reason]:
            for product_id in sorted(affected[reason]):
                print(f"{label} {product_id}")
            print(f"FAIL {reason} {findings[reason]}")
    return bool(findings)


def main(argv=None):
    parser = PrivateArgumentParser(description=__doc__)
    parser.add_argument("--content", required=True, type=Path, help="copy of the Hass content directory")
    parser.add_argument("--site", required=True, type=Path, help="copy of the site directory")
    args = parser.parse_args(argv)
    try:
        safe = all(stat.S_ISDIR(root.lstat().st_mode) for root in (args.content, args.site))
    except (OSError, ValueError):
        safe = False
    if not safe:
        print("FAIL unsafe-input")
        failed = True
    else:
        try:
            content = content_model.load_content(args.content)
            # The loader validates the envelope, not the type of its payload.
            if not isinstance(content.products, list):
                raise content_model.ContentError(["expected product list"])
        except (content_model.ContentError, UnicodeError, OSError):
            print("FAIL content-invalid")
            failed = True
        else:
            pictures, malformed = picture_references(content)
            failed = check(args.site, pictures, malformed)
    print(f"{'FAIL' if failed else 'PASS'} content_image_format")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
