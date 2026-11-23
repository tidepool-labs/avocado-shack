#!/usr/bin/env python3
"""Report pilot photo metadata and Hass sharpness offline."""

import argparse
import io
from pathlib import Path
import stat
import sys
import warnings

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import media, newitem_render
from hass.ops import photos


class PhotoParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's normal diagnostic may echo private arguments verbatim.
        super().error("expected 1 to 10 photo paths (use -- before paths starting with -)")


def report(k, path):
    with warnings.catch_warnings():
        # Decoder diagnostics can contain private metadata. Never relay them.
        warnings.simplefilter("ignore")
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            if not stat.S_ISREG(path.lstat().st_mode):
                print(f"FAIL unreadable {k}")
                return False
            data = path.read_bytes()
            with Image.open(io.BytesIO(data)) as source:
                source.load()
                fmt, (width, height) = source.format, source.size
                gps = "yes" if 34853 in source.getexif() else "no"
        except Exception:  # noqa: BLE001 - filesystem and Pillow input errors must not expose details
            print(f"FAIL unreadable {k}")
            return False

        try:
            img, alpha, _ = newitem_render._upright(data)
        except (media.Refused, newitem_render.Refused):
            # A Pillow-readable file can still be outside Hass's scoring inputs.
            score = None
        else:
            score = photos._sharpness(img, alpha)

    soft = score is not None and score < photos.SHARP_MIN
    sharpness = "unscored" if score is None else "soft" if soft else "ok"
    print(f"photo {k} format {fmt}")
    print(f"photo {k} size {width}x{height}")
    print(f"photo {k} bytes {len(data)}")
    print(f"photo {k} gps {gps}")
    print(f"photo {k} sharpness {sharpness}")
    if soft:
        print(f"FAIL soft {k}")
    return not soft


def main(argv=None):
    parser = PhotoParser(
        prog="pilot_photo_precheck", allow_abbrev=False,
        description="Report local photo metadata and Hass sharpness. Unscored does not certify sharpness.",
    )
    parser.add_argument("photos", metavar="PHOTO", nargs="+", type=Path)
    args = parser.parse_args(argv)
    if len(args.photos) > 10:
        parser.error("too many photos")

    passed = True
    for k, path in enumerate(args.photos, 1):
        if not report(k, path):
            passed = False
    print(f"{'PASS' if passed else 'FAIL'} pilot_photo_precheck")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
