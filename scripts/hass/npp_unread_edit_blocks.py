#!/usr/bin/env python3
"""Check offline whether an unreadable text blocks a later readable card edit."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp  # noqa: E402
from hass.npp import edits, job, reply  # noqa: E402

PARENT = {
    "name": "Honey", "category": "pantry", "sellingPrice": "6.00",
    "priceUnit": "each", "maker": None, "_texts": 1,
}
CASES = [
    ["photo", "call it Fig Jam"],
    ["photo", "change it to something nicer"],
    ["photo", "change it to something nicer", "call it Fig Jam"],
    ["photo", "make it pop", "call it Fig Jam", "put it in dairy"],
    ["photo", "call it Fig Jam", "change it to something nicer"],
]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    try:
        pinned = hass.npp.assets()
        st = reply.Stages(pinned, start=lambda w: None, render=lambda w, l: None)
        grammar = edits.Grammar(pinned[1])
    except Exception:  # noqa: BLE001 - report only the fixed diagnostic, not exception text
        print("FAIL check-error")
        print("FAIL npp_unread_edit_blocks")
        return 1

    failed = False
    for i, texts in enumerate(CASES):
        try:
            work = job.Work(
                "abc1234",
                {"texts": texts, "slots": {"intake": {
                    "price": "6.00", "sold_by": "item", "price_span": [0, 3],
                }}, "attachments": []},
                {"listing_json": json.dumps(PARENT)},
                None,
            )
            plan = st.edit(work)
            if plan.questions:
                print(f"case {i} question={plan.questions[0][0]}")
            elif plan.patch is not None:
                print(f"case {i} patch={','.join(plan.patch)}")
            else:
                raise ValueError("edit plan has neither questions nor a patch")
            if edits.read(grammar, texts[-1], {}).patch and plan.questions:
                print(f"FAIL blocked {i}")
                failed = True
        except Exception:  # noqa: BLE001 - a case that could not be checked is a finding
            print("FAIL check-error")
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_unread_edit_blocks")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
