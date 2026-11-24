#!/usr/bin/env python3
"""Check the NPP shelf lists against the site's canonical categories, offline."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import content_model, npp
from hass.npp import edits


NAME = "npp_category_enum_agreement"


def _enum(files, path, field):
    values = json.loads(files[path])["properties"][field]["enum"]
    if not isinstance(values, list) or any(
        value is not None and not isinstance(value, str) for value in values
    ):
        raise ValueError("expected a category enum")
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(prog=NAME, description=__doc__, add_help=False)
    parser.parse_args(argv)

    content = list(content_model.CATEGORIES)
    sources = {}
    findings = []
    try:
        files = npp.assets()[1]
        identify_enum = _enum(files, "hass-product-identify/identify.schema.json", "category_guess")
        card = _enum(files, "hass-gallery-style/card.schema.json", "category")
    except Exception:
        # Do not include exception text or claim counts for unavailable schemas.
        findings.append("assets-unreadable")
    else:
        sources["identify"] = [value for value in identify_enum if value is not None]
        sources["card"] = card
        if None not in identify_enum:
            findings.append("identify-null-missing")
    sources["edits"] = list(edits.CATEGORIES)

    print(f"categories content count={len(content)}")
    expected = set(content)
    for source, values in sources.items():
        print(f"categories {source} count={len(values)}")
        distinct = set(values)
        if distinct != expected or len(distinct) != len(values):
            findings.append(f"category-drift {source}")
    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} {NAME}")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
