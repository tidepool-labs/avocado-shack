#!/usr/bin/env python3
"""Compare the offline S4 maker-fact check and S5 story binding."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.npp import copy, research


FACTS = (
    ('founded', '1990', '2026-11-21'),
    ('founded', '2026', '2026-11-21'),
    ('founded', '2027', '2027-01-15'),
    ('makes', 'jam', '2026-11-21'),
    ('makes', 'jams and jellies', '2026-11-21'),
    ('makes', 'jams, jellies and honey', '2026-11-21'),
    ('makes', 'small-batch hot sauce', '2026-11-21'),
    ('nature', 'family farm', '2026-11-21'),
    ('nature', 'co-op', '2026-11-21'),
)
NAME = 'Etto Farm'
URL = 'https://ettofarm.example/'
SCHEMA = 'hass-maker-research/facts.schema.json'
SENTENCES = {
    'founded': NAME + ' started in {}.',
    'makes': NAME + ' makes {}.',
    'nature': NAME + ' is a {}.',
}


def _compare(slot, value, day, schema, markers, writer):
    sentence = SENTENCES[slot].format(value)
    markup = ('<html><head><title>Etto Farm</title></head><body><h1>Etto Farm</h1><p>'
              + sentence + '</p><footer>© Etto Farm</footer></body></html>')
    page = research.parse_page(URL, day, markup)
    row = {'slot': slot, 'value': value, 'url': URL, 'quote': sentence}
    kept = research._check(row, {URL: page}, NAME, '', schema, markers) is None
    fact = copy.Fact('official-' + slot, slot, value, URL, sentence, 'supports')
    context = copy.Context('food', 'pantry', 'raw', 'Honey', 'made by Etto Farm',
                           maker_name=NAME, town='Arroyo Grande', facts=(fact,))
    bound = slot in writer.bindings(context, 'story')
    return kept, bound


def _run_checks():
    try:
        pinned = npp.assets()
        schema = json.loads(pinned[1][SCHEMA])
        markers = research._markers(schema)
        writer = copy.Writer(pinned)
    except Exception:
        print('FAIL check-error')
        return False

    passed = True
    for position, (slot, value, day) in enumerate(FACTS, 1):
        try:
            kept, bound = _compare(slot, value, day, schema, markers, writer)
        except Exception:
            print('FAIL check-error')
            passed = False
            continue
        print(f"fact {position:02d} s4={'kept' if kept else 'refused'} "
              f"s5={'bound' if bound else 'unbound'}")
        if kept and not bound:
            print(f'FAIL kept-unbound {position:02d}')
            passed = False
    return passed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    if args:
        parser.error('no arguments accepted')

    passed = _run_checks()
    print(f"{'PASS' if passed else 'FAIL'} npp_story_fact_parity")
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
