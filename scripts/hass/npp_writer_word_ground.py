#!/usr/bin/env python3
"""Check the writer's word grounding on nine synthetic descriptions."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import newitem


ALLOWED = 'wildflower honey from cedar row apiary'
VOCAB = frozenset({'spread', 'toast', 'warm', 'spoon', 'bread', 'tea'})
OPENERS = frozenset({'spoon', 'tri', 'try', 'keep'})
CASES = [
    'Wildflower honey from Cedar Row Apiary.',
    'Raw wildflower honey from Cedar Row Apiary.',
    'Wildflower honey from Cedar Row Apiary. Spoon it onto warm toast.',
    'Wildflower honey from Cedar Row Apiary. It has butter.',
    'Wildflower honey from Cedar Row Apiary. Spoon it onto toast, made with lavender.',
    'Wildflower honey from the hills.',
    'Award honey from Cedar Row Apiary.',
    'Wildflower honey. Keep it warm.',
    '',
]
MUST_FLAG = (1, 3, 4, 5, 6)
EXPECTED = (
    'case 0 bad=[]',
    "case 1 bad=['raw']",
    'case 2 bad=[]',
    "case 3 bad=['assertion: It has butter.']",
    "case 4 bad=['made', 'lavender', 'made with']",
    "case 5 bad=['hills']",
    "case 6 bad=['award']",
    "case 7 bad=['keep']",
    'case 8 bad=[]',
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    failed = False
    for index, text in enumerate(CASES):
        try:
            bad = newitem.ungrounded_claims(text, ALLOWED, VOCAB, OPENERS)
        except Exception:
            print('FAIL check-error')
            failed = True
            break

        line = f'case {index} bad={bad!r}'
        print(line)
        if index in MUST_FLAG and not bad:
            print(f'FAIL unsaid-word-passed {index}')
            failed = True
        if line != EXPECTED[index]:
            print(f'FAIL words-changed {index}')
            failed = True

    print(f'{"FAIL" if failed else "PASS"} npp_writer_word_ground')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
