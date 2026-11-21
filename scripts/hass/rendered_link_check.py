#!/usr/bin/env python3
"""Check internal href and src targets in offline renders of a Hass content copy."""

import argparse
from datetime import date
from html.parser import HTMLParser
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import content_model, sitegen  # noqa: E402

SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
PRINTABLE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,120}")


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.links.extend((value or "") for name, value in attrs if name in ("href", "src"))


class Arguments(argparse.ArgumentParser):
    def error(self, message):
        # argparse includes raw argv in some diagnostics (e.g. an invalid date).
        super().error("invalid arguments; see --help")


def resolve_path(page: str, value: str) -> str:
    """Return a root-relative path, preserving any excess '..' at the root."""
    path = value.split("#", 1)[0].split("?", 1)[0]
    if not path:
        return page
    parts = [] if path.startswith("/") else page.split("/")[:-1]
    for part in path.split("/"):
        if part == ".." and parts and parts[-1] != "..":
            parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    return "/".join(parts)


def site_file(site: Path, path: str) -> bool:
    target = site
    for part in path.split("/"):
        target = target / part
        if os.path.islink(target):
            return False
    try:
        return stat.S_ISREG(target.stat().st_mode)
    except (OSError, ValueError):
        return False


def check_links(rendered: dict[str, bytes], site: Path) -> int:
    pages = links = skipped = 0
    broken: set[tuple[str, str]] = set()
    for key, html in rendered.items():
        if not key.startswith(sitegen.SITE_PREFIX) or not key.endswith(".html"):
            continue
        page = key.removeprefix(sitegen.SITE_PREFIX)
        pages += 1
        parser = LinkParser()
        parser.feed(html.decode("utf-8"))
        parser.close()
        for value in parser.links:
            if value.startswith(("//", "#")) or SCHEME.match(value):
                skipped += 1
                continue
            links += 1
            path = resolve_path(page, value)
            index = f"{path}/index.html" if path else "index.html"
            if path.split("/", 1)[0] == ".." or not (
                sitegen.SITE_PREFIX + path in rendered
                or sitegen.SITE_PREFIX + index in rendered
                or site_file(site, path)
            ):
                broken.add((page, path))

    print(f"pages {pages}")
    print(f"links {links}")
    print(f"skipped {skipped}")
    unprintable = 0
    for page, path in sorted(broken):
        if PRINTABLE.fullmatch(path):
            print(f"broken {page} /{path}")
        else:
            unprintable += 1
    if unprintable:
        print(f"note unprintable {unprintable}")
    return len(broken)


def fail(reason: str) -> int:
    print(f"FAIL {reason}")
    print("FAIL rendered_link_check")
    return 1


def main(argv=None) -> int:
    parser = Arguments(description=__doc__)
    parser.add_argument("--content", required=True, type=Path, help="content copy")
    parser.add_argument("--site", required=True, type=Path, help="storefront-mockup copy")
    parser.add_argument("--templates", type=Path, default=ROOT / "hass" / "templates")
    parser.add_argument("--today", type=date.fromisoformat, help="shop date (YYYY-MM-DD)")
    args = parser.parse_args(argv)

    for directory in (args.content, args.site, args.templates):
        try:
            if os.path.islink(directory) or not directory.is_dir():
                return fail("unsafe-input")
        except OSError:
            return fail("unsafe-input")
    try:
        content = content_model.load_and_validate(Path(args.content), None)
    except (content_model.ContentError, UnicodeDecodeError, OSError):
        return fail("content-invalid")
    try:
        rendered = sitegen.render(content, Path(args.templates), today=args.today or content_model.shop_today())
    except (content_model.ContentError, OSError, UnicodeError):
        return fail("render-failed")

    if broken := check_links(rendered, args.site):
        return fail(f"broken-link {broken}")
    print("PASS rendered_link_check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
