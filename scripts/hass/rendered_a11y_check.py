#!/usr/bin/env python3
"""Render a content copy in memory and report basic HTML accessibility counts."""

import argparse
from collections import Counter
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import content_model, sitegen


CHECKS = ("no-lang", "h1-count", "img-no-alt", "duplicate-id", "empty-link")
VOID_TAGS = frozenset("area base br col embed hr img input link meta param source track wbr".split())
NONVISIBLE_TAGS = {"script", "style", "template"}


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's messages can quote raw arguments, including input paths.
        super().error("invalid arguments; see --help")


class PageCheck(HTMLParser):
    """Check static markup; visibility here does not evaluate CSS or scripts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.has_lang = False
        self.headings = 0
        self.ids = Counter()
        self.missing_alt = 0
        self.empty_alt = 0
        self.empty_links = 0
        self.link_named = None  # None outside a link with href.
        self.elements = []  # (tag, hidden), with visibility inherited from the parent

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        hidden = ("hidden" in attributes or tag in NONVISIBLE_TAGS
                  or bool(self.elements and self.elements[-1][1]))
        if tag not in VOID_TAGS:
            self.elements.append((tag, hidden))
        if "id" in attributes:
            self.ids[attributes["id"] or ""] += 1
        if tag == "html":
            self.has_lang |= bool((attributes.get("lang") or "").strip())
        elif tag == "h1":
            self.headings += 1
        elif tag == "a":
            self.finish_link()
            if "href" in attributes:
                self.link_named = bool((attributes.get("aria-label") or "").strip())
        elif tag == "img":
            if "alt" not in attributes:
                self.missing_alt += 1
            elif not attributes["alt"]:
                self.empty_alt += 1
            elif not hidden and self.link_named is not None and attributes["alt"].strip():
                self.link_named = True

    def handle_endtag(self, tag):
        if tag == "a":
            self.finish_link()
        for index in range(len(self.elements) - 1, -1, -1):
            if self.elements[index][0] == tag:
                del self.elements[index:]
                break

    def handle_data(self, data):
        if (self.link_named is False and data.strip()
                and not (self.elements and self.elements[-1][1])):
            self.link_named = True

    def finish_link(self):
        if self.link_named is False:
            self.empty_links += 1
        self.link_named = None

    def findings(self):
        self.finish_link()
        return {
            "no-lang": int(not self.has_lang),
            "h1-count": int(self.headings != 1),
            "img-no-alt": self.missing_alt,
            "duplicate-id": sum(count > 1 for count in self.ids.values()),
            "empty-link": self.empty_links,
        }


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL rendered_a11y_check")
    return 1


def main(argv=None):
    parser = PrivateArgumentParser(description=__doc__)
    parser.add_argument("--content", type=Path, required=True, help="copied content folder")
    parser.add_argument("--templates", type=Path, default=ROOT / "hass/templates",
                        help="template folder (default: hass/templates)")
    parser.add_argument("--today", type=date.fromisoformat, help="shop date (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    try:
        unsafe = any(path.is_symlink() or not path.is_dir()
                     for path in (args.content, args.templates))
    except OSError:
        unsafe = True
    if unsafe:
        return fail("unsafe-input")
    try:
        content = content_model.load_and_validate(args.content, None)
    except (content_model.ContentError, OSError, UnicodeError):
        return fail("content-invalid")
    try:
        rendered = sitegen.render(content, args.templates, today=args.today or content_model.shop_today())
    except (content_model.ContentError, OSError, UnicodeError):
        return fail("render-failed")

    pages = sorted(key for key in rendered if key.endswith(".html"))
    print(f"pages {len(pages)}")
    totals = Counter()
    empty_alt = 0
    for key in pages:
        page = PageCheck()
        page.feed(rendered[key].decode("utf-8"))
        page.close()
        empty_alt += page.empty_alt
        for kind, count in page.findings().items():
            if count:
                totals[kind] += count
                print(f"page {key.removeprefix('storefront-mockup/')} {kind} {count}")
    if empty_alt:
        print(f"note empty-alt {empty_alt}")
    for kind in CHECKS:
        if totals[kind]:
            print(f"FAIL {kind} {totals[kind]}")
    if totals:
        print("FAIL rendered_a11y_check")
        return 1
    print("PASS rendered_a11y_check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
