#!/usr/bin/env python3
"""Report whether Hass calls a recognized, already-satisfied name edit unclear."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.npp import edits, reply
from hass.npp.job import Work


LISTING = {
    "name": "Wildflower Honey",
    "category": "pantry",
    "kind": "food",
    "sellingPrice": "4.00",
    "priceUnit": "each",
    "maker": None,
    "makerKey": None,
    "newMaker": False,
    "town": "",
    "url": "",
    "facts": [],
    "photo": "ab" * 32,
    "personOrScreen": False,
    "size": None,
    "labelWords": [],
}
SAME = ["call it Wildflower Honey", "rename it to Wildflower Honey", "the name is Wildflower Honey"]
CONTROL = "call it Clover Honey"


def _work(text):
    return Work(
        "abcd",
        {
            "texts": ["Wildflower honey $4 each", text],
            "slots": {"intake": {"price": "4.00", "sold_by": "item", "price_span": [17, 19], "private": []}},
            "attachments": ["ab" * 32],
        },
        {"listing_json": json.dumps({**LISTING, "_texts": 1})},
        None,
    )


def _unexpected_stage(*_args):
    raise RuntimeError("only the edit stage is exercised")


def _reply_id(plan):
    if plan.questions:
        return plan.questions[0][0]
    if plan.patch is not None:
        return "patch"
    raise ValueError("edit returned neither a question nor a patch")


def _checks():
    try:
        st = reply.Stages(npp.assets(), start=_unexpected_stage, render=_unexpected_stage, mapper=None)
    except Exception:
        yield "check-error"
        return

    for i, text in enumerate(SAME):
        try:
            work = _work(text)
            finance = work.request["slots"]["intake"]
            read_ok = any(field == "name" for field, _ in edits.read(st.grammar, text, dict(finance), None).patch)
            outcome = _reply_id(st.edit(work))
        except Exception:
            yield "check-error"
            continue
        print(f"nochange {i} read={'yes' if read_ok else 'no'} reply={outcome}")
        if read_ok and outcome == "ask_edit_unclear":
            yield f"nochange-called-unclear {i}"

    try:
        outcome = _reply_id(st.edit(_work(CONTROL)))
    except Exception:
        yield "check-error"
        return
    print(f"nochange control reply={outcome}")
    if outcome != "patch":
        yield "control-broken"


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    for reason in _checks():
        print(f"FAIL {reason}")
        failed = True
    print(f"{'FAIL' if failed else 'PASS'} npp_edit_no_change_reply")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
