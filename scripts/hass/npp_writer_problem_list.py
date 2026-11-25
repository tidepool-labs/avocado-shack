#!/usr/bin/env python3
"""Check that newitem.writer_problems refuses a model-written description for every unsaid word, claim, negation, number or hidden product's wording (offline, fixtures only)."""

import argparse
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hass import newitem  # noqa: E402

PRODUCTS = [
    {'id': 'p-1', 'status': 'active', 'name': 'Orange Blossom Honey',
     'description': 'Orange blossom honey from Harbor Lane Farm. Spoon it onto warm toast. Stir a little into tea.'},
    {'id': 'p-2', 'status': 'hidden', 'name': 'Lavender Honey',
     'description': 'Lavender honey from Old Mill. Drizzle it over ice cream.'},
]
CONTENT = types.SimpleNamespace(products=PRODUCTS)
FACTS = {'name': 'Wildflower Honey', 'maker': 'Cedar Row Apiary', 'place': 'Fillmore', 'kind': 'honey'}
MAKER = {'name': 'Cedar Row Apiary', 'place': 'Fillmore, CA'}
MESSAGE = 'new wildflower honey from Cedar Row Apiary in Fillmore'

CASES = [
    'Wildflower honey from Cedar Row Apiary in Fillmore. Spoon it onto warm toast.',
    'Raw wildflower honey from Cedar Row Apiary.',
    'Wildflower honey from Cedar Row Apiary. Drizzle it over ice cream.',
    'Wildflower honey from Cedar Row Apiary. Spoon it onto toast, never cold.',
    'Wildflower honey from Cedar Row Apiary. Harvested in spring.',
    'Wildflower honey from Cedar Row Apiary. Spoon 2 onto toast.',
    'Organic wildflower honey from Cedar Row Apiary.',
    'Wildflower honey from Cedar Row Apiary. Stir a little into tea.',
    'Wildflower honey from Cedar Row Apiary. Warm toast loves it.',
    '',
]

# Cases whose text must never come back with no problem at all.
MUST_FLAG = (1, 2, 3, 4, 5, 6, 8)

# The informational lines as measured with the repo's own words (pinned).
EXPECTED = [
    "case 0 problems=[]",
    "case 1 problems=['sentence 1 says more than the facts: raw']",
    "case 2 problems=['sentence 2 uses words the shop never uses: drizzle, over, ice, cream', "
    "'sentence 2 is not a serving suggestion like the others']",
    "case 3 problems=['a negation (the facts are written plainly)', "
    "'sentence 2 uses words the shop never uses: never, cold']",
    "case 4 problems=['claim word he did not affirm: harvested in', "
    "'sentence 2 states origin, ingredient or history: harvested', "
    "'sentence 2 uses words the shop never uses: harvested, spring', "
    "'sentence 2 is not a serving suggestion like the others']",
    "case 5 problems=['sentence 2 uses words the shop never uses: 2']",
    "case 6 problems=['claim word he did not affirm: organic', 'sentence 1 says more than the facts: organic']",
    "case 7 problems=[]",
    "case 8 problems=['sentence 2 uses words the shop never uses: lov', "
    "'sentence 2 is not a serving suggestion like the others']",
    "case 9 problems=[]",
]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    failed = False
    for i, text in enumerate(CASES):
        try:
            got = newitem.writer_problems(text, FACTS, MAKER, MESSAGE, CONTENT)
            line = f"case {i} problems={got!r}"
        except Exception:
            print("FAIL check-error")
            failed = True
            break
        print(line)
        if not got and i in MUST_FLAG:
            print(f"FAIL unchecked-description-passed {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL problems-changed {i}")
            failed = True
    print("FAIL npp_writer_problem_list" if failed else "PASS npp_writer_problem_list")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
