#!/usr/bin/env python3
"""Check that product_claims.sanitize cuts unsupported claims from a new listing.

Offline and read-only: it feeds nine made-up listings to the pure repo function
and compares the resulting listing with the pinned answers.
"""

import argparse
import collections  # noqa: F401  (named in the unit's import list)
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import product_claims

# (name, description, shelf, label claims, owner texts, word that must not stay public)
CASES = [
    ('Wildflower Honey', 'Wildflower honey from Cedar Row Apiary.', 'pantry', [], [], ''),
    ('Wildflower Honey', 'Wildflower honey. It cures colds.', 'pantry', [], [], 'cure'),
    ('Organic Wildflower Honey', 'Organic honey.', 'pantry', [], [], 'organic'),
    ('Wildflower Honey', 'Certified organic honey.', 'pantry', ['Certified organic'], [], ''),
    ('Organic Honey', 'Organic honey from the farm.', 'pantry', [], ['it is organic honey'], ''),
    ('Claw Hammer', 'A hammer that cures colds.', 'general', [], [], 'cure'),
    ('Wildflower Honey', 'Call 000-555-0100 for honey.', 'pantry', [], [], '555'),
    ('Wildflower Honey', 'Wildflower honey, gluten free and raw.', 'pantry', [], [], 'gluten'),
    ('Wildflower Honey', 'Award winning honey.', 'pantry', [], [], 'award'),
]
MUST_CUT = (1, 2, 5, 6, 7, 8)

# Measured at c8cdcc95. Case 0 wraps the brand inside the description, and case 7
# keeps 'raw' while cutting 'gluten free'; the owner decides whether that wording is wanted.
EXPECTED = [
    "case 0 label=['Cedar Row Apiary'] name='Wildflower Honey' "
    "description='Wildflower honey from Label says: \\u201cCedar Row Apiary\\u201d.' dropped=[]",
    "case 1 label=['Cedar Row Apiary'] name='Wildflower Honey' "
    "description='Wildflower honey.' dropped=['It cures colds.']",
    "case 2 label=['Cedar Row Apiary'] name='New item' "
    "description='New item' dropped=['Organic Wildflower Honey', 'Organic honey.']",
    "case 3 label=['Cedar Row Apiary', 'Certified organic'] name='Wildflower Honey' "
    "description='Label says: \\u201cCertified organic\\u201d honey.' dropped=[]",
    "case 4 label=['Cedar Row Apiary'] name='Organic Honey' "
    "description='Organic Honey' dropped=['Organic honey from the farm.']",
    "case 5 label=['Cedar Row Apiary'] name='Claw Hammer' "
    "description='Claw Hammer' dropped=['A hammer that cures colds.']",
    "case 6 label=['Cedar Row Apiary'] name='Wildflower Honey' "
    "description='Wildflower Honey' dropped=['Call 000-555-0100 for honey.']",
    "case 7 label=['Cedar Row Apiary'] name='Wildflower Honey' "
    "description='Wildflower honey raw.' dropped=['gluten free']",
    "case 8 label=['Cedar Row Apiary'] name='Wildflower Honey' "
    "description='Wildflower Honey' dropped=['Award winning honey.']",
]

NAME = 'npp_label_claim_sanitize'
ATTRIBUTION = 'Label says: \u201c[^\u201d]*\u201d'


def public_text(slots):
    text = ' '.join(str(slots.get(k) or '') for k in ('name', 'maker', 'description', 'image_alt'))
    return re.sub(ATTRIBUTION, '', text).casefold()


def run_case(index, case):
    name, description, shelf, label, owner, word = case
    slots = {'name': name, 'maker': 'Cedar Row Apiary', 'description': description,
             'image_alt': name, 'shelf': shelf, 'photo': 'a' * 64, 'intake': {},
             '_owner_texts': list(owner)}
    details = {'brand': 'Cedar Row Apiary', 'claims': list(label), 'category': shelf}
    got = product_claims.sanitize(slots, details)
    line = ('case %d label=%s name=%s description=%s dropped=%s'
            % (index, ascii(got), ascii(slots['name']), ascii(slots['description']),
               ascii(slots['intake']['dropped_claims'])))
    findings = []
    if index in MUST_CUT and word and word in public_text(slots):
        findings.append('FAIL claim-kept-public %d' % index)
    if line != EXPECTED[index]:
        findings.append('FAIL listing-changed %d' % index)
    return line, findings


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    failed = False
    for index, case in enumerate(CASES):
        try:
            line, findings = run_case(index, case)
        except Exception:
            print('FAIL check-error')
            failed = True
            break
        print(line)
        for finding in findings:
            print(finding)
            failed = True
    print(('FAIL ' if failed else 'PASS ') + NAME)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
