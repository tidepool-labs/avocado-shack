#!/usr/bin/env python3
"""Join a saved private NPP recording and a later top-up into one new recording for strict replay.

  python3 scripts/hass/npp_merge_recordings.py OUT BASE TOPUP [TOPUP ...] [--base-sha256 HEX]

`hass/tests/npp/run_npp.py --record --recorded BASE --record-to TOPUP` calls only what BASE lacks and saves only those
new rows, while replay takes one `--recorded` file. This joins them without changing any row: every input must
have the recorder's shape. A key that appears twice (across inputs, or against the versioned tapes in
hass/tests/npp/tapes/) is refused rather than overwritten. Each operation kind must keep the same source label, and OUT
must be a new file outside the checkout, created 0600 like the recorder's own file. Nothing is called or sent. Only
per-kind row counts and the SHA-256 digests of the inputs and output are printed, never a row.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
KEY = re.compile(r'[0-9a-f]{64}:[0-9a-f]{64}:(0|[1-9][0-9]*)')


class Refused(ValueError):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _unique(pairs):
    """object_pairs_hook: a JSON object that names a key twice would silently drop a row, so refuse it."""
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise Refused('a JSON object repeats a key; rows are never dropped or overwritten')
    return dict(pairs)


def load(name, raw):
    """Parse one recording from the exact bytes that were hashed, refusing anything not the recorder's shape."""
    try:
        data = json.loads(raw, object_pairs_hook=_unique)
    except Refused as error:
        raise Refused(f'{name}: {error}') from None
    except ValueError as error:
        raise Refused(f'{name}: unreadable recording ({type(error).__name__})') from None
    if not isinstance(data, dict) or not data:
        raise Refused(f'{name}: not a recording (expected a non-empty object of operation kinds)')
    for kind, block in data.items():
        if not isinstance(block, dict) or set(block) != {'kind', 'source', 'entries'} or block['kind'] != kind:
            raise Refused(f'{name}: kind {kind!r} is not a recorder block')
        if not isinstance(block['source'], str) or not isinstance(block['entries'], dict) or not block['entries']:
            raise Refused(f'{name}: kind {kind!r} has no source label or no rows')
        for key, entry in block['entries'].items():
            if not KEY.fullmatch(key) or not isinstance(entry, dict) or set(entry) != {'output'}:
                raise Refused(f'{name}: kind {kind!r} holds a row that is not pin:input:ordinal -> output')
    return data


def merge(recordings, versioned=()):
    """Return the joined recording; `versioned` is the set of 'kind:key' already on the checked-in tapes."""
    out = {}
    for name, data in recordings:
        for kind, block in data.items():
            have = out.setdefault(kind, {'kind': kind, 'source': block['source'], 'entries': {}})
            if have['source'] != block['source']:
                raise Refused(f'{name}: kind {kind!r} source label differs from an earlier input')
            for key, entry in block['entries'].items():
                if key in have['entries']:
                    raise Refused(f'{name}: kind {kind!r} repeats a recorded key; rows are never overwritten')
                if f'{kind}:{key}' in versioned:
                    raise Refused(f'{name}: kind {kind!r} repeats a key on the versioned tapes')
                have['entries'][key] = entry
    return out


def versioned_keys():
    sys.path.insert(0, str(REPO))
    from hass.tests.npp import run_npp
    return set(run_npp.Tapes().entries)


def write_new(path, data):
    path = Path(path)
    if path.exists() or not path.parent.is_dir():
        raise Refused('OUT must be a new file in an existing directory')
    if path.resolve().is_relative_to(REPO):
        raise Refused('OUT must be outside the checkout; private recordings never enter Git')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, sort_keys=True)
        handle.write('\n')
    return sha256(path.read_bytes())


def main(argv=None, versioned=None):
    p = argparse.ArgumentParser(description='Join a saved private NPP recording and its top-up into one new file.')
    p.add_argument('out', type=Path)
    p.add_argument('base', type=Path)
    p.add_argument('topups', type=Path, nargs='+')
    p.add_argument('--base-sha256', help='refuse unless BASE has exactly this SHA-256')
    args = p.parse_args(argv)
    try:
        inputs = [args.base, *args.topups]
        if len({path.resolve() for path in inputs}) != len(inputs):
            raise Refused('the same recording was given twice')
        raws = []
        for path in inputs:
            try:
                raws.append(path.read_bytes())  # read once: the digest checked and the rows parsed are the same bytes
            except OSError:
                raise Refused('every input must be an existing, readable recording file') from None
        digests = [sha256(raw) for raw in raws]
        want = (args.base_sha256 or '').lower()
        if args.base_sha256 is not None and digests[0] != want:
            raise Refused(f'BASE digest {digests[0][:8]} is not the expected {want[:8]}')
        loaded = [(path.name, load(path.name, raw)) for path, raw in zip(inputs, raws)]
        joined = merge(loaded, versioned_keys() if versioned is None else versioned)
        out_sha = write_new(args.out, joined)
    except Refused as error:
        print(json.dumps({'refused': str(error)}))
        return 2
    print(json.dumps({
        'inputs': [{'sha256': digest, 'rows': {k: len(b['entries']) for k, b in sorted(data.items())}}
                   for digest, (_name, data) in zip(digests, loaded)],
        'output': {'sha256': out_sha, 'rows': {k: len(b['entries']) for k, b in sorted(joined.items())}},
    }, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
