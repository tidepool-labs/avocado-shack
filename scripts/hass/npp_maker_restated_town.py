#!/usr/bin/env python3
"""Check whether restating a maker in an NPP edit preserves the maker's town."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp
from hass.npp import edits


LISTING = {'name': 'Honey', 'maker': 'Miners', 'makerTown': 'Watsonville'}
SEQUENCES = (
    ('made by Miners',),
    ('made by miners',),
    ('made by Miners, Watsonville',),
    ('made by Bees Co',),
    ('from Bees',),
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    failed = False
    try:
        grammar = edits.Grammar(hass.npp.assets()[1])
    except Exception:
        print('FAIL check-error')
        failed = True
    else:
        for i, texts in enumerate(SEQUENCES):
            try:
                out, _ = edits.apply(LISTING, [edits.read(grammar, t, {}) for t in texts])
            except Exception:
                print('FAIL check-error')
                failed = True
                continue
            maker, town = out['maker'], out.get('makerTown')
            print(f'case {i} maker={maker} town={town or "none"}')
            if maker.casefold() == LISTING['maker'].casefold() and not town:
                print(f'FAIL town-dropped {i}')
                failed = True

    print(f'{"FAIL" if failed else "PASS"} npp_maker_restated_town')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
