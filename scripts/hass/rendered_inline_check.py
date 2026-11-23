#!/usr/bin/env python3
"""Check rendered Hass pages for inline content, without writing or serving them."""

import argparse
from collections import Counter
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import content_model, sitegen  # noqa: E402

KINDS = ("inline-style", "inline-handler", "inline-script", "script-url")


class PageScan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.csp = False
        self.counts = Counter()

    def handle_starttag(self, tag, attrs):
        if tag == "style":
            self.counts["inline-style"] += 1
        elif tag == "script":
            attributes = dict(attrs)
            if "src" not in attributes and attributes.get("type") != "application/ld+json":
                self.counts["inline-script"] += 1

        for name, value in attrs:
            if tag == "meta" and name == "http-equiv" and (value or "").lower() == "content-security-policy":
                self.csp = True
            if name == "style":
                self.counts["inline-style"] += 1
            elif name.startswith("on"):
                self.counts["inline-handler"] += 1
            elif name in ("href", "src", "action") and (value or "").lstrip().lower().startswith("javascript:"):
                self.counts["script-url"] += 1


def report(rendered):
    pages = {}
    for key, data in sorted(rendered.items()):
        if key.endswith(".html"):
            scan = PageScan()
            scan.feed(data.decode("utf-8"))
            scan.close()
            pages[key.removeprefix(sitegen.SITE_PREFIX)] = scan

    print(f"pages {len(pages)}")
    print(f"csp {sum(scan.csp for scan in pages.values())}")
    incidental_styles = 0
    for page, scan in pages.items():
        if not scan.csp:
            print(f"note no-csp {page}")
            incidental_styles += scan.counts["inline-style"]
    print(f"note inline-style-no-csp {incidental_styles}")

    failed = False
    for kind in KINDS:
        counts = [(page, scan.counts[kind]) for page, scan in pages.items()
                  if (scan.csp or kind == "script-url") and scan.counts[kind]]
        if counts:
            failed = True
            print(f"FAIL {kind} {sum(count for _, count in counts)}")
            for page, count in counts:
                print(f"page {page} {kind} {count}")
    return int(failed)


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL rendered_inline_check")
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content", required=True, type=Path, help="directory with Hass content JSON")
    parser.add_argument("--templates", type=Path, default=sitegen.TEMPLATE_DIR, help="template directory override")
    parser.add_argument("--today", type=date.fromisoformat, help="shop date override (YYYY-MM-DD)")
    args = parser.parse_args(argv)

    if any(path.is_symlink() or not path.is_dir() for path in (args.content, args.templates)):
        return fail("unsafe-input")
    try:
        content = content_model.load_and_validate(args.content, None)
    except (content_model.ContentError, OSError, UnicodeError):
        return fail("content-invalid")
    today = args.today if args.today is not None else content_model.shop_today()
    try:
        rendered = sitegen.render(content, args.templates, today=today)
    except (content_model.ContentError, OSError, UnicodeError):
        return fail("render-failed")

    status = report(rendered)
    print("FAIL rendered_inline_check" if status else "PASS rendered_inline_check")
    return status


if __name__ == "__main__":
    sys.exit(main())
