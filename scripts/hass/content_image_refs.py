#!/usr/bin/env python3
"""Audit product and home picture references in offline content and site copies."""

import argparse
from collections import Counter
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse can echo unrecognized arguments, including private paths.
        super().error("expected --content DIR and --site DIR (see --help)")


def finish(*findings):
    for finding in findings:
        print(f"FAIL {finding}")
    print("FAIL content_image_refs" if findings else "PASS content_image_refs")
    return int(bool(findings))


def site_files(content_dir, site_dir):
    assets = site_dir / "assets"
    pictures = assets / "products"
    for directory in (content_dir, site_dir, assets, pictures):
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise NotADirectoryError

    files = set()
    not_regular = 0
    with os.scandir(pictures) as entries:
        for entry in entries:
            if stat.S_ISREG(entry.stat(follow_symlinks=False).st_mode):
                files.add(entry.name)
            else:
                not_regular += 1
    return files, not_regular


def report(content, files, not_regular):
    product_refs = Counter()
    missing = []
    bad_path = held_missing = malformed = 0
    for product in content.products:
        if not isinstance(product, dict):
            malformed += 1
            continue
        status = product.get("status")
        image = product.get("image")
        name = None
        if isinstance(image, str) and content_model.IMAGE_RE.fullmatch(image):
            name = image.removeprefix("assets/products/")
            product_refs[name] += 1

        if status == "held":
            held_missing += name not in files
        elif status in ("active", "hidden"):
            if name is None:
                bad_path += 1
            elif name not in files:
                pid = product.get("id")
                # The loader checks envelopes, not the record IDs.
                missing.append(pid if isinstance(pid, str) and content_model.ID_RE.fullmatch(pid)
                               else "<invalid-id>")

    referenced = set(product_refs)
    home = content.store.get("homeImage")
    if isinstance(home, dict) and isinstance(home.get("image"), str):
        # This audit inventories the saved string; it does not validate the home schema.
        name = home["image"].removeprefix("assets/products/")
        referenced.add(name)
        if name not in files:
            missing.append("store.homeImage")

    orphans = files - referenced
    print(f"files {len(files)}")
    print(f"referenced {len(referenced)}")
    print(f"note not-regular {not_regular}")
    print(f"note orphan {len(orphans)}")
    for name in sorted(orphans):
        print(f"orphan {name}")
    print(f"note shared-image {sum(count >= 2 for count in product_refs.values())}")
    print(f"note held-image-missing {held_missing}")
    print(f"note malformed {malformed}")

    findings = []
    if bad_path:
        findings.append(f"bad-image-path {bad_path}")
    if missing:
        for label in sorted(missing):
            print(f"missing {label}")
        findings.append(f"image-missing {len(missing)}")
    return finish(*findings)


def main(argv=None):
    parser = ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", required=True, type=Path, help="content copy")
    parser.add_argument("--site", required=True, type=Path, help="storefront copy")
    args = parser.parse_args(argv)

    try:
        files, not_regular = site_files(args.content, args.site)
    except OSError:
        return finish("unsafe-input")
    try:
        content = content_model.load_content(args.content)
    except (OSError, ValueError):  # Includes ContentError and decoding errors.
        return finish("content-invalid")
    if not isinstance(content.products, list):
        return finish("content-invalid")
    return report(content, files, not_regular)


if __name__ == "__main__":
    sys.exit(main())
