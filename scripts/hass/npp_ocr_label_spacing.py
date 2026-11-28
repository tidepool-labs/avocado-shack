#!/usr/bin/env python3
"""Check the photo stage's OCR label-word handoff with an offline fixture."""

import argparse
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import content_model, npp
from hass.npp import copy, missing, picture, private_numbers, stages
from hass.npp.job import Work

OCR = 'Wildflower\nHoney\n12\noz\nNet  Wt 12 oz\n16 fl oz'
WORDS = ('12 oz', 'Net Wt 12 oz', '16 fl oz', 'Honey')
SHA = 'ab' * 32


def _source_label_words():
    port = object.__new__(stages.ProductionStages)
    port.pinned = npp.assets()
    port.replies = port.pinned[2]
    port.writer = copy.Writer(port.pinned)
    port.missing = missing.MissingInfo(port.pinned)
    # This fixture has no selector client; the local picture step doesn't use one.
    port.selector = None  # pyright: ignore[reportAttributeAccessIssue]
    port.catalog = lambda: content_model.load_content(ROOT / 'hass/content')
    port.clover = lambda: None
    port._remaining = lambda work: 0
    port.c = SimpleNamespace(settings={})
    port._photo = lambda sha: b'x'

    received = None

    def choose(_settings, _sha, **kwargs):
        nonlocal received
        received = kwargs
        return picture.FrozenPicture('raw', 'p', SHA)

    with patch.object(picture, 'read_text', lambda data: OCR), patch.object(picture, 'choose', choose):
        port._picture(Work('abcd', {'attachments': [SHA]}, None, None),
                      {'photo': SHA, 'labelWords': list(WORDS), 'personOrScreen': False},
                      frozenset(), local=True)
    return None if received is None else received['source_label_words']


def _check():
    passed_words = _source_label_words()
    if passed_words is None:
        return [], ['not-reached']
    rows, findings = [], []
    for position, word in enumerate(WORDS, 1):
        numbers = frozenset(amount for value in private_numbers.values(word) for amount in value.amounts)
        confirmed = private_numbers.picture_problem(word, OCR, [word], numbers) is None
        passed = word in passed_words
        rows.append(f"word {position:02d} confirmed={'yes' if confirmed else 'no'} passed={'yes' if passed else 'no'}")
        if confirmed and not passed:
            findings.append(f'label-word-lost {position:02d}')
    return rows, findings


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    try:
        rows, findings = _check()
    except Exception:
        # Report an incomplete check without leaking the underlying exception text.
        rows, findings = [], ['check-error']
    for row in rows:
        print(row)
    for reason in findings:
        print(f'FAIL {reason}')
    print(f"{'FAIL' if findings else 'PASS'} npp_ocr_label_spacing")
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
