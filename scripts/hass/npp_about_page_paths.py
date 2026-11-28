#!/usr/bin/env python3
"""Check S4 ownership and About-link parsing with offline HTML fixtures."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp
from hass.npp import research


PATHS = (
    "/about", "/about/", "/about-us", "/our-story", "/who-we-are", "/pages/about",
    "/en/about/", "/About", "/about.html", "/about-us.html", "/about.htm",
    "/our-story.html", "/", "/contact",
)
ABOUT_COUNT = 12
SITE = "https://miners.example"
RETRIEVED = "2026-11-21"
HTML = (
    "<html><head><title>Miners Orchards</title></head><body><h1>Miners Orchards</h1>"
    "<p>We are Miners Orchards.</p><p>Miners Orchards grows apples in Arroyo Grande.</p>"
    "</body></html>"
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    try:
        _, files, _ = hass.npp.assets()
        markers = research._markers(json.loads(files["hass-maker-research/facts.schema.json"]))
    except Exception:
        print("FAIL check-error")
        print("FAIL npp_about_page_paths")
        return 1

    failed = False
    for index, path in enumerate(PATHS):
        try:
            page = research.parse_page(SITE + path, RETRIEVED, HTML)
            reason = research._own_site(page, "Miners Orchards", "Arroyo Grande", markers)
        except Exception:
            print("FAIL check-error")
            failed = True
            continue

        try:
            nav = research.parse_page(
                SITE + "/", RETRIEVED, f'<html><body><nav><a href="{path}">About</a></nav></body></html>',
            )
            print(f"path {index} own={reason} link={'yes' if nav.about else 'no'}")
        except Exception:
            print("FAIL check-error")
            failed = True

        if index < ABOUT_COUNT and reason != "official":
            print(f"FAIL about-page-refused {index}")
            failed = True
        elif index >= ABOUT_COUNT and reason == "official":
            print(f"FAIL control-accepted {index}")
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_about_page_paths")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
