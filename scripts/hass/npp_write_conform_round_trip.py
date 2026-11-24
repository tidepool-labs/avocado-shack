#!/usr/bin/env python3
"""Check offline that S7 rebuilds the listing copy S5 returns."""

import argparse
from itertools import product
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import content_model, npp
from hass.npp import copy


KINDS = ('food', 'drink', 'fresh', 'non-food')
VARIANTS = ('raw', 'house')
TOOL = 'npp_write_conform_round_trip'


def first_selector(writer):
    """Choose the first offered template and supply only its required IDs."""
    def select(_step, _prompt, schema, options):
        choices = {}
        for field, offered in options['templates'].items():
            if not offered:
                continue
            template = writer.templates[offered[0]]
            required = schema['properties'][field]['required']
            choice = {'template_id': offered[0]}
            if 'phrase_ids' in required:
                banks = (token[7:] for token in copy.TOKEN.findall(template['text'])
                         if token.startswith('phrase:'))
                choice['phrase_ids'] = [
                    next(phrase_id for phrase_id in options['phrase_ids']
                         if writer.phrases[phrase_id]['bank'] == bank)
                    for bank in banks
                ]
            if 'fact_ids' in required:
                refs = options['fact_ids']
                choice['fact_ids'] = sorted({refs[slot] for slot in template['slots'] if slot in refs})
            choices[field] = choice
        return choices
    return select


def cases():
    for kind, category, variant in product(KINDS, content_model.CATEGORIES, VARIANTS):
        yield copy.Context(kind, category, variant, 'Wildflower Honey', 'add wildflower honey'), False
    yield copy.Context(
        'food', 'pantry', 'raw', 'Wildflower Honey', 'new honey made by Etto Farm in Arroyo Grande',
        maker_name='Etto Farm', town='Arroyo Grande', size_text='12 oz',
        source_read='ETTO FARM WILDFLOWER HONEY 12 oz',
        facts=(
            copy.Fact('official-makes', 'makes', 'honey', 'https://etto.example/',
                      'Etto Farm makes honey.', 'supports'),
            copy.Fact('official-founded', 'founded', '1950', 'https://etto.example/',
                      'Etto Farm was founded in 1950.', 'supports'),
        ),
    ), True


def check(writer, ctx, story, label, select):
    case = f'{ctx.kind} {ctx.category} {ctx.variant} {label}' + (' story' if story else '')
    try:
        result = writer.write(ctx, select)
    except Exception:
        return False, ['check-error']
    if result is None:
        return False, [f'no-copy {case}']

    findings = []
    try:
        conforms = writer.conform(result.text, result.selections, ctx)
        if not conforms:
            findings.append(f'nonconform {case}')
    except Exception:
        conforms = False
        findings.append('check-error')
    if story and not result.text.get('story'):
        findings.append(f'story-missing {label}')
    return conforms, findings


def main(argv=None):
    parser = argparse.ArgumentParser(prog=TOOL, description=__doc__, add_help=False)
    parser.parse_args(argv)

    writes = conform = 0
    findings = []
    try:
        writer = copy.Writer(npp.assets())
    except Exception:
        findings.append('check-error')
    else:
        selectors = (('none', None), ('first', first_selector(writer)))
        for ctx, story in cases():
            for label, select in selectors:
                writes += 1
                conforms, problems = check(writer, ctx, story, label, select)
                conform += int(conforms)
                findings.extend(problems)

    for reason in findings:
        print(f'FAIL {reason}')
    print(f'matrix writes={writes} conform={conform}')
    print(f'{"FAIL" if findings else "PASS"} {TOOL}')
    return int(bool(findings))


if __name__ == '__main__':
    sys.exit(main())
