#!/usr/bin/env python3
"""Report the shelf and kind chosen by the NPP cap's offline planning path."""

import argparse
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import content_model, npp
from hass.npp import copy, edits, missing, stages
from hass.npp.job import Work

CASES = ["it is honey", "it is strawberry jam", "it is a ceramic mug"]


def _port():
    # Wire the planner only. The fake renderer never opens a photo or an editor.
    p: Any = object.__new__(stages.ProductionStages)
    p.pinned = npp.assets()
    p.replies = p.pinned[2]
    p.grammar = edits.Grammar(p.pinned[1])
    p.writer = copy.Writer(p.pinned)
    p.missing = missing.MissingInfo(p.pinned)
    p.selector = p.mapper = None
    p.catalog = lambda: content_model.load_content(ROOT / "hass/content")
    p.clover = lambda: None
    p._remaining = lambda work: 0
    p.render_listing = lambda work, listing, *, local=False: "card"
    return p


def _listing(p, text):
    work = Work("abcd", {
        "texts": ["$4 each", text],
        "slots": {"intake": {"price": "4.00", "sold_by": "item", "price_span": [17, 19], "private": []}},
        "attachments": ["ab" * 32],
    }, None, None)
    result = p.cap(work, None)
    plan = result[0] if isinstance(result, tuple) else result
    return plan.listing if plan is not None else None


def _identifier(value):
    if value is None:
        return "none"
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", value):
        raise ValueError("not a code identifier")
    return value


def _finish(findings):
    for finding in findings:
        print(f"FAIL {finding}")
    print("FAIL npp_cap_plan_shelf" if findings else "PASS npp_cap_plan_shelf")
    return 1 if findings else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    try:
        p = _port()
        default_count = len(p.missing.rules["kind_default_category"].keys())
    except Exception:
        return _finish(["check-error"])

    findings = []
    for i, text in enumerate(CASES):
        try:
            listing = _listing(p, text)
            ready = "no" if listing is None else "yes"
            kind = _identifier(listing.get("kind")) if listing is not None else "none"
            category = _identifier(listing.get("category")) if listing is not None else "none"
        except Exception:
            # Don't expose exception text, even if multiple cases hit the same error.
            if "check-error" not in findings:
                findings.append("check-error")
            print(f"cap {i} ready=no kind=none category=none")
            continue
        print(f"cap {i} ready={ready} kind={kind} category={category}")
        if listing is None:
            findings.append(f"cap-not-ready {i}")
        elif i in (0, 1):
            if kind == "non-food":
                findings.append(f"cap-food-as-nonfood {i}")
            if category == "general":
                findings.append(f"cap-food-general {i}")

    print(f"cap defaults kind_default_category={default_count}")
    return _finish(findings)


if __name__ == "__main__":
    sys.exit(main())
