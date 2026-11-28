#!/usr/bin/env python3
"""Check the NPP selector's fallback wording with offline reply fixtures."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import interpreter_local, npp
from hass.npp import copy


GOOD = {
    'name': {'template_id': 'name-item'},
    'description': {
        'template_id': 'desc-food-plain',
        'phrase_ids': ['food-open-1', 'food-use-1', 'food-close-1'],
    },
    'imageAlt': {'template_id': 'alt-photo'},
}


def _response(body, status=200):
    def reply(_url, _body, _headers, _timeout):
        return status, body
    return reply


def wrap(content, status=200):
    return _response(json.dumps({'choices': [{'message': {'content': content}}]}).encode(), status)


def _raises(error):
    def reply(_url, _body, _headers, _timeout):
        raise error
    return reply


def _replies():
    # Distinguish adapter rejection (none) from parsed selections the writer ignores.
    return (
        ('good', 'good', wrap(json.dumps(GOOD))),
        ('status500', 'none', wrap(json.dumps(GOOD), 500)),
        ('dup-top', 'none', wrap('{"name": {"template_id": "name-item"}, "name": {"template_id": "name-item"}}')),
        ('dup-nested', 'none', wrap('{"name": {"template_id": "name-item", "template_id": "name-item-size"}}')),
        ('not-json', 'none', wrap('hello')),
        ('no-choices', 'none', _response(b'{"x": 1}')),
        ('raw-not-json', 'none', _response(b'nope')),
        ('oserror', 'none', _raises(OSError())),
        ('timeout', 'none', _raises(TimeoutError())),
        ('failed', 'none', _raises(interpreter_local._Failed('x'))),
        ('list', 'ignored', wrap('[1, 2]')),
        ('extra-key', 'ignored', wrap(json.dumps({**GOOD, 'price': {'template_id': 'x'}}))),
        ('unknown-template', 'ignored', wrap('{"name": {"template_id": "nope"}}')),
    )


def _findings():
    try:
        writer = copy.Writer(npp.assets())
        ctx = copy.Context('food', 'pantry', 'raw', 'Wildflower Honey', 'add wildflower honey')
        defaults = writer.write(ctx, None).selections
    except Exception:
        yield 'check-error'
        return

    for name, group, reply in _replies():
        try:
            select = copy.codex_selector(transport=reply)
            raw = select({'model': 'm-1', 'effort': 'low', 'timeout_s': 5}, 'P', {}, {})
            result = writer.write(ctx, select)
            # Use the existing bad-reply finding for either adapter mismatch;
            # an ignored parsed reply must not be silently rejected as None.
            bad_raw = (group == 'none' and raw is not None) or (group == 'ignored' and raw is None)
            if result is None:
                if bad_raw:
                    yield f'bad-reply-used {name}'
                yield f'write-none {name}'
                continue

            raw_kind = {type(None): 'none', dict: 'dict', list: 'list'}.get(type(raw))
            # Scalars have no allowed info-row kind, but still need the checks below.
            if raw_kind is not None:
                print(f"reply {name} raw={raw_kind} basic={'yes' if result.basic else 'no'}")
            if group == 'good':
                if result.basic or any(
                    result.selections.get(field, {}).get('template_id') != choice['template_id']
                    for field, choice in GOOD.items()
                ):
                    yield 'good-reply-dropped'
            elif bad_raw or result.selections != defaults or not result.basic:
                yield f'bad-reply-used {name}'
        except Exception:
            yield 'check-error'


def main(argv=None):
    # This check has no options, including help; any supplied argument is an error.
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    for reason in _findings():
        print(f'FAIL {reason}')
        failed = True
    print(f"{'FAIL' if failed else 'PASS'} npp_selector_reply_fallback")
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
