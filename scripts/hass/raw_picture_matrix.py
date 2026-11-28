#!/usr/bin/env python3
"""Audit the S6 raw-photo decision offline with synthetic pixels and fixed reads."""

import argparse
from collections import Counter
from io import BytesIO
from itertools import product
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import newitem_synthetic  # noqa: E402
from hass.npp import picture  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    _, extra = parser.parse_known_args(argv)
    if extra:
        parser.error("no arguments are accepted")

    try:
        from PIL import Image, ImageFilter
    except ImportError:
        print("FAIL pillow-missing")
        print("FAIL raw_picture_matrix")
        return 1

    try:
        sharp = newitem_synthetic.make_photo()
        with Image.open(BytesIO(sharp)) as image, BytesIO() as output:
            image.convert("RGB").filter(ImageFilter.GaussianBlur(8)).save(output, "JPEG")
            blurry = output.getvalue()
    except Exception:
        print("FAIL check-error")
        print("FAIL raw_picture_matrix")
        return 1

    images = (("sharp", sharp), ("blurry", blurry))
    people = (("false", False), ("true", True), ("none", None))
    reads = (
        ("clean", "Raspberry " + "jam"),
        ("none", None),
        ("money", "only " + "$4.99"),
        ("contact", "write ab" + "@" + "example.com"),
        ("contact-short", "write a" + "@" + "example.com"),
        ("path", "/home/" + "someone"),
    )
    checks = (("true", True), ("false", False), ("none", None))
    counts = Counter()
    findings = []
    for (image, data), (person_name, person), (read_name, read), (clear_name, clear) in product(
        images, people, reads, checks
    ):
        counts["cells"] += 1
        label = f"{image}-{person_name}-{read_name}-{clear_name}"
        try:
            reason = picture._raw_problem(data, person, lambda text, allowed: clear,
                                          (), (), lambda data: read)
        except Exception:
            if "check-error" not in findings:
                findings.append("check-error")
            continue
        safe = label == "sharp-false-clean-true"
        if reason is None:
            counts["allowed"] += 1
            if not safe:
                findings.append(f"raw-allowed-unsafe {label}")
        else:
            counts[reason if reason in ("style", "blurry") else "other"] += 1
            if safe:
                findings.append("safe-cell-refused")

    print(f"cells {counts['cells']}")
    print(f"allowed {counts['allowed']}")
    for reason in ("style", "blurry", "other"):
        print(f"reason {reason} {counts[reason]}")
    for finding in findings:
        print(f"FAIL {finding}")
    print("FAIL raw_picture_matrix" if findings else "PASS raw_picture_matrix")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
