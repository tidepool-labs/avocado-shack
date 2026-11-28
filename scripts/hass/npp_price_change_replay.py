#!/usr/bin/env python3
"""Replay synthetic price edits against the offline NPP card-out stage."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.npp import private_numbers
from hass.npp.job import Work
from hass.npp.reply import Stages


WORDINGS = (
    "$5 each",
    "make it $5 each",
    "sell it for $5 each",
    "$5 a pound",
    "$5",
    "make it $5",
    "change the price to $5",
    "the price is $5 each",
    "price: $5",
    "sell them for $5",
    "price is now $5",
    "it's $5 now",
)


YES_NO = {True: "yes", False: "no"}
FINDINGS = {"asked": "price-asked", "skipped": "price-not-routed", "other": "price-other"}


def replay(st, wording):
    routed = st.takes_turn(wording, "card_out")
    f = private_numbers.finance(wording)
    read = f.price_span is not None
    if not routed:
        return routed, read, "skipped"

    slot = {}
    if read:
        if f.selling_price is None:
            raise ValueError("price span without a selling price")
        slot["price"] = f.selling_price.partition(" ")[0]
    plan = st.edit(Work(
        "abcd",
        {"texts": ["x", f.public_words], "slots": {"intake": slot}, "attachments": ["ab" * 32]},
        {"listing_json": json.dumps({"name": "Honey", "sellingPrice": "4.00", "priceUnit": "each", "_texts": 1})},
        None,
    ))
    if plan.questions:
        return routed, read, "asked"
    if plan.listing is not None and plan.listing.get("sellingPrice") == "5.00":
        return routed, read, "applied"
    return routed, read, "other"


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    try:
        st = Stages(npp.assets(), start=None, render=None)
    except Exception:
        print("FAIL check-error")
        print("FAIL npp_price_change_replay")
        return 1

    failed = False
    for position, wording in enumerate(WORDINGS, 1):
        try:
            routed, read, result = replay(st, wording)
        except Exception:
            # Exception text may contain input or file paths; report only the check failure.
            print("FAIL check-error")
            failed = True
            continue
        print(f"price {position:02d} routed={YES_NO[routed]} read={YES_NO[read]} result={result}")
        if result in FINDINGS:
            print(f"FAIL {FINDINGS[result]} {position:02d}")
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_price_change_replay")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
