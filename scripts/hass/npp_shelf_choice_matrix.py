#!/usr/bin/env python3
"""Report the shelves selected by the offline S3 missing-info decision."""

import argparse
from itertools import product
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.content_model import CATEGORIES
from hass.npp import missing


KINDS = ("food", "drink", "fresh", "non-food")
GUESSES = ("vegetables", "flowers", "general", None)
CONFIDENCES = (0.9, 0.3)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    try:
        mi = missing.MissingInfo(npp.assets())
    except Exception:
        print("FAIL check-error")
        print("FAIL npp_shelf_choice_matrix")
        return 1

    failed = False
    for kind, guess, conf in product(KINDS, GUESSES, CONFIDENCES):
        label = guess or "none"
        try:
            category = mi.decide(
                {"is_product": True, "item": "Thing", "kind": kind,
                 "category_guess": guess,
                 "confidence": {"item": 0.9, "kind": 0.9, "category": conf, "brand": 0}},
                price=missing.OwnerPrice("4.00", "item"),
            ).category
        except Exception:
            print("FAIL check-error")
            failed = True
            continue

        print(f"shelf {kind} {label} {conf} -> {category}")
        if category not in CATEGORIES:
            print(f"FAIL not-a-shelf {kind} {label} {conf}")
            failed = True
        if kind == "non-food" and category != "general":
            print(f"FAIL nonfood-shelf {label} {conf}")
            failed = True
        if kind != "non-food" and guess is not None and conf == 0.9 and category != guess:
            print(f"FAIL confident-guess-lost {kind} {label}")
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_shelf_choice_matrix")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
