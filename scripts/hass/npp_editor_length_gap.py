#!/usr/bin/env python3
"""Report where NPP copy binds text longer than the editor allows."""

import argparse
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.content_model import TEXT_LIMITS
from hass.npp import copy


LENGTHS = (40, 60, 61, 80, 81, 100, 120)
ROWS = (
    ('brand', 'name', 'product', 'brand'),
    ('maker_name', 'story', 'maker', 'name'),
    ('town', 'story', 'maker', 'place'),
)


def longest_bound(writer, row, field):
    longest = 0
    for length in LENGTHS:
        value = ('Abcdefghi ' * 13)[:length]
        if value.endswith(' '):
            value = value[:-1] + 'a'
        slot: dict[str, Any] = {row: value}
        ctx = copy.Context('food', 'pantry', 'raw', 'Honey', value, **slot)
        if row in writer.bindings(ctx, field):
            longest = max(longest, length)
    return longest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    findings = []
    try:
        writer = copy.Writer(npp.assets())
    except Exception:
        findings.append('check-error')
    else:
        for row, field, kind, key in ROWS:
            try:
                limit = TEXT_LIMITS[kind][key]
                longest = longest_bound(writer, row, field)
            except Exception:
                # A partial measurement cannot stand in for a completed row.
                if 'check-error' not in findings:
                    findings.append('check-error')
                continue
            print(f'field {row} longest-bound={longest} editor={limit}')
            if longest > limit:
                findings.append(f'limit-gap {row}')

    for reason in findings:
        print(f'FAIL {reason}')
    print(f'{"FAIL" if findings else "PASS"} npp_editor_length_gap')
    return int(bool(findings))


if __name__ == '__main__':
    raise SystemExit(main())
