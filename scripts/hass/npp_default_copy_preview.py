#!/usr/bin/env python3
"""Count offline NPP fallback results and description template selections."""

import argparse
from collections import Counter
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import content_model, npp
from hass.npp import copy
from hass.product_claims import drop_copy_claims

TOOL = "npp_default_copy_preview"
# Stand-in for S2's photo read; this preview has no photo or label input.
KINDS = {
    "drinks": "drink",
    "fruit": "fresh",
    "vegetables": "fresh",
    "flowers": "fresh",
    "general": "non-food",
}


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse diagnostics can echo an input path or other rejected value.
        super().error("invalid arguments (see --help)")


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("expected a nonnegative integer")
    return number


def fail(reason):
    print(f"FAIL {reason}")
    print(f"FAIL {TOOL}")
    return 1


def main(argv=None):
    parser = PrivateArgumentParser(prog=f"{TOOL}.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", type=Path, default=content_model.CONTENT_DIR, metavar="DIR")
    parser.add_argument("--owner-words", choices=("name", "none"), default="name")
    parser.add_argument("--max-no-copy", type=nonnegative, default=0, metavar="N")
    args = parser.parse_args(argv)

    try:
        # lstat refuses a symlink to a directory as well as a dangling symlink.
        if not stat.S_ISDIR(args.content.lstat().st_mode):
            return fail("unsafe-input")
    except (OSError, ValueError):
        return fail("unsafe-input")
    try:
        content = content_model.load_content(args.content)
        products = sorted(content.active_products(), key=lambda product: product["id"])
    except Exception:
        return fail("content-invalid")
    try:
        pinned = npp.assets()
    except Exception:
        return fail("assets-invalid")

    templates = Counter()
    no_copy = not_plain = 0
    try:
        writer = copy.Writer(pinned)
        for product in products:
            category, name = product["category"], product["name"]
            owner_words = name if args.owner_words == "name" else ""
            others = tuple(other["description"] for other in products
                           if other is not product and other.get("description"))
            ctx = copy.Context(KINDS.get(category, "food"), category, "raw", name, owner_words,
                               other_descriptions=others)
            result = writer.write(ctx, None)
            if result is None:
                no_copy += 1
                if not copy.plain(drop_copy_claims(name, owner_words)[0]):
                    not_plain += 1
            else:
                templates[result.selections["description"]["template_id"]] += 1
    except Exception:
        return fail("writer-error")

    print(f"products {len(products)}")
    print(f"copy {len(products) - no_copy}")
    print(f"no-copy {no_copy}")
    for template_id, count in sorted(templates.items()):
        print(f"template {template_id} {count}")
    print(f"no-copy-reason item-not-plain {not_plain}")
    print(f"no-copy-reason other {no_copy - not_plain}")
    if no_copy > args.max_no_copy:
        return fail(f"no-copy-over {no_copy} {args.max_no_copy}")
    print(f"PASS {TOOL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
