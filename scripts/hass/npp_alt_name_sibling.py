#!/usr/bin/env python3
"""Check that S5's plain alt-name templates cover their sized names offline."""

import argparse
from itertools import product
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import content_model, npp
from hass.npp import copy


TEMPLATE_ASSET = "hass-listing-copy/copy-templates.json"


def check_pair(sized, twin):
    template_id = sized["id"]
    if twin is None:
        return f"twin {template_id} base=- cases=0 mismatched=0", [f"twin-missing {template_id}"]

    findings = []
    if twin["field"] != "name":
        findings.append(f"twin-field {template_id}")

    cases = mismatched = 0
    for kind, category, variant in product(sized["kinds"], content_model.CATEGORIES, ("raw", "house")):
        ctx = copy.Context(kind=kind, category=category, variant=variant, item="Fixture")
        sized_ok = copy.eligible(sized, ctx)
        twin_ok = copy.eligible(twin, ctx)
        cases += 1
        if sized_ok and not twin_ok:
            mismatched += 1
            findings.append(f"twin-narrower {template_id} {kind} {category} {variant}")
    return f"twin {template_id} base={twin['id']} cases={cases} mismatched={mismatched}", findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    failed = False
    try:
        _, files, _ = npp.assets()
        templates = json.loads(files[TEMPLATE_ASSET])["templates"]
        by_id = {row["id"]: row for row in templates}
        for sized in templates:
            template_id = sized["id"]
            if template_id.endswith("-size"):
                summary, findings = check_pair(sized, by_id.get(template_id.removesuffix("-size")))
                print(summary)
                for finding in findings:
                    print(f"FAIL {finding}")
                failed |= bool(findings)
    except Exception:
        # A check that cannot run must not look like a clean comparison.
        print("FAIL check-error")
        failed = True

    print("FAIL npp_alt_name_sibling" if failed else "PASS npp_alt_name_sibling")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
