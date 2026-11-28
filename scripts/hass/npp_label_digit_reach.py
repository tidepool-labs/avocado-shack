#!/usr/bin/env python3
"""Check offline which photo label words survive into an NPP listing plan."""

import argparse
from decimal import Decimal
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import content_model, npp
from hass.npp import copy, missing, private_numbers, stages
from hass.npp.job import Work

WORDS = ('Wildflower', 'Honey', '12 oz', 'Net Wt 12 oz', 'Since 1990', 'Raw', '2 pack')
EVIDENCE = {
    'is_product': True,
    'item': 'Wildflower Honey',
    'kind': 'food',
    'category_guess': 'pantry',
    'confidence': {'item': 0.9, 'category': 0.9, 'brand': 0, 'size': 0.9},
    'brand_on_label': None,
    'size_text': None,
    'has_person_or_screen': False,
    'label_words': WORDS,
}


class FixtureIdentifier:
    def read(self, photos):
        for _ in photos:
            pass
        # Keep patched fixtures in sync without mutating the default evidence.
        evidence = EVIDENCE if EVIDENCE['label_words'] is WORDS else {**EVIDENCE, 'label_words': WORDS}
        return SimpleNamespace(evidence=evidence)


def start_fixture_plan():
    # The normal constructor wires model clients; this port only runs the planner.
    p = object.__new__(stages.ProductionStages)
    p.pinned = npp.assets()
    p.replies = p.pinned[2]
    p.writer = copy.Writer(p.pinned)
    p.missing = missing.MissingInfo(p.pinned)
    p.selector = None  # pyright: ignore[reportAttributeAccessIssue]
    p.catalog = lambda: content_model.load_content(ROOT / 'hass' / 'content')
    p.clover = lambda: None
    p._remaining = lambda work: 0
    p.identifier = FixtureIdentifier()  # pyright: ignore[reportAttributeAccessIssue]
    p._photo = lambda sha: b'x'
    p._research = lambda work, maker, town, owner_url, reading: ()
    return p.start_plan(Work('abcd', {
        'texts': ["it's wildflower honey"],
        'slots': {'intake': {'price': '4.00', 'sold_by': 'item', 'price_span': [0, 8], 'private': ['2']}},
        'attachments': ['ab' * 32],
    }, None, None))


def check():
    plan = start_fixture_plan()
    if plan.listing is None:
        return [], ['no-listing']
    private = frozenset({Decimal('2')})
    kept_words = plan.listing['labelWords']
    yes_no = {True: 'yes', False: 'no'}
    rows, findings = [], []
    for position, word in enumerate(WORDS, 1):
        label_ok = private_numbers.problem(word, private, digits_allowed=True) is None
        kept = word in kept_words
        rows.append(f'word {position:02d} label-ok={yes_no[label_ok]} kept={yes_no[kept]}')
        if label_ok and not kept:
            findings.append(f'label-word-dropped {position:02d}')
    return rows, findings


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    try:
        rows, findings = check()
    except Exception:
        # A failed check must not echo exception details or fixture words.
        rows, findings = [], ['check-error']
    for row in rows:
        print(row)
    for reason in findings:
        print(f'FAIL {reason}')
    print('FAIL npp_label_digit_reach' if findings else 'PASS npp_label_digit_reach')
    return 1 if findings else 0


if __name__ == '__main__':
    raise SystemExit(main())
