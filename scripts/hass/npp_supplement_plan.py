#!/usr/bin/env python3
"""Count a proposed supplement from synthetic, key-only metadata; never record anything.

Usage: python3 scripts/hass/npp_supplement_plan.py METADATA --case 14 --case 16

METADATA is {"base_keys": [...], "cases": {"14": {"complete": true,
"operations": [{"key": "image:<pin SHA>:<input SHA>:0", "max_calls": 2}]}, ...}}.
Use an independent --case list of the exact intended case/variant labels. The producer
must supply the full replay-visible paid-operation base key set (including versioned
hits, excluding local captures), and mark a case complete only when every reachable
paid operation is enumerated. An explicit empty list
means no operations, not an unobserved path. max_calls bounds *all attempts for that
key across the proposed run*, including any retries before a result is cached. Repeat
that same bound for a shared key. Estimates for unobserved keys do not qualify.

WITHIN_CAPS checks the submitted metadata only. It is not a verified census, a replay
pass, or authority to record. Missing identification is outside the ID-only scope.
"""
import argparse
import json
import re
from pathlib import Path


CEILINGS = {'codex': 40, 'images': 4}
# Emitted with every result, WITHIN_CAPS included, so the output alone never reads as a go-ahead.
AUTHORITY = 'none: counts of submitted metadata only; not a census, replay pass or authority to record'
OP_KEY = re.compile(r'(copy|image|s2):[0-9a-f]{64}:[0-9a-f]{64}:(?:0|[1-9][0-9]*)')
CASE = re.compile(r'[0-9]{2}[a-z]?')


class Hold(ValueError):
    """Reasons are fixed codes; never serialize caller data."""


class PlanParser(argparse.ArgumentParser):
    def error(self, message):
        raise Hold('invalid_arguments')


def unique_object(pairs):
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise Hold('invalid_metadata')
    return obj


def operation_kind(key):
    match = OP_KEY.fullmatch(key) if isinstance(key, str) else None
    if not match:
        raise Hold('invalid_metadata')
    return match[1]


def plan(data, scope):
    if len(set(scope)) != len(scope) or not all(CASE.fullmatch(case) for case in scope):
        raise Hold('invalid_scope')
    if not isinstance(data, dict) or set(data) != {'base_keys', 'cases'}:
        raise Hold('invalid_metadata')
    base_keys, cases = data['base_keys'], data['cases']
    if not isinstance(base_keys, list) or not isinstance(cases, dict):
        raise Hold('invalid_metadata')
    for key in base_keys:
        operation_kind(key)
    base = set(base_keys)
    if len(base) != len(base_keys):
        raise Hold('invalid_metadata')
    if set(cases) != set(scope):
        raise Hold('scope_mismatch')

    bounds = {}
    for case in cases.values():
        if (not isinstance(case, dict) or set(case) != {'complete', 'operations'}
                or case['complete'] is not True or not isinstance(case['operations'], list)):
            raise Hold('incomplete_case')
        for operation in case['operations']:
            if not isinstance(operation, dict) or set(operation) != {'key', 'max_calls'}:
                raise Hold('invalid_metadata')
            key, maximum = operation['key'], operation['max_calls']
            operation_kind(key)
            if type(maximum) is not int or maximum < 1:
                raise Hold('unknown_bound')
            if bounds.setdefault(key, maximum) != maximum:
                raise Hold('conflicting_bounds')

    counts: dict[str, int] = dict.fromkeys(('copy', 'image', 's2'), 0)
    calls = dict.fromkeys(CEILINGS, 0)
    for key in bounds.keys() - base:
        kind = operation_kind(key)
        counts[kind] += 1
        calls['images' if kind == 'image' else 'codex'] += bounds[key]
    result = {'status': 'WITHIN_CAPS', 'cases': len(scope), 'exact_base_hits': len(base & bounds.keys()),
              'distinct_missing': counts, 'maximum_calls': calls}
    if counts['s2']:
        result.update(status='HOLD', reason='missing_identification')
    elif any(calls[pool] > limit for pool, limit in CEILINGS.items()):
        result.update(status='HOLD', reason='over_cap')
    return result


def main():
    parser = PlanParser(description='Count a proposed supplement without calling or recording anything.')
    parser.add_argument('metadata', type=Path)
    parser.add_argument('--case', action='append', required=True)
    try:
        args = parser.parse_args()
        data = json.loads(args.metadata.read_bytes(), object_pairs_hook=unique_object)
        result = plan(data, args.case)
    except Hold as error:
        result = {'status': 'HOLD', 'reason': str(error)}
    except (OSError, ValueError, RecursionError):
        result = {'status': 'HOLD', 'reason': 'invalid_metadata'}
    result['recording_authority'] = AUTHORITY
    print(json.dumps(result, sort_keys=True))
    return 2 if result['status'] == 'HOLD' else 0


if __name__ == '__main__':
    raise SystemExit(main())
