#!/usr/bin/env python3
"""Check the polish label-word verdicts offline using synthetic scores and boxes."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import photo_polish


CASES = [
    ('changed', [('HONEY', 0.9), ('RAW', 0.8)], None),
    ('changed', [('HONEY', 0.2)], None),
    ('changed', [('HONEY', None)], None),
    ('changed', [('HONEY', 0.4)], {'HONEY'}),
    ('changed', [('HONEY', 0.4)], {'HONE!'}),
    ('changed', [('MONEY', 0.4)], {'RAW', 'WILD'}),
    ('changed', [('RAW', 0.4)], {'WILD'}),
    ('removed', [('HONEY', 0.9, (10, 10, 50, 12))], []),
    ('removed', [('HONEY', 0.1, (10, 10, 50, 12))], [('HONEY', (10, 10, 50, 12))]),
    ('removed', [('HONEY', 0.4, (10, 10, 50, 12))], [('HONEY', (12, 11, 50, 12))]),
    ('removed', [('HONEY', 0.4, (10, 10, 50, 12))], [('HONEY', (300, 200, 50, 12))]),
    ('removed', [('HONEY', 0.4, (10, 10, 50, 12)), ('HONEY', 0.4, (10, 40, 50, 12))],
     [('HONEY', (10, 10, 50, 12))]),
    ('removed', [('AB', 0.0)], []),
]

MUST_FLAG = (1, 5, 8, 10, 11)
EXPECTED = (
    'case 0 changed=no',
    'case 1 changed=yes',
    'case 2 changed=no',
    'case 3 changed=no',
    'case 4 changed=no',
    'case 5 changed=yes',
    'case 6 changed=no',
    'case 7 removed=no',
    'case 8 removed=yes',
    'case 9 removed=no',
    'case 10 removed=yes',
    'case 11 removed=yes',
    'case 12 removed=no',
)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    checks = {'changed': photo_polish.text_changed, 'removed': photo_polish.text_removed}
    failed = False
    for i, (kind, a, b) in enumerate(CASES):
        try:
            flagged = checks[kind](a, b)
        except Exception:
            print('FAIL check-error')
            failed = True
            break

        line = f"case {i} {kind}={'yes' if flagged else 'no'}"
        print(line)
        if i in MUST_FLAG and not flagged:
            print(f'FAIL label-change-passed {i}')
            failed = True
        if line != EXPECTED[i]:
            print(f'FAIL label-changed {i}')
            failed = True

    print('FAIL npp_polish_label_words' if failed else 'PASS npp_polish_label_words')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
