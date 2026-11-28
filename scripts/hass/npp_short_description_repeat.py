#!/usr/bin/env python3
"""Report repeated S5 descriptions using only pinned assets and fixture names."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp
from hass.npp import copy


ITEMS = ('Honey', 'Jam', 'Wildflower Honey', 'Apple Butter', 'Big Sur Wildflower Honey')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    failed = False
    try:
        writer = copy.Writer(hass.npp.assets())
    except Exception:
        print('FAIL check-error')
        failed = True
    else:
        for i, item in enumerate(ITEMS):
            others = ()
            for k in range(1, 4):
                prefix = f'item {i} round {k}'
                try:
                    ctx = copy.Context('food', 'pantry', 'raw', item,
                                       'add ' + item.lower(), other_descriptions=others)
                    result = writer.write(ctx, None)
                    if result is None:
                        print(f'{prefix} no-listing')
                        if k == 1:
                            print(f'FAIL first-round-none {i}')
                            failed = True
                        break
                    description = result.text['description']
                    template = result.selections['description']['template_id']
                    print(f'{prefix} template={template}')
                    if copy.words(description) in [copy.words(o) for o in others]:
                        print(f'FAIL repeated-description {i} {k}')
                        failed = True
                    others += (description,)
                except Exception:
                    # An incomplete item must not pass or expose the exception text.
                    print('FAIL check-error')
                    failed = True
                    break

    print(f'{"FAIL" if failed else "PASS"} npp_short_description_repeat')
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
