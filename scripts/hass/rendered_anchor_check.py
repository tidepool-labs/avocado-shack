#!/usr/bin/env python3
"""Check fragment targets in an offline render without writing site files."""

import argparse
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
import posixpath
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import content_model, sitegen  # noqa: E402


PRINTABLE_FRAGMENT = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")
URL_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")


class PageAnchors(HTMLParser):
    def __init__(self, html: bytes):
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.hrefs: list[str] = []
        self.feed(html.decode("utf-8"))
        self.close()

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if value is None:
                continue
            if name == "id":
                self.ids.add(value)
            elif name == "href":
                self.hrefs.append(value)


def target_page(source: str, path: str, pages: dict[str, PageAnchors]) -> str | None:
    if not path:
        return source
    if path.startswith("//") or URL_SCHEME.match(path):
        return None
    # Resolve relative jumps from the rendered page's directory, not the cwd.
    base = "/" + posixpath.dirname(source)
    key = posixpath.normpath(posixpath.join(base, path)).lstrip("/")
    for candidate in (key, posixpath.join(key, "index.html")):
        if candidate in pages:
            return candidate
    return None


def fail(reason: str) -> int:
    print(f"FAIL {reason}")
    print("FAIL rendered_anchor_check")
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--templates", type=Path, default=ROOT / "hass/templates")
    parser.add_argument("--today", type=date.fromisoformat)
    args = parser.parse_args(argv)
    if any(path.is_symlink() or not path.is_dir() for path in (args.content, args.templates)):
        return fail("unsafe-input")
    try:
        content = content_model.load_and_validate(args.content, None)
    except (content_model.ContentError, OSError, UnicodeError):
        return fail("content-invalid")
    try:
        rendered = sitegen.render(content, args.templates, today=args.today or content_model.shop_today())
    except (content_model.ContentError, OSError, UnicodeError):
        return fail("render-failed")
    pages = {key.removeprefix(sitegen.SITE_PREFIX): PageAnchors(html)
             for key, html in rendered.items() if key.endswith(".html")}

    checked = offpage = 0
    missing = set()
    for source, anchors in pages.items():
        for href in anchors.hrefs:
            url, _, fragment = href.partition("#")
            if not fragment:
                continue
            target = target_page(source, url.partition("?")[0], pages)
            if target is None:
                offpage += 1
                continue
            checked += 1
            if fragment not in pages[target].ids:
                missing.add((source, target, fragment))

    print(f"pages {len(pages)}")
    print(f"anchors {checked}")
    unprintable = 0
    for source, target, fragment in sorted(missing):
        if PRINTABLE_FRAGMENT.fullmatch(fragment):
            print(f"anchor {source} {target} {fragment}")
        else:
            unprintable += 1
    if offpage:
        print(f"note offpage {offpage}")
    if unprintable:
        print(f"note unprintable {unprintable}")
    if missing:
        return fail(f"anchor-missing {len(missing)}")
    print("PASS rendered_anchor_check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
