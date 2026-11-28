#!/usr/bin/env python3
"""Replay synthetic maker edits up to the offline copy-candidate boundary."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import content_model, npp
from hass.npp import copy, edits, missing, picture, private_numbers, research, stages
from hass.npp.job import Work

SHA = "ab" * 32
PARENT = {
    "name": "Wildflower Honey",
    "category": "pantry",
    "kind": "food",
    "sellingPrice": "4.00",
    "priceUnit": "each",
    "maker": "Etto Farm",
    "makerKey": None,
    "newMaker": True,
    "town": "Arroyo Grande",
    "url": "",
    "facts": [{
        "id": "official-founded",
        "slot": "founded",
        "value": "1990",
        "url": "https://ettofarm.example/",
        "quote": "Etto Farm started in 1990.",
        "verdict": "supports",
    }],
    "photo": SHA,
    "personOrScreen": False,
    "size": None,
    "labelWords": [],
    "_texts": 3,
}
BASE_TEXTS = ["it's wildflower honey", "made by Etto Farm", "based in Arroyo Grande"]
CASES = (
    "",
    "made by Bee Hill Apiary",
    "made by Etto Farm",
    "call it Clover Honey",
    "made by Bee Hill Apiary from Arroyo Grande",
)


def _probe():
    # Avoid ProductionStages.__init__, which constructs live adapters.
    p = object.__new__(stages.ProductionStages)
    p.pinned = npp.assets()
    p.replies = p.pinned[2]
    p.writer = copy.Writer(p.pinned)
    p.missing = missing.MissingInfo(p.pinned)
    p.selector = None  # pyright: ignore[reportAttributeAccessIssue]
    p.catalog = lambda: content_model.load_content(ROOT / "hass/content")
    p.clover = lambda *_args: None
    p._remaining = lambda work: 0

    def fixture_picture(work, listing, private, *, local):
        return picture.FrozenPicture("raw", "assets/products/fixture.jpg", SHA), SHA, "", []

    recorded = []

    def record_candidate(context, listing, finance, makers, key, fresh, url, sha, selector):
        recorded.append((context, fresh))
        return None, None, None

    p._picture = fixture_picture
    p._candidate = record_candidate
    return p, recorded


def _check_case(p, recorded, number, text):
    words = private_numbers.finance(text).public_words
    listing = PARENT
    texts = BASE_TEXTS.copy()
    if text:
        edit = edits.read(edits.Grammar(npp.assets()[1]), words, {})
        listing = edits.apply(PARENT, [edit])[0]
        texts.append(words)
    work = Work("abcd", {
        "texts": texts,
        "slots": {"intake": {"price": "4.00", "sold_by": "item", "price_span": [0, 8], "private": []}},
        "attachments": [SHA],
    }, None, None)
    recorded.clear()
    p.render_listing(work, listing, local=True)
    if not recorded:
        return f"not-reached {number:02d}"
    ctx, fresh = recorded[-1]
    foreign = sum(not ctx.maker_name or not research._has(fact.quote, ctx.maker_name)
                  for fact in ctx.facts)
    print(f"case {number:02d} fresh={'yes' if fresh else 'no'} foreign={foreign}")
    return f"foreign-facts {number:02d}" if foreign else None


def _findings():
    try:
        p, recorded = _probe()
    except Exception:  # Report only a fixed label, never fixture or exception text.
        yield "check-error"
        return

    for number, text in enumerate(CASES, 1):
        try:
            reason = _check_case(p, recorded, number, text)
        except Exception:
            reason = "check-error"
        if reason:
            yield reason


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)
    failed = False
    for reason in _findings():
        print(f"FAIL {reason}")
        failed = True
    print(f"{'FAIL' if failed else 'PASS'} npp_maker_edit_facts")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
