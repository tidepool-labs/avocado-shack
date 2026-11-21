#!/usr/bin/env python3
"""Audit active product descriptions from a content copy without printing text."""

import argparse
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import content_model, house_style  # noqa: E402


CLAIM_CHECK = "no unstated claim term"


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL description_style_audit")
    return 1


def audit(products, spec):
    checks = Counter()
    passed = hard_products = invalid_ids = 0
    findings = []
    for product in products:
        result = house_style.check_description(product["description"], spec)
        passed += result["pass"]
        failed = [check for check in result["checks"] if not check["ok"]]
        checks.update({check["name"] for check in failed})
        hard = sum(check["hard"] and check["name"] != CLAIM_CHECK for check in failed)
        hard_products += bool(hard)
        pid = product["id"]
        if not isinstance(pid, str) or not content_model.ID_RE.fullmatch(pid):
            invalid_ids += 1
        elif hard:
            findings.append((pid, hard))

    print(f"checked {len(products)}")
    print(f"pass {passed}")
    for name, count in sorted(checks.items()):
        print(f"check {count} {name}")
    print(f"note unstated-claim {checks[CLAIM_CHECK]}")
    if invalid_ids:
        print(f"note invalid-id {invalid_ids}")
    for pid, hard in sorted(findings):
        print(f"hard {pid} {hard}")
    if hard_products:
        return fail(f"description-hard {hard_products}")
    print("PASS description_style_audit")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", required=True, type=Path, metavar="DIR")
    parser.add_argument("--spec", type=Path, default=house_style.SPEC_PATH, metavar="FILE")
    args, extra = parser.parse_known_args(argv)
    if extra:
        # An extra argument could itself contain a path or other private text.
        parser.error("unrecognized arguments")

    try:
        if args.content.is_symlink() or not args.content.is_dir():
            return fail("unsafe-input")
    except OSError:
        return fail("unsafe-input")
    try:
        content = content_model.load_and_validate(args.content, None)
    except (OSError, ValueError, TypeError):
        # ContentError is a ValueError; malformed records can also fail validation
        # with a TypeError (for example, an unhashable product ID).
        return fail("content-invalid")
    try:
        if args.spec.is_symlink() or not args.spec.is_file():
            return fail("spec-unreadable")
        spec = house_style.load_spec(args.spec)
        # Never let a falsey spec silently fall back to the default in the scorer.
        if not isinstance(spec, dict) or "descriptions" not in spec:
            return fail("spec-unreadable")
    except (OSError, ValueError, RecursionError):
        return fail("spec-unreadable")
    try:
        return audit(content.active_products(), spec)
    except (KeyError, TypeError, OverflowError, ValueError):
        # A JSON document can load but lack the values the style checker needs.
        return fail("spec-unreadable")


if __name__ == "__main__":
    sys.exit(main())
