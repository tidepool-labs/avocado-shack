#!/usr/bin/env python3
"""Audit S4's quote checks offline, before any verify model is called."""

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp
from hass.npp import research


URL = "https://etto.example/"
NAME = "Etto Farm"
HONEY = "Etto Farm makes honey."
FOUNDED = "Etto Farm was founded in 1950."
APIARY = "Etto Farm is an apiary."
TOWN = "Etto Farm is in Arroyo Grande."
UNNAMED = "We ship honey."
HEDGE = "Etto Farm probably makes jam."
OLD = "Etto Farm was founded in 1750."
PRODUCTS = "honey, jam, wax, candles, soap, lotion and tea"
MAKES_LIST = f"Etto Farm makes {PRODUCTS}."
WINERY = "Etto Farm is a winery."
CONTROL = "Etto Farm is a farm."
MARKET = "Etto Farm sells honey at the market."
KITCHEN = "Etto Farm Kitchen makes jam."

# URL, slot, value, quote, known town, first refusal (None means accepted).
ROWS = (
    (URL, "makes", "honey", HONEY, "", None),
    ("https://other.example/", "makes", "honey", HONEY, "", "unverified-url"),
    (URL, "makes", "honey", "Etto Farm makes candy.", "", "quote-not-in-visible-body-text"),
    (URL, "makes", "jam", HEDGE, "", "negation-past-or-hedge-marker"),
    (URL, "makes", "honey", UNNAMED, "", "quote-does-not-name-maker"),
    (URL, "makes", "honey", "Etto Farm makes", "", "fragment-without-context"),
    (URL, "makes", "wax", HONEY, "", "value-not-in-quote"),
    (URL, "name", "Etto", HONEY, "", "invalid-name"),
    (URL, "town", "Arroyo Grande", TOWN, "Arroyo Grande", None),
    (URL, "town", "Arroyo Grande", TOWN, "Nipomo", "invalid-town"),
    (URL, "founded", "1750", OLD, "", "invalid-year"),
    (URL, "founded", "1950", FOUNDED, "", None),
    (URL, "nature", "apiary", APIARY, "", None),
    (URL, "nature", "winery", WINERY, "", "invalid-nature"),
    (URL, "makes", PRODUCTS, MAKES_LIST, "", "invalid-product-type"),
    (URL, "name", NAME, HONEY, "", None),
)
NAME_ROWS = (
    (NAME, "nature", "farm", HONEY),
    (NAME, "nature", "farm", MARKET),
    ("Etto Farm Kitchen", "nature", "kitchen", KITCHEN),
)


def _audit(fail):
    _, files, _ = hass.npp.assets()
    schema = json.loads(files["hass-maker-research/facts.schema.json"])
    markers = research._markers(schema)
    page = research.Page(URL, "2026-11-21", titles=[NAME], blocks=[
        HONEY, FOUNDED, APIARY, TOWN, UNNAMED, HEDGE,
        "Etto Farm makes honey. Etto Farm sells it at markets.",
        OLD, MAKES_LIST, WINERY, CONTROL, MARKET, KITCHEN,
    ])
    pages = {page.url: page}

    def check(url, slot, value, quote, name=NAME, town=""):
        row = dict(url=url, slot=slot, value=value, quote=quote)
        return research._check(row, pages, name, town, schema, markers)

    for index, (url, slot, value, quote, town, expected) in enumerate(ROWS):
        reason = check(url, slot, value, quote, town=town)
        print(f"row {index} reason={reason or 'ok'}")
        if reason != expected:
            fail(f"reason-moved {index}")

    for index, (name, slot, value, quote) in enumerate(NAME_ROWS):
        reason = check(URL, slot, value, quote, name=name)
        print(f"name-row {index} reason={reason or 'ok'}")
        stripped = re.sub(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", " ", quote, flags=re.I)
        if not research._has(stripped, value) and reason is None:
            fail(f"value-only-in-name {index}")

    if check(URL, "nature", "farm", CONTROL) is not None:
        fail("control-refused")


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False

    def fail(reason):
        nonlocal failed
        failed = True
        print(f"FAIL {reason}")

    try:
        _audit(fail)
    except Exception:
        # An unreadable schema or interrupted check is not a clean run.
        fail("check-error")
    print(f"{'FAIL' if failed else 'PASS'} npp_quote_check_reasons")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
