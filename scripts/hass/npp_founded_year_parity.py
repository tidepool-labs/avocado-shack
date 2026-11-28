#!/usr/bin/env python3
"""Compare the S4 research and S5 story verdicts on offline founding-year fixtures."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import npp
from hass.npp import copy, research


READ_DATES = ['2026-11-21', '2027-01-04']
YEARS = ['1799', '1800', '2026', '2027', '2028']
CONTROL = ('2026-11-21', '1800')
URL = 'https://ettofarm.example/'
NAME = 'Etto Farm'


def verdicts(read_date, year, schema, markers, writer):
    quote = f'{NAME} started in {year}.'
    page = research.parse_page(
        URL, read_date,
        f'<html><head><title>{NAME}</title></head><body><p>{quote}</p></body></html>',
    )
    reason = research._check(
        {'url': URL, 'slot': 'founded', 'value': year, 'quote': quote},
        {URL: page}, NAME, '', schema, markers,
    )
    context = copy.Context(
        'food', 'pantry', 'raw', 'Honey', 'made by Etto Farm', maker_name=NAME,
        facts=(copy.Fact('official-founded', 'founded', year, URL, quote, 'supports'),),
    )
    return reason, 'founded' in writer.bindings(context, 'story')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    if args:
        parser.error('no arguments accepted')

    findings = []
    try:
        pinned = npp.assets()
        schema = json.loads(pinned[1]['hass-maker-research/facts.schema.json'])
        markers = research._markers(schema)
        writer = copy.Writer(pinned)
    except Exception:
        findings.append('check-error')
    else:
        saw_control = False
        for read_date in READ_DATES:
            for year in YEARS:
                control = (read_date, year) == CONTROL
                saw_control |= control
                try:
                    reason, binds = verdicts(read_date, year, schema, markers, writer)
                except Exception:
                    # Keep testing the other pairs; never expose exception details.
                    if 'check-error' not in findings:
                        findings.append('check-error')
                    if control:
                        findings.append('control-broken')
                    continue

                kept = reason is None
                print(f'founded {read_date} {year} s4={"kept" if kept else reason} '
                      f's5={"yes" if binds else "no"}')
                if kept != binds:
                    findings.append(f'founded-split {read_date} {year}')
                if control and not (kept and binds):
                    findings.append('control-broken')
        if not saw_control:
            findings.append('control-broken')

    for reason in findings:
        print(f'FAIL {reason}')
    print(f'{"FAIL" if findings else "PASS"} npp_founded_year_parity')
    return int(bool(findings))


if __name__ == '__main__':
    raise SystemExit(main())
