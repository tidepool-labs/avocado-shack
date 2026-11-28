#!/usr/bin/env python3
"""Check offline whether a cap-born version remembers its consumed texts."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import content_model, npp
from hass.npp import copy, edits, missing, reply, stages
from hass.npp.job import Work

PHOTO = "ab" * 32
TEXTS = ("Wildflower honey $4 each", "it is honey")
LISTING = {
    "name": "Wildflower Honey", "category": "pantry", "kind": "food",
    "sellingPrice": "4.00", "priceUnit": "each", "maker": None,
    "makerKey": None, "newMaker": False, "town": "", "url": "", "facts": [],
    "photo": PHOTO, "personOrScreen": False, "size": None, "labelWords": [],
}


def fixture_port():
    # Do not initialize the live port or render a real card.
    p = object.__new__(stages.ProductionStages)
    p.pinned = npp.assets()
    p.replies = p.pinned[2]
    p.grammar = edits.Grammar(p.pinned[1])
    p.writer = copy.Writer(p.pinned)
    p.missing = missing.MissingInfo(p.pinned)
    setattr(p, "selector", None)
    p.mapper = None
    p.catalog = lambda: content_model.load_content(ROOT / "hass" / "content")
    p.clover = lambda: None
    p._remaining = lambda work: 0
    p.render_listing = lambda work, listing, *, local=False: "card"
    return p


def fixture_work(texts, parent=None):
    return Work("abcd", {
        "texts": list(texts),
        "slots": {"intake": {"price": "4.00", "sold_by": "item",
                             "price_span": [17, 19], "private": []}},
        "attachments": [PHOTO],
    }, parent, None)


def edit_outcome(port, parent):
    work = fixture_work((*TEXTS, "call it Clover Honey"),
                        {"listing_json": json.dumps(parent)})
    plan = reply.Stages.edit(port, work)
    if plan.questions:
        qid = plan.questions[0][0]
        if isinstance(qid, str) and qid.isascii() and qid.isidentifier():
            return qid
    elif plan.listing is not None:
        return "patch"
    raise ValueError("no reportable edit outcome")


def check():
    try:
        port = fixture_port()
        result = port.cap(fixture_work(TEXTS), None)
        plan = result[0] if isinstance(result, tuple) else result
        listing = plan.listing if plan is not None else None
        if listing is not None and not isinstance(listing, dict):
            raise ValueError("invalid cap listing")
    except Exception:
        # Never report exception details, which can contain request text.
        return ["check-error"]

    stamped = isinstance(listing, dict) and reply.SEEN in listing
    print(f"cap ready={'yes' if listing is not None else 'no'}")
    print(f"cap stamped={'yes' if stamped else 'no'}")
    findings = []
    if listing is None:
        findings.append("cap-not-ready")
    if not stamped:
        findings.append("seen-missing")

    parent = listing if listing is not None else LISTING
    outcomes = []
    for label, candidate in (("capped", parent), ("stamped", {**parent, reply.SEEN: 2})):
        try:
            outcome = edit_outcome(port, candidate)
        except Exception:
            continue
        print(f"edit {label}={outcome}")
        outcomes.append(outcome)
    if len(outcomes) != 2:
        findings.append("check-error")
    elif outcomes[0] != outcomes[1]:
        findings.append("edit-diverges")
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)
    findings = check()
    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} npp_cap_version_seen")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
