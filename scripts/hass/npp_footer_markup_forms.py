#!/usr/bin/env python3
"""Report which offline footer fixtures S4 recognizes as maker ownership."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.npp import research

NAME = "Miners Orchards"
TOWN = "Arroyo Grande"
COPYRIGHT = f"&copy; 2024 {NAME}."
FORMS = (
    f"<footer>{COPYRIGHT}</footer>",
    f"<footer><p>{COPYRIGHT}</p></footer>",
    f"<footer><div><small>{COPYRIGHT}</small></div></footer>",
    f'<div id="page"><footer><p>{COPYRIGHT}</p></footer></div>',
    f"<main><footer><p>{COPYRIGHT}</p></footer></main>",
    f'<div class="footer"><p>{COPYRIGHT}</p></div>',
    f'<div id="footer"><p>{COPYRIGHT}</p></div>',
    f'<div class="site-footer">{COPYRIGHT}</div>',
    f"<p>{COPYRIGHT}</p>",
    f'<section class="footer"><p>{COPYRIGHT}</p></section>',
    f'<div role="contentinfo"><p>{COPYRIGHT}</p></div>',
    f'<footer><nav><a href="/">Home</a></nav><p>{COPYRIGHT}</p></footer>',
    f'<footer class="hidden">{COPYRIGHT}</footer>',
    f"<footer><span>{COPYRIGHT}</span></footer>",
)
FOOTER = frozenset({0, 1, 2, 3, 4, 11, 13})
HIDDEN = 12


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    try:
        _, files, _ = npp.assets()
        markers = research._markers(json.loads(files["hass-maker-research/facts.schema.json"]))
    except Exception:
        print("FAIL check-error")
        print("FAIL npp_footer_markup_forms")
        return 1

    failed = False
    for i, form in enumerate(FORMS):
        html = (
            f"<html><head><title>{NAME}</title></head><body><h1>{NAME}</h1>"
            f"<p>{NAME} grows apples in {TOWN}.</p>{form}</body></html>"
        )
        try:
            page = research.parse_page("https://miners.example/", "2026-11-21", html)
            reason = research._own_site(page, NAME, TOWN, markers)
        except Exception:
            print("FAIL check-error")
            failed = True
            continue

        print(f"form {i} reason={reason} owner-lines={len(page.ownership)}")
        finding = None
        if i in FOOTER and reason != "official":
            if any(NAME in line for line in page.ownership):
                finding = f"footer-refused {i}"
            else:
                finding = f"footer-text-lost {i}"
        elif i == HIDDEN and reason == "official":
            finding = "hidden-footer-accepted"
        if finding is not None:
            print(f"FAIL {finding}")
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_footer_markup_forms")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
