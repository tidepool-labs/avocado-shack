#!/usr/bin/env python3
"""Print what S4 sees in saved maker HTML as counts, without fetching anything."""

import argparse
from datetime import date
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import maker_site
from hass.npp import research


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse can echo an unrecognized flag or an unexpected value.
        super().error("invalid arguments; see --help")


def iso_date(value):
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            date.fromisoformat(value)
            return value
        except ValueError:
            pass
    raise argparse.ArgumentTypeError("expected a valid YYYY-MM-DD date")


def read_html(path):
    """Return (markup, finding), treating unreadable inputs as unsafe."""
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            return None, "unsafe-input"
        # Recheck the open file; a replacement symlink or FIFO cannot redirect
        # or hang the read between lstat and open.
        with open(path, "rb", opener=open_without_following) as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode):
                return None, "unsafe-input"
            if info.st_size > maker_site.MAX_BYTES:
                return None, "too-large"
            data = source.read(maker_site.MAX_BYTES + 1)
    except (OSError, ValueError):
        return None, "unsafe-input"
    if len(data) > maker_site.MAX_BYTES:
        return None, "too-large"
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, "not-utf8"


def open_without_following(path, flags):
    return os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK)


def site(url):
    host = urlsplit(url).hostname
    return host.removeprefix("www.") if host is not None else None


def same_site(url, href, host):
    try:
        return site(urljoin(url, href)) == host
    except ValueError:
        # A malformed link has no matching host, but is still in Page.about.
        return False


def show_page(url, retrieved, markup):
    try:
        page = research.parse_page(url, retrieved, markup)
    except (ValueError, AssertionError):
        # The parser may refuse malformed HTML or over-deep nesting.
        return "unsafe-input"

    host = site(url)
    same = sum(same_site(url, href, host) for href in page.about)
    print(f"titles {len(page.titles)}")
    print(f"ownership {len(page.ownership)}")
    print(f"blocks {len(page.blocks)}")
    print(f"about {len(page.about)}")
    print(f"about-same-site {same}")
    print(f"about-other-site {len(page.about) - same}")
    return None if page.blocks else "no-blocks"


def main(argv=None):
    parser = PrivateArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--html", required=True, type=Path, metavar="FILE", help="saved UTF-8 HTML")
    parser.add_argument("--url", required=True, metavar="URL", help="page address (not fetched)")
    parser.add_argument("--retrieved", required=True, type=iso_date, metavar="YYYY-MM-DD",
                        help="retrieval date in YYYY-MM-DD format")
    args = parser.parse_args(argv)

    findings = []
    try:
        url = maker_site.check_address(args.url)
    except maker_site.PageError:
        url = None
        findings.append("bad-url")

    markup, finding = read_html(args.html)
    if finding:
        findings.append(finding)
    elif url is not None:
        finding = show_page(url, args.retrieved, markup)
        if finding:
            findings.append(finding)

    for finding in findings:
        print(f"FAIL {finding}")
    print("FAIL research_page_view" if findings else "PASS research_page_view")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
