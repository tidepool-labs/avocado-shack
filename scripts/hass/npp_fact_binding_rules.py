#!/usr/bin/env python3
"""Check which synthetic maker facts S5 binds into a story, offline."""

import argparse
from dataclasses import replace
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.npp import copy


BASE = copy.Fact('official-makes', 'makes', 'honey', 'https://ettofarm.example/',
                 'Etto Farm makes honey.', 'supports')
CASES = (
    ('ok', (BASE,), True),
    ('bad-id', (replace(BASE, id='1bad'),), False),
    ('refutes', (replace(BASE, verdict='refutes'),), False),
    ('empty-quote', (replace(BASE, quote=''),), False),
    ('value-not-said', (replace(BASE, value='jam'),), False),
    ('hedged', (replace(BASE, quote='Etto Farm may make honey.'),), False),
    ('two-same-slot', (BASE, replace(BASE, id='official-jam', value='jam',
                                    quote='Etto Farm makes jam.')), False),
    ('dup-id', (BASE, replace(BASE, slot='nature', value='farm',
                              quote='Etto Farm is a farm.')), False),
    ('owner-not-said', (replace(BASE, source='owner_words',
                                quote='Etto Farm also makes honey.'),), False),
    ('owner-said', (replace(BASE, source='owner_words',
                            quote='Etto Farm makes honey'),), True),
    ('http-url', (replace(BASE, url='http://ettofarm.example/'),), True),
    ('bad-url', (replace(BASE, url='ftp://x'),), False),
)


def context(facts):
    return copy.Context('food', 'pantry', 'raw', 'Honey',
                        'made by Etto Farm\nEtto Farm makes honey',
                        maker_name='Etto Farm', facts=facts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    argv = sys.argv[1:] if argv is None else argv
    parser.parse_args(argv)
    if argv:  # A bare option terminator is not a supported invocation either.
        parser.error('no arguments accepted')

    try:
        writer = copy.Writer(npp.assets())
    except Exception:
        print('FAIL check-error')
        print('FAIL npp_fact_binding_rules')
        return 1

    failed = False
    for name, facts, expected in CASES:
        try:
            bound = 'makes' in writer.bindings(context(facts), 'story')
        except Exception:
            print('FAIL check-error')
            failed = True
            continue
        print(f"fact {name} makes={'yes' if bound else 'no'}")
        if bound != expected:
            reason = 'fact-bound' if bound else 'fact-dropped'
            print(f'FAIL {reason} {name}')
            failed = True

    print('FAIL npp_fact_binding_rules' if failed else 'PASS npp_fact_binding_rules')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
