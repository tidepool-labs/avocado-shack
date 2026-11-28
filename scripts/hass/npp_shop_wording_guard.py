#!/usr/bin/env python3
"""Check S4 shop and owner wording offline; report maker overlaps separately."""

import argparse
from pathlib import Path
import sys

ROOT = str(Path(__file__).resolve().parents[2])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from hass.npp import research


MAKER = "Miners Orchards"
SHOP = (
    "We are not affiliated with Miners Orchards.",
    "This is an unofficial fan page.",
    "We are an independent shop selling local foods.",
    "Miners Orchards is one of our brands.",
    "The brands we stock include Miners Orchards.",
    "We stock Miners Orchards jam.",
    "Miners Orchards products are available here.",
    "We are an authorized retailer.",
)
OWN = (
    "Miners Orchards grows apples in Arroyo Grande.",
    "We sell Miners Orchards jam at three farmers markets.",
    "Our farm stand offers fresh fruit picked at Miners Orchards.",
    "Miners Orchards products are available at our farm stand.",
    "Miners Orchards jams are sold at the Saturday market.",
    "We carry the whole Miners Orchards range in our barn shop.",
    "Miners Orchards is independently owned and operated.",
    "Miners Orchards is a licensed dairy.",
    "Miners Orchards is not affiliated with any other orchard.",
    "Miners Orchards supplies restaurants across the county.",
    "Find us at the Arroyo Grande farmers market every Saturday.",
    "Miners Orchards is part of the Arroyo Grande farm trail.",
    "We work with local stores that sell Miners Orchards honey.",
    "Our honey is sold in local shops.",
    "Miners Orchards has been family run since 1950.",
    "Miners Orchards is an authorized organic grower.",
)
OWNER_OK = (
    "Miners Orchards",
    "Miners Orchards LLC",
    "The Miners Orchards Company",
    "Miners Orchards & Sons",
    "Miners Orchards Family Farm",
    "Miners Orchards, Inc.",
)
OWNER_NO = (
    "Miners Orchards Shop",
    "Miners Orchards Grocery",
    "Miners Orchards Deli",
    "Miners Orchards Market",
    "Miners",
)


def _check_page(sentence):
    page = research.Page("https://miners.example/", "2026-11-21", blocks=[sentence])
    return research._contrary(page, MAKER)


def _check_owner(entity):
    return research._owner(entity, MAKER)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    argv = sys.argv[1:] if argv is None else argv
    parser.parse_args(argv)
    if argv:
        # argparse ordinarily accepts a bare end-of-options marker.
        parser.error("no arguments allowed")

    failed = False
    for inputs, check, expected, reason in (
        (SHOP, _check_page, True, "shop-missed"),
        (OWN, _check_page, None, None),  # Informational; no expected verdict.
        (OWNER_OK, _check_owner, True, "owner-refused"),
        (OWNER_NO, _check_owner, False, "owner-accepted"),
    ):
        for i, value in enumerate(inputs):
            try:
                actual = check(value)
            except Exception:
                print("FAIL check-error")
                failed = True
                continue
            if expected is None:
                print(f"own {i} contrary={'yes' if actual else 'no'}")
            elif actual != expected:
                print(f"FAIL {reason} {i}")
                failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_shop_wording_guard")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
