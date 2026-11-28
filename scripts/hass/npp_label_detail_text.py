#!/usr/bin/env python3
"""Check the pinned NPP label-detail and claim decisions on offline fixtures."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import label_reader


CASES = [
    ('Wildflower   honey from the hills', 400),
    ('Only 4 dollars', 400),
    ('Price: ask', 400),
    ('€3 jar', 400),
    ('line one\nline two', 400),
    ('unknown', 400),
    ('Not printed.', 400),
    ('Certified organic', 400),
    ('xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', 40),
    ('Raw honey\u2028unfiltered', 400),
    (12, 400),
    ('Cold pressed', 400),
]
MUST_NONE = (1, 2, 3, 4, 5, 6, 8, 9, 10)
EXPECTED = (
    "case 0 text='Wildflower honey from the hills' claim=no",
    'case 1 text=None claim=no',
    'case 2 text=None claim=no',
    'case 3 text=None claim=no',
    'case 4 text=None claim=no',
    'case 5 text=None claim=no',
    'case 6 text=None claim=no',
    "case 7 text='Certified organic' claim=yes",
    'case 8 text=None claim=no',
    'case 9 text=None claim=no',
    'case 10 text=None claim=no',
    "case 11 text='Cold pressed' claim=yes",
)


def main(argv=None):
    # This diagnostic has no arguments, including the automatic help flags.
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    for i, (value, limit) in enumerate(CASES):
        try:
            text = label_reader.detail_text(value, limit)
            claim = 'yes' if text and label_reader.is_claim(text) else 'no'
        except Exception:
            print('FAIL check-error')
            failed = True
            break

        line = f'case {i} text={text!r} claim={claim}'
        print(line)
        if i in MUST_NONE and text is not None:
            print(f'FAIL unsafe-detail-kept {i}')
            failed = True
        if line != EXPECTED[i]:
            print(f'FAIL detail-changed {i}')
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_label_detail_text")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
