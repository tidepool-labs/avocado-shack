#!/usr/bin/env python3
"""Check offline whether S10 asks about names S3 recognizes as duplicates."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import npp
from hass.content_model import load_content
from hass.npp import missing, private_numbers
from hass.npp.job import Work
from hass.npp.reply import Stages


POSITIONS = (1, 2, 3, 4)
EXTRA = ('Zzyzx Fixture Jam',)
TOOL = 'npp_rename_duplicate_check'


def finish(failed):
    print(f"{'FAIL' if failed else 'PASS'} {TOOL}")
    return int(failed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else list(argv)
    if args == ['--']:
        parser.error('unrecognized arguments: --')
    parser.parse_args(args)

    try:
        content = load_content(ROOT / 'hass' / 'content')
        active = content.active_products()
        invalid = [k for k in POSITIONS if not 1 <= k <= len(active)]
        if invalid:
            for _ in invalid:
                print('FAIL position-missing')
            return finish(True)
        names = [active[k - 1]['name'] for k in POSITIONS] + list(EXTRA)
        st = Stages(npp.assets(), start=None, render=None)
    except Exception:
        print('FAIL check-error')
        return finish(True)

    failed = False
    yes_no = ('no', 'yes')
    for pos, name in enumerate(names, 1):
        try:
            words = private_numbers.finance('call it ' + name).public_words
            work = Work('abcd', {'texts': ['x', words], 'slots': {'intake': {}},
                                 'attachments': ['ab' * 32]},
                        {'listing_json': json.dumps({'name': 'Wildflower Honey', '_texts': 1})}, None)
            plan = st.edit(work)
            renamed = (plan.listing or {}).get('name') == name
            duplicate = bool(missing._duplicates(name, content.products, content.makers, None))
            asked = any(qid == 'duplicate' for qid, _ in plan.questions)
        except Exception:
            print('FAIL check-error')
            failed = True
            continue
        print(f'rename {pos:02d} renamed={yes_no[renamed]} duplicate={yes_no[duplicate]} asked={yes_no[asked]}')
        if renamed and duplicate and not asked:
            print(f'FAIL rename-unasked {pos:02d}')
            failed = True
    return finish(failed)


if __name__ == '__main__':
    raise SystemExit(main())
