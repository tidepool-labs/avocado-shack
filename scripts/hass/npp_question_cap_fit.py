#!/usr/bin/env python3
"""Measure first-ask S3 replies against the pinned question caps, offline."""

import argparse
from collections.abc import Iterator
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import npp
from hass.content_model import load_content
from hass.npp import missing


ITEM = "Wildflower Honey"
SCENARIOS = (
    ("nothing", {}),
    ("item-no-price", {"owner_item": ITEM}),
    ("price-no-unit", {"owner_item": ITEM, "price": missing.OwnerPrice("4.00", None)}),
    ("unit-no-price", {"owner_item": ITEM, "price": missing.OwnerPrice(None, "item")}),
    ("dup-no-price", {}),
    ("dup-priced", {"price": missing.OwnerPrice("4.00", "item")}),
)


def scenario_inputs(catalog) -> Iterator[tuple[str, dict[str, Any], bool]]:
    product = next(p for p in catalog.products if p.get("status") != "held")
    duplicate = dict(owner_item=product["name"], products=catalog.products, makers=catalog.makers)
    for label, inputs in SCENARIOS:
        yield label, (duplicate | inputs if label.startswith("dup-") else inputs), False
    for key, maker in catalog.makers.items():
        if maker.get("hidden") is True:
            continue
        name = maker["name"]
        variant = name[:-1] if name.endswith("s") else name + "s"
        yield f"near {key}", dict(owner_item=ITEM, owner_texts=["made by " + variant],
                                  makers=catalog.makers, price=missing.OwnerPrice(None, None)), True


def check():
    mi = missing.MissingInfo(npp.assets())
    catalog = load_content(ROOT / "hass/content")
    caps = mi.replies["caps"]
    max_questions = caps["max_questions_per_reply"]
    max_chars = caps["question_max_chars"]
    failed = False
    near_max = 0
    for label, inputs, near in scenario_inputs(catalog):
        decision = mi.decide(**inputs)
        count = len(decision.questions)
        chars = len(" ".join(sentence for _, sentence in decision.questions))
        ids = ",".join(qid for qid, _ in decision.questions) or "-"
        print(f"qcap {label} questions={count} chars={chars} ids={ids}")
        if near:
            near_max = max(near_max, chars)
        for reason, finding in (
            ("over-count", count > max_questions),
            ("over-chars", chars > max_chars),
            ("silent-stall", decision.missing and count == 0),
        ):
            if finding:
                print(f"FAIL {reason} {label}")
                failed = True
    print(f"qcap near-max chars={near_max}")
    return failed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    if args:
        parser.error("no arguments accepted")
    try:
        failed = check()
    except Exception:
        # Do not print exception text (which can expose input details).
        print("FAIL check-error")
        failed = True
    print(f"{'FAIL' if failed else 'PASS'} npp_question_cap_fit")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
