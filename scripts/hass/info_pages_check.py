#!/usr/bin/env python3
"""Check the visibility, robots tags, and links of four offline-rendered info pages."""

import argparse
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from hass import content_model, sitegen  # noqa: E402


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse can quote rejected values or unrecognized arguments (including paths).
        super().error("invalid arguments; see --help")


class _Page(HTMLParser):
    def __init__(self, data: bytes):
        super().__init__(convert_charrefs=True)
        self.noindex = False
        self.hrefs: list[str] = []
        self.feed(data.decode("utf-8"))
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "meta" and (values.get("name") or "").casefold() == "robots":
            self.noindex |= "noindex" in (values.get("content") or "").casefold()
        if (href := values.get("href")) is not None:
            self.hrefs.append(href)


def _finish(*findings: str) -> int:
    for finding in findings:
        print(f"FAIL {finding}")
    print("FAIL info_pages_check" if findings else "PASS info_pages_check")
    return int(bool(findings))


def main(argv=None):
    parser = _ArgumentParser(prog="info_pages_check.py", description=__doc__)
    parser.add_argument("--content", required=True, type=Path, help="copied content directory")
    parser.add_argument("--templates", type=Path, default=REPO_ROOT / "hass/templates",
                        help="template directory (default: repository templates)")
    parser.add_argument("--today", type=date.fromisoformat, default=content_model.shop_today(),
                        help="render date (default: shop's current date)")
    args = parser.parse_args(argv)

    if any(path.is_symlink() or not path.is_dir() for path in (args.content, args.templates)):
        return _finish("unsafe-input")
    try:
        content = content_model.load_and_validate(args.content, None)
    except (content_model.ContentError, UnicodeError, OSError):
        return _finish("content-invalid")
    try:
        files = sitegen.render(content, args.templates, today=args.today)
    except (content_model.ContentError, OSError, UnicodeError):
        return _finish("render-failed")

    def parse(name: str) -> _Page:
        return _Page(files[sitegen.SITE_PREFIX + name])

    shown = set()
    hidden = {}
    shown_noindex = hidden_indexable = 0
    for page, (key, _) in content_model.INFO_PAGES.items():
        noindex = parse(f"{page}/index.html").noindex
        if content.store.get(key, {}).get("shown"):
            shown.add(page)
            shown_noindex += noindex
            print(f"page {page} shown")
        else:
            hidden[f"/{page}/"] = page
            hidden_indexable += not noindex
            print(f"page {page} hidden")
    print(f"shown {len(shown)} of 4")

    home_links = parse("index.html").hrefs
    hidden_links = 0
    for source, links in (("index.html", home_links), ("hike/index.html", parse("hike/index.html").hrefs)):
        for href in links:
            if href in hidden:
                hidden_links += 1
                print(f"link {source} {hidden[href]}")
    for page in content_model.INFO_PAGES:
        if page in shown and f"/{page}/" not in home_links:
            print(f"note shown-unlinked {page}")

    return _finish(*(f"{reason} {count}" for reason, count in (
        ("shown-noindex", shown_noindex),
        ("hidden-indexable", hidden_indexable),
        ("footer-hidden-link", hidden_links),
    ) if count))


if __name__ == "__main__":
    sys.exit(main())
