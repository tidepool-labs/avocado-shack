#!/usr/bin/env python3
"""Check the new-maker key produced by Hass without opening a live editor."""

import argparse
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import claims, label_reader
from hass.npp import copy, stages


NAMES = ['Etto Farm', 'Café Ñandú', 'Ελιά Farm', '東京農園', 'Øster Farm',
         "D'Arcy & Sons", 'Ferme Bœuf']


class RecordingEditor:
    def __init__(self):
        self.ops = []

    def candidate(self, ops):
        self.ops.extend(ops)
        return {'result': 'refused'}


class FixtureWriter:
    def write(self, ctx, selector):
        return copy.Copy({'name': 'N', 'description': 'D.', 'imageAlt': 'A', 'story': 'S.'}, {}, False, ())


def check_name(ps, finance, index, name):
    context = copy.Context('food', 'pantry', 'raw', 'Honey', '', maker_name=name, town='Arroyo Grande')
    editor = ps.c.editor
    editor.ops.clear()
    try:
        accepted = label_reader.identity_text('brand', name) == name
        ps._candidate(context, {}, finance, {}, None, True, '', 'ab' * 32, None)
        maker = next((op for op in editor.ops if op['op'] == 'maker.add'), None)
        key = maker['args']['key'] if maker is not None else ''
        print(f"slug {index} accepted={'yes' if accepted else 'no'} key={key or '-'}")
        if maker is None:
            return f'no-maker-op {index}'
        if accepted:
            if not key:
                return f'key-empty {index}'
            if any(letter.isalpha() and not 'a' <= letter <= 'z' for letter in claims.fold(name)):
                return f'key-drops-letters {index}'
    except Exception:
        # Report an incomplete check without leaking exception text.
        return 'check-error'
    return None


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    ps = object.__new__(stages.ProductionStages)
    # The production constructor and writer are deliberately bypassed.
    setattr(ps, 'writer', FixtureWriter())
    ps.c = SimpleNamespace(editor=RecordingEditor())
    finance = SimpleNamespace(selling_price='4.00 each')

    failed = False
    for index, name in enumerate(NAMES):
        reason = check_name(ps, finance, index, name)
        if reason:
            print(f'FAIL {reason}')
            failed = True
    print(f"{'FAIL' if failed else 'PASS'} npp_new_maker_key_slug")
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
