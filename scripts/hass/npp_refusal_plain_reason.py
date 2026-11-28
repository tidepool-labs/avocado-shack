#!/usr/bin/env python3
"""Check the pinned live-gate refusal wording offline."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import live_policy


CASES = [
    'sign-up is on',
    'undo of a change that never went live',
    'not live: maker.add without a new product',
    'not live: product.edit',
    'not live: maker.hide',
    'not live: zzz.fixture',
    'protected sentences: prices',
    'protected sentences: unchecked claims',
    'protected sentences: zzz',
    'protected operation: hike.repeat',
    'protected field: events.trailId',
    'protected field: events.distance',
    'protected field: products.brand',
    'protected field: makers.url',
    'protected field: club.signupLimit',
    'more than 10 records',
    'fixture nonsense',
]

EXPECTED = '''case 0 why="the website can't take sign-ups yet" next="I can post it with no sign-up button and the guest limit written on the page, so people ask you at the shop. Say “no sign-up” and I'll redo it that way."
case 1 why='it takes back a change that never went on the website from chat' next=None
case 2 why='it adds a maker on its own, without a new product' next='Tell me the new product from this maker, and I can add them together.'
case 3 why="it is a kind of change I can't put on the website from chat yet" next=None
case 4 why='it takes a maker off the website' next=None
case 5 why="it is a kind of change I can't put on the website from chat yet" next=None
case 6 why="it mentions a price, and I can't check that from chat" next='Send it again without that part, and I can put the rest on the website.'
case 7 why="it mentions a claim I can't check, and I can't check that from chat" next='Send it again without that part, and I can put the rest on the website.'
case 8 why="it mentions a claim I can't check, and I can't check that from chat" next='Send it again without that part, and I can put the rest on the website.'
case 9 why='it copies a hike' next=None
case 10 why="a link to a saved route can't go on the website from chat yet" next="Say “without the route” and I'll post it without that link."
case 11 why="how far it is can't go on the website from chat yet" next='Send it again without that part, and I can put the rest on the website.'
case 12 why="the brand or maker of a product that is already on the website can't be changed from chat" next=None
case 13 why="a maker's town or website link can't be changed from chat" next=None
case 14 why="the hike club settings can't be changed from chat" next=None
case 15 why='it changes too many things at once' next='Send it as a few smaller changes, and I can put each one on the website.'
case 16 why="I couldn't read the change" next='Could you say it another way?'
'''.splitlines()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    failed = False
    for i, reason in enumerate(CASES):
        try:
            why, nxt = live_policy._plain_reason(reason)
        except Exception:
            print('FAIL check-error')
            failed = True
            break

        line = f'case {i} why={why!r} next={nxt!r}'
        print(line)
        if not why or 'graham' in why.casefold() or (nxt is not None and 'graham' in nxt.casefold()):
            print(f'FAIL unplain-refusal {i}')
            failed = True
        if line != EXPECTED[i]:
            print(f'FAIL reason-changed {i}')
            failed = True

    print(f'{"FAIL" if failed else "PASS"} npp_refusal_plain_reason')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
