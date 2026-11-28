#!/usr/bin/env python3
"""Compare the real S4 and S5 gates on offline quotes with injected entailment."""

import argparse
from html import escape
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import maker_site
from hass.npp import assets, copy, research


NAME = 'Fixture Farm'
URL = 'https://fixture.invalid/'
RETRIEVED = '2026-11-21'
PHRASES = (
    'grows no-spray greens',
    'cannot stop baking',
    'is not small',
    'will open a shop',
    "won't use sprays",
    'makes non-GMO honey',
    'sold honey at markets since 1990',
    'formerly made cheese',
    'makes honey that may contain nuts',
    'makes No-Knead bread',
    'has a willow tree',
    'is a family farm',
    'makes honey that is never heated',
    'makes unsold-out jam',
)
MARKER_REFUSAL = 'negation-past-or-hedge-marker'
TRAILER = 'npp_hedge_marker_parity'


def s4_fact(pinned, row):
    quote = row['quote']
    page = research.parse_page(
        URL, RETRIEVED, f'<head><title>{NAME}</title></head><body><h1>{NAME}</h1>'
        f'<p>{escape(quote)}</p><footer>Copyright 2026 {NAME}</footer></body>',
    )
    calls = []

    def checked_address(url):
        if url != URL:
            raise AssertionError('unexpected fixture address')
        return URL

    def fetch(url, _seconds):
        calls.append('fetch')
        checked_address(url)
        return page

    def search(*_args):
        calls.append('search')
        raise AssertionError('unexpected search')

    def extract(name, visible, _seconds):
        calls.append('extract')
        if (name, visible) != (NAME, {URL: (NAME, quote)}):
            raise AssertionError('incorrect extraction input')
        return {'facts': [dict(row)]}

    def verify(name, slot, value, supplied_quote, _seconds):
        calls.append('verify')
        if (name, slot, value, supplied_quote) != (NAME, row['slot'], row['value'], quote):
            raise AssertionError('incorrect verification input')
        return 'supports'

    with patch.object(maker_site, 'check_address', new=checked_address):
        result = research.research(
            pinned, search=search, fetch=fetch, extract=extract, verify=verify,
            owner_maker=NAME, owner_url=URL, clock=lambda: 0.0,
        )

    story = result.story_facts
    audit = result.receipt['facts']
    if (story == () and audit == [dict(row, verifier=None, kept=False, reason=MARKER_REFUSAL)]
            and calls == ['fetch', 'extract']):
        return None
    if (len(story) == 1 and audit == [dict(row, verifier='supports', kept=True, reason='verified')]
            and calls == ['fetch', 'extract', 'verify']):
        fact = story[0]
        fact_id = fact['id']
        if isinstance(fact_id, str) and fact_id and fact == dict(row, id=fact_id, retrieved=RETRIEVED):
            return fact
    raise ValueError('invalid S4 result')


def compare(pinned, writer, phrase):
    row = dict(slot='makes', value='honey', url=URL, quote=f'{NAME} {phrase}, alongside honey.')
    kept = s4_fact(pinned, row)
    # Only a confirmed marker refusal gets an S5-only counterfactual.
    source = kept if kept is not None else dict(row, id='official-makes')
    fact = copy.Fact(**{key: source[key] for key in ('id', 'slot', 'value', 'url', 'quote')},
                     verdict='supports')
    ctx = copy.Context('food', 'pantry', 'basic', 'Honey', maker_name=NAME, facts=(fact,))
    bindings = writer.bindings(ctx, 'story')
    if not isinstance(bindings, dict) or ('makes' in bindings and bindings['makes'] != ('honey', fact.id)):
        raise ValueError('invalid S5 binding')
    return kept is not None, 'makes' in bindings


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    findings = []
    controls = {2: (False, False), 10: (True, True)}
    control_broken = False
    try:
        pinned = assets()
        writer = copy.Writer(pinned)
    except Exception:
        findings.append('check-error')
    else:
        for index, phrase in enumerate(PHRASES):
            try:
                s4, s5 = compare(pinned, writer, phrase)
            except Exception:
                # Never print raw stage exceptions or certify an incomplete run.
                if 'check-error' not in findings:
                    findings.append('check-error')
                continue
            print(f'hedge {index} s4={"keep" if s4 else "refuse"} s5={"keep" if s5 else "refuse"}')
            if s4 and not s5:
                findings.append(f's5-stricter {index}')
            if index in controls and (s4, s5) != controls[index]:
                control_broken = True
    if control_broken:
        findings.append('control-broken')
    for finding in findings:
        print(f'FAIL {finding}')
    print(f'{"FAIL" if findings else "PASS"} {TRAILER}')
    return int(bool(findings))


if __name__ == '__main__':
    sys.exit(main())
