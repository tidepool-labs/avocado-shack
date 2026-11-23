#!/usr/bin/env python3
"""Check the home page's rendered store JSON-LD without writing site files."""

import argparse
from datetime import date
from html.parser import HTMLParser
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import content_model, sitegen


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's detailed error may echo values from the command line.
        super().error("invalid arguments (see --help)")


class _JsonLdScripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[list[str]] = []
        self._collecting = False

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type") == "application/ld+json":
            self.blocks.append([])
            self._collecting = True

    def handle_data(self, data):
        if self._collecting:
            self.blocks[-1].append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self._collecting = False


def _fail(reason):
    print(f"FAIL {reason}")
    print("FAIL rendered_jsonld_check")
    return 1


def _reject_constant(_token):
    raise ValueError("non-JSON constant")


def _mismatches(block, store, open_days):
    address = block.get("address")
    if not isinstance(address, dict):
        address = {}
    phone = store.get("phone")
    phone_matches = (block.get("telephone") == f"+1-{phone[:3]}-{phone[3:6]}-{phone[6:]}"
                     if phone else "telephone" not in block)
    hours = block.get("openingHoursSpecification")
    hours_match = (isinstance(hours, list) and len(hours) == open_days
                   if open_days else "openingHoursSpecification" not in block)
    checks = (
        ("type", block.get("@type") == "GroceryStore"),
        ("name", block.get("name") == store["name"]),
        ("street", address.get("streetAddress") == store["streetAddress"]),
        ("town", address.get("addressLocality") == store["town"]),
        ("telephone", phone_matches),
        ("hours", hours_match),
    )
    return [field for field, matches in checks if not matches]


def main(argv=None):
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument("--content", type=Path, required=True, help="directory of content JSON files")
    parser.add_argument("--templates", type=Path, default=ROOT / "hass" / "templates", help="template directory")
    parser.add_argument("--today", type=date.fromisoformat, metavar="YYYY-MM-DD", help="render date (default: shop date)")
    args = parser.parse_args(argv)

    try:
        if any(path.is_symlink() or not path.is_dir() for path in (args.content, args.templates)):
            return _fail("unsafe-input")
    except (OSError, ValueError):
        return _fail("unsafe-input")
    try:
        content = content_model.load_and_validate(args.content, None)
    except (content_model.ContentError, OSError, UnicodeDecodeError):
        return _fail("content-invalid")
    try:
        pages = sitegen.render(content, args.templates, today=args.today or content_model.shop_today())
    except (content_model.ContentError, OSError, UnicodeDecodeError):
        return _fail("render-failed")

    scripts = _JsonLdScripts()
    scripts.feed(pages.get(sitegen.SITE_PREFIX + "index.html", b"").decode("utf-8"))
    scripts.close()
    count = len(scripts.blocks)
    print(f"jsonld {count}")
    days = sitegen.parse_hours(content.store["hours"])["days"]
    if days is None:
        print("note hours-unreadable")
    if count == 0:
        return _fail("jsonld-missing")
    if count > 1:
        return _fail(f"jsonld-duplicate {count}")
    try:
        block = json.loads("".join(scripts.blocks[0]), parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        return _fail("jsonld-invalid")
    if not isinstance(block, dict):
        return _fail("jsonld-invalid")

    open_days = sum(day is not None and "opens" in day for day in days or ())
    mismatches = _mismatches(block, content.store, open_days)
    for field in mismatches:
        print(f"mismatch {field}")
    if mismatches:
        return _fail(f"jsonld-mismatch {len(mismatches)}")
    print("PASS rendered_jsonld_check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
