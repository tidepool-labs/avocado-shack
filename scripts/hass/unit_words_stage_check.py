#!/usr/bin/env python3
"""Compare S3 and S10 price-unit readings offline, without changing either stage."""

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import npp
from hass.npp import edits, private_numbers


PHRASES = (
    "each", "apiece", "per item", "per lb", "a lb", "per pound",
    "a pound", "/lb", "lb", "ea", "per basket", "a piece",
)
CHECK = "unit_words_stage_check"


def compare_price_units():
    """Print observations and yield only finding reasons, in check order."""
    try:
        grammar = json.loads(npp.assets()[1]["hass-listing-edit/edit-grammar.json"])
        price = next((form for form in grammar["forms"] if form["id"] == "price"), None)
        if price is None:
            yield "price-form-missing"
            return
        pattern = price["pattern"]
    except Exception:
        yield "assets-unreadable"
        return

    try:
        for phrase in PHRASES:
            suffix = phrase if phrase.startswith("/") else " " + phrase
            selling_price = private_numbers.finance("selling $4" + suffix).selling_price or ""
            s3 = "none"
            if selling_price.endswith(" each"):
                s3 = "each"
            elif selling_price.endswith(" per lb"):
                s3 = "lb"
            match = re.fullmatch(pattern, "make it $4" + suffix, re.I)
            form = "none"
            if match is not None:
                unit = match.groupdict().get("unit")
                form = "unitless" if unit is None else edits.UNITS[unit.lower()]
            mapped = edits.UNITS.get(phrase, "none")
            slug = phrase.replace("/", "slash-").replace(" ", "-")
            print(f"unit {slug} s3={s3} form={form} map={mapped}")
            if not s3 == form == mapped:
                yield f"unit-disagree {slug}"
    except Exception:
        yield "check-error"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    failed = False
    for reason in compare_price_units():
        print(f"FAIL {reason}")
        failed = True
    print(f"{'FAIL' if failed else 'PASS'} {CHECK}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
