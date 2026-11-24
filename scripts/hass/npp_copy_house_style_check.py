#!/usr/bin/env python3
"""Check NPP's offline fallback descriptions against the older house style."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import content_model, house_style, npp
from hass.npp import copy


CHECK = "npp_copy_house_style_check"
KINDS = {
    "drinks": "drink",
    "fruit": "fresh",
    "vegetables": "fresh",
    "flowers": "fresh",
    "general": "non-food",
}


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's original message can echo an unrecognized path or value.
        super().error("invalid arguments")


def fail(reason):
    print(f"FAIL {reason}")
    print(f"FAIL {CHECK}")
    return 1


def main(argv=None):
    parser = PrivateArgumentParser(prog=f"{CHECK}.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", type=Path, default=content_model.CONTENT_DIR,
                        metavar="DIR", help="content directory (read only)")
    directory = parser.parse_args(argv).content
    try:
        safe = not directory.is_symlink() and directory.is_dir()
    except OSError:
        safe = False
    if not safe:
        return fail("unsafe-input")

    try:
        content = content_model.load_content(directory)
        products = sorted(content.active_products(), key=lambda product: product["id"])
        descriptions = tuple(product["description"] for product in products)
    except Exception:
        return fail("content-invalid")
    try:
        pinned = npp.assets()
    except Exception:
        return fail("assets-invalid")
    try:
        spec = house_style.load_spec()
    except Exception:
        return fail("style-spec-invalid")

    try:
        writer = copy.Writer(pinned)
    except Exception:
        return fail("check-error")

    written = style_pass = style_fail = soft_misses = 0
    check_error = False
    for index, product in enumerate(products):
        try:
            category = product["category"]
            owner_words = product["name"]
            ctx = copy.Context(KINDS.get(category, "food"), category, "raw", owner_words,
                               owner_words, other_descriptions=descriptions[:index] + descriptions[index + 1:])
            result = writer.write(ctx, None)
            if result is None:
                # The writer can legitimately decline to produce a listing.
                continue
            written += 1
            verdict = house_style.check_description(result.text["description"], spec,
                                                    name=result.text["name"], owner_text=owner_words)
            if verdict["pass"]:
                soft_misses += sum(not check["ok"] and not check["hard"] for check in verdict["checks"])
                style_pass += 1
            else:
                style_fail += 1
        except Exception:
            check_error = True

    print(f"products {len(products)}")
    print(f"written {written}")
    print(f"style-pass {style_pass}")
    print(f"style-fail {style_fail}")
    print(f"soft-misses {soft_misses}")
    if check_error:
        print("FAIL check-error")
    if style_fail:
        print(f"FAIL style-fail {style_fail}")
    if check_error or style_fail:
        print(f"FAIL {CHECK}")
        return 1
    print(f"PASS {CHECK}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
