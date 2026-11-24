#!/usr/bin/env python3
"""Count shared NPP description spans in the catalog without showing the copy."""

import argparse
from itertools import combinations
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model, npp
from hass.npp import validate


class CountsParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse diagnostics can echo arbitrary argument values.
        super().error("invalid arguments")


def nonnegative_int(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return number


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL catalog_copy_overlap")
    return 1


def main(argv=None):
    parser = CountsParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", type=Path, default=content_model.CONTENT_DIR, metavar="DIR")
    parser.add_argument("--max-pairs", type=nonnegative_int, default=0, metavar="N")
    args = parser.parse_args(argv)

    try:
        safe = not args.content.is_symlink() and args.content.is_dir()
    except (OSError, ValueError):
        safe = False
    if not safe:
        return fail("unsafe-input")

    try:
        content = content_model.load_content(args.content)
        descriptions = [p["description"] for p in sorted(content.active_products(), key=lambda p: p["id"])
                        if p.get("description")]
        if any(not isinstance(text, str) for text in descriptions):
            return fail("content-invalid")
    except Exception:
        return fail("content-invalid")

    try:
        pinned = npp.assets()
        templates = json.loads(pinned[1]["hass-listing-copy/copy-templates.json"])
        k = templates["no_copying"]["span_words"]
        if type(k) is not int or k < 1:
            return fail("assets-invalid")
    except Exception:
        return fail("assets-invalid")

    spans = [validate._spans(description, k) for description in descriptions]
    degrees = [0] * len(spans)
    pairs = 0
    for (i, left), (j, right) in combinations(enumerate(spans), 2):
        if not left.isdisjoint(right):
            pairs += 1
            degrees[i] += 1
            degrees[j] += 1

    print(f"span-words {k}")
    print(f"descriptions {len(spans)}")
    print(f"pairs {pairs}")
    print(f"products {sum(degree > 0 for degree in degrees)}")
    print(f"largest {max(degrees, default=0)}")
    if pairs > args.max_pairs:
        return fail(f"shared-pairs {pairs} {args.max_pairs}")
    print("PASS catalog_copy_overlap")
    return 0


if __name__ == "__main__":
    sys.exit(main())
