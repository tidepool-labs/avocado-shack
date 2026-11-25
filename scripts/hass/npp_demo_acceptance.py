#!/usr/bin/env python3
"""Check completeness of saved private replay evidence, not permission to go live.

REPLAY is run_npp.py's --json report. EVIDENCE is the local bundle producer's
JSON receipt: checkout, replay_sha256 (the report's raw bytes), deliveries
[{id, variant, n, state, png_sha256, attachment_sha256}], and reference_cards
[{id, png_sha256}]. IDs and versions come from the versioned cases; gallery
IDs are strings. The producer must hash the actual PNG and chat attachment
bytes. A gallery render counts only as a reference, never as a confirmed
chat delivery. This checker does not prove attendance, install/rollback,
or approval. Run from the replay pin.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.tests.npp import run_npp  # noqa: E402
from scripts.hass.npp_card_gallery import CASE_IDS  # noqa: E402


def digest(value, width=64):
    return isinstance(value, str) and re.fullmatch(f'[0-9a-f]{{{width}}}', value) is not None


def unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError('duplicate JSON key')
    return result


def decode(raw):
    result = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(result, dict):
        raise ValueError('expected JSON object')
    return result


def expected():
    rows, deliveries = {}, set()
    for case_id, case in run_npp.load_cases().items():
        for variant, view in run_npp.case_views(case):
            key = (case_id, variant)
            if key in rows:
                raise ValueError('duplicate case variant')
            layers = {'conversation' if view['path'] == 'question' else 'card'}
            if run_npp.has_research(view):
                layers.add('research')
                seed = run_npp.owner_seed(view)
                if seed['maker'] and (seed['town'] or seed['url']) and view['expect'].get('research'):
                    layers.add('seed')
            rows[key] = (view['path'], view['terminal'], layers)
            deliveries.update((*key, row['n']) for row in view['expect'].get('versions', [])
                              if row.get('delivered') is True)
    if ({key[0] for key in rows} != set(range(1, 39)) or len(rows) != 49
            or len(deliveries) != 78 or len(set(CASE_IDS)) != 12):
        raise ValueError('unexpected versioned corpus')
    return rows, deliveries


def key_of(row):
    case_id, variant = row['id'], row['variant']
    if type(case_id) is not int or (variant is not None and not isinstance(variant, str)):
        raise ValueError('invalid variant identity')
    return case_id, variant


def covered(items, read_key):
    if not isinstance(items, list) or not all(isinstance(row, dict) for row in items):
        return set(), False
    try:
        keys = [read_key(row) for row in items]
        return set(keys), None not in keys and len(set(keys)) == len(keys)
    except (TypeError, KeyError, ValueError):
        return set(), False


def check(replay_raw, evidence_raw, *, checkout, recording_sha256):
    report, evidence = decode(replay_raw), decode(evidence_raw)
    variants, deliveries = expected()
    cards = set(CASE_IDS)
    summary = report.get('summary')
    fingerprint = summary.get('fingerprint') if isinstance(summary, dict) else None
    reasons = []
    if not (digest(checkout, 40) and evidence.get('checkout') == checkout
            and evidence.get('replay_sha256') == hashlib.sha256(replay_raw).hexdigest()):
        reasons.append('bundle-binding')
    if not (isinstance(summary, dict) and summary.get('preview') is True
            and isinstance(fingerprint, dict) and digest(recording_sha256)
            and fingerprint.get('recorded_sha256') == recording_sha256):
        reasons.append('recorded-renderer-replay-required')

    def passing(row):
        key = key_of(row)
        if key not in variants:
            return None
        path, terminal, layers = variants[key]
        if (row.get('result') == 'pass' and row.get('path') == path and row.get('terminal') == terminal
                and row.get('layers') == dict.fromkeys(layers, 'pass')):
            return key
        return None

    def confirmed(row):
        png = row.get('png_sha256')
        if (row.get('state') == 'confirmed' and type(row.get('n')) is int and digest(png)
                and row.get('attachment_sha256') == png):
            return (*key_of(row), row['n'])
        return None

    def drawn(row):
        card_id = row.get('id')
        return card_id if isinstance(card_id, str) and digest(row.get('png_sha256')) else None

    observed, unique = covered(report.get('cases'), passing)
    if not unique or observed != variants.keys():
        reasons.append('variant-coverage')
    sent, unique = covered(evidence.get('deliveries'), confirmed)
    if not unique or sent != deliveries:
        reasons.append('delivery-coverage')
    drawn_cards, unique = covered(evidence.get('reference_cards'), drawn)
    if not unique or drawn_cards != cards:
        reasons.append('reference-coverage')
    return {
        'status': 'hold' if reasons else 'pass', 'reasons': reasons,
        'cases': len({key[0] for key in observed & variants.keys()}),
        'variants': len(observed & variants.keys()), 'required_variants': len(variants),
        'deliveries': len(sent & deliveries), 'required_deliveries': len(deliveries),
        'reference_cards': len(drawn_cards & cards),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Check completeness of saved private replay evidence.')
    parser.add_argument('replay', type=Path)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--checkout', required=True)
    parser.add_argument('--recording-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        result = check(args.replay.read_bytes(), args.evidence.read_bytes(), checkout=args.checkout,
                       recording_sha256=args.recording_sha256)
    except (OSError, ValueError, RecursionError):
        result = {'status': 'hold', 'reasons': ['unreadable-receipt-or-corpus']}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
