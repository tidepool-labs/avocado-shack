#!/usr/bin/env python3
"""Report whether static hiding forms keep maker text out of S4 evidence."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.npp import research


SECRET = "Hidden Founded Line"
SHOWN = "Shown line"
HIDDEN = (
    f'<p hidden>{SECRET}</p>',
    f'<p aria-hidden="true">{SECRET}</p>',
    f'<p aria-hidden="TRUE">{SECRET}</p>',
    f'<p inert>{SECRET}</p>',
    f'<p class="hidden">{SECRET}</p>',
    f'<p class="d-none">{SECRET}</p>',
    f'<p class="x sr-only">{SECRET}</p>',
    f'<p class="visually-hidden">{SECRET}</p>',
    f'<p style="display:none">{SECRET}</p>',
    f'<p style="display: none !important">{SECRET}</p>',
    f'<p style="visibility:hidden">{SECRET}</p>',
    f'<p style="opacity: 0">{SECRET}</p>',
    f'<div hidden/><p>{SECRET}</p>',
    f'<script>document.write("{SECRET}")</script>',
    f'<style>p::after{{content:"{SECRET}"}}</style>',
    f'<noscript><p>{SECRET}</p></noscript>',
    f'<template><p>{SECRET}</p></template>',
    f'<form><p>{SECRET}</p></form>',
    f'<aside><p>{SECRET}</p></aside>',
    f'<svg><text>{SECRET}</text></svg>',
    f'<button><p>{SECRET}</p></button>',
    f'<dialog><p>{SECRET}</p></dialog>',
    f'<details><p>{SECRET}</p></details>',
    f'<iframe><p>{SECRET}</p></iframe>',
    f'<div hidden><div><p>{SECRET}</p></div></div>',
    f'<nav><p>{SECRET}</p></nav>',
    f'<p class="screen-reader-text">{SECRET}</p>',
    f'<p class="invisible">{SECRET}</p>',
    f'<p style="visibility:collapse">{SECRET}</p>',
    f'<p style="font-size:0">{SECRET}</p>',
    f'<p><span hidden>{SECRET}</span>Shown</p>',
)
VISIBLE = (
    f'<p>{SHOWN}</p>',
    f'<h1>{SHOWN}</h1>',
    f'<h2>{SHOWN}</h2>',
    f'<h3>{SHOWN}</h3>',
    f'<li>{SHOWN}</li>',
    f'<header><p>{SHOWN}</p></header>',
    f'<p class="lead">{SHOWN}</p>',
    f'<p style="color:red">{SHOWN}</p>',
    f'<p aria-hidden="false">{SHOWN}</p>',
    f'<div><p>{SHOWN}</p></div>',
)
OPACITY_PARTIAL = f'<p style="opacity:0.5">{SHOWN}</p>'


def _parse(markup):
    try:
        return research.parse_page('https://m.example/', '2026-11-21', markup)
    except Exception:
        # No fixture text, exception details or invented yes/no observation.
        print('FAIL check-error')
        return None


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    for index, fragment in enumerate(HIDDEN):
        page = _parse(f'<html><head><title>T</title></head><body><p>Visible one.</p>{fragment}</body></html>')
        if page is None:
            failed = True
            continue
        leak = any(SECRET in text for text in (*page.blocks, *page.ownership, *page.titles))
        print(f'hidden {index} leak={"yes" if leak else "no"}')
        if leak:
            print(f'FAIL hidden-text-read {index}')
            failed = True

    for index, fragment in enumerate((*VISIBLE, OPACITY_PARTIAL)):
        page = _parse(f'<html><body>{fragment}</body></html>')
        if page is None:
            failed = True
            continue
        kept = SHOWN in page.blocks
        partial = index == len(VISIBLE)
        label = 'opacity-partial' if partial else f'visible {index}'
        print(f'{label} kept={"yes" if kept else "no"}')
        if not partial and not kept:
            print(f'FAIL visible-text-lost {index}')
            failed = True

    print(f'{"FAIL" if failed else "PASS"} npp_hidden_text_classes')
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
