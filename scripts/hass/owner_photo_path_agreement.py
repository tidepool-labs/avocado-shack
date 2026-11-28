#!/usr/bin/env python3
"""Check that installed owner-photo paths agree across Hass and the storefront."""

import argparse
from pathlib import Path
import re
import stat
import sys
import warnings

ROOT = Path(__file__).resolve().parents[2]
SHOP = ROOT / "storefront-mockup/shop.js"
SHOP_CAP = 1_000_000
SITE_LITERAL = re.compile(r"const installedImage=s=>typeof s==='string'&&/(.+?)/\.test\(s\);")
SHAS = ("0" * 64, "ab" * 32, "0123456789abcdef" * 4)

sys.path.insert(0, str(ROOT))
from hass import content_model, house_style  # noqa: E402
from hass.skills import item_picture  # noqa: E402


class Finding(Exception):
    """A fixed diagnostic that does not expose source data."""


def read_shop():
    try:
        info = SHOP.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise Finding("input-unsafe shop")
        if info.st_size > SHOP_CAP:
            raise Finding("input-too-large shop")
        with SHOP.open("rb") as stream:
            raw = stream.read(SHOP_CAP + 1)
        if not isinstance(raw, bytes):
            raise Finding("input-unreadable shop")
        if len(raw) > SHOP_CAP:
            raise Finding("input-too-large shop")
        return raw.decode("utf-8")
    except (OSError, ValueError):
        raise Finding("input-unreadable shop") from None


def site_regex(text):
    match = SITE_LITERAL.search(text)
    if not match or not (match[1].startswith("^") and match[1].endswith("$")):
        raise Finding("js-regex-missing")
    # fullmatch enforces a true end, unlike Python's unmodified dollar anchor.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            warnings.simplefilter("ignore", DeprecationWarning)
            return re.compile(match[1][1:-1].replace(r"\/", "/"))
    except (re.error, OverflowError, RecursionError):
        raise Finding("js-regex-invalid") from None


def compare(site):
    installed = [path for sha in SHAS for path in item_picture.installed_names(sha)]
    h = "ab" * 8
    prefix = "assets/products/photo-"
    near_misses = (
        f"{prefix}{h.upper()}.jpg",
        f"{prefix}{h[:15]}.jpg",
        f"{prefix}{h}a.jpg",
        f"{prefix}{h}.jpeg",
        f"{prefix}{h}.webp",
        f"./{prefix}{h}.jpg",
        f"{prefix}{h}.jpg\n",
        f"{prefix}{h}.jpg.png",
    )
    rules = (("home", content_model.HOME_IMAGE_RE),
             ("owner", house_style.OWNER_IMAGE_RE), ("site", site))
    findings = []
    for name, regex in rules:
        refused = sum(regex.fullmatch(path) is None for path in installed)
        if refused:
            findings.append(f"installed-refused {name} {refused}")
    for index, path in enumerate(near_misses, 1):
        if any(regex.fullmatch(path) is not None for _, regex in rules):
            findings.append(f"near-miss-disagree {index}")
    print(f"installed {len(installed)}")
    print(f"near-misses {len(near_misses)}")
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    parser.parse_args(args)
    if args:  # argparse normally accepts a bare '--' even with no positionals.
        parser.error("no arguments expected")

    try:
        site = site_regex(read_shop())
    except Finding as error:
        findings = [str(error)]
    else:
        try:
            findings = compare(site)
        except Exception:
            findings = ["check-error"]

    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} owner_photo_path_agreement")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
