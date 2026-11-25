#!/usr/bin/env python3
"""Check a public demo-fixture projection, without rendering or visiting its URL.

Usage: python3 -B scripts/hass/npp_fixture_preflight.py public-fixture.json
The JSON object supplies item and products (a local fixture's [{name, status?}],
status one of active/hidden/held), plus optional owner_url, owner_maker, and label
({brand, confidence}, as read by S2). Optional fields may be omitted but never
null; unknown keys anywhere are INVALID. Supply [] explicitly for an empty fixture
catalog. No private replay inputs.
Exit 0 CLEAR (these checks only), 1 HOLD (named checks), 2 INVALID (bad input).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.content_model import PRODUCT_STATUSES, _https
from hass.npp.missing import _duplicates, _maker


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def lint(fixture: dict) -> list[str]:
    """Return independent issue codes; only the supplied fixture snapshot is used."""
    if (not isinstance(fixture, dict) or not _text(fixture.get("item"))
            or set(fixture) - {"item", "products", "owner_url", "owner_maker", "label"}):
        raise ValueError("fixture")
    products = fixture.get("products")
    if not isinstance(products, list) or any(
        not isinstance(row, dict) or set(row) - {"name", "status"} or not _text(row.get("name"))
        or ("status" in row and row["status"] not in PRODUCT_STATUSES) for row in products
    ):
        raise ValueError("products")
    # Optional fields may be absent, but a present field is never null or the wrong type.
    maker, label = fixture.get("owner_maker"), fixture.get("label")
    if "owner_maker" in fixture and not _text(maker):
        raise ValueError("maker")
    if "owner_url" in fixture and not isinstance(fixture["owner_url"], str):
        raise ValueError("owner_url")
    evidence = {}
    if "label" in fixture:
        if not isinstance(label, dict) or set(label) - {"brand", "confidence"} or not _text(label.get("brand")):
            raise ValueError("label")
        c = label.get("confidence")
        if not isinstance(c, (int, float)) or isinstance(c, bool) or not 0 <= c <= 1:
            raise ValueError("confidence")
        evidence = {"brand_on_label": label["brand"], "confidence": {"brand": c}}

    issues = []
    if "owner_url" in fixture:
        problems = []
        _https(problems, "owner_url", fixture["owner_url"])
        if problems:
            issues.append("reserved_owner_url" if problems[0].endswith("(private name)") else "invalid_owner_url")
    if _maker(maker, evidence, {}).state == "contradictory":
        issues.append("label_identity_conflict")
    if _duplicates(fixture["item"], products, {}, None):
        issues.append("catalog_duplicate")
    return issues


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args(argv)
    try:
        issues = lint(json.loads(args.fixture.read_text(encoding="utf-8"), object_pairs_hook=_unique))
    except (OSError, ValueError, RecursionError):
        print(json.dumps({"status": "INVALID", "issues": ["invalid_fixture"]}))
        return 2
    print(json.dumps({"status": "HOLD" if issues else "CLEAR", "issues": issues}))
    return int(bool(issues))


if __name__ == "__main__":
    raise SystemExit(main())
