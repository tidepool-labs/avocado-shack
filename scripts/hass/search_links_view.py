#!/usr/bin/env python3
"""Count the links NPP would keep from a saved search results page (offline)."""

import argparse
import errno
from html.parser import HTMLParser
import os
from pathlib import Path
import stat
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.npp import research_hermes


MAX_BYTES = 2 * 1024 * 1024


class _Arguments(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error can echo a path in a misplaced argument.
        super().error("invalid arguments; use --help for usage details")


class _AnchorCount(HTMLParser):
    def __init__(self):
        super().__init__()
        self.count = 0

    def handle_starttag(self, tag, attrs):
        if tag == "a" and "result__a" in (dict(attrs).get("class") or "").split():
            self.count += 1


def _read_page(path):
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            return None, "unsafe-input"
        # Guard against a symlink or FIFO replacing the checked directory entry.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                return None, "unsafe-input"
            if info.st_size > MAX_BYTES:
                return None, "too-large"
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(MAX_BYTES + 1)
        finally:
            os.close(fd)
    except OSError as error:
        return None, "unsafe-input" if error.errno == errno.ELOOP else "unreadable-input"
    if len(data) > MAX_BYTES:
        return None, "too-large"
    return data, None


def _fail(reason):
    print(f"FAIL {reason}")
    print("FAIL search_links_view")
    return 1


def main(argv=None):
    arguments = _Arguments(prog="search_links_view.py", description=__doc__, allow_abbrev=False)
    arguments.add_argument("--page", required=True, type=Path, metavar="FILE")
    arguments.add_argument("--limit", required=True, type=int, metavar="N", help="result limit (1–50)")
    args = arguments.parse_args(argv)
    if not 1 <= args.limit <= 50:
        arguments.error("--limit must be between 1 and 50")

    data, reason = _read_page(args.page)
    if data is None:
        return _fail(reason)
    text = data.decode("utf-8", errors="replace")
    try:
        parser = research_hermes._Links(args.limit)
        parser.feed(text)
        parser.close()
        kept = parser.urls
        counter = _AnchorCount()
        counter.feed(text)
        counter.close()
        hosts = {urlsplit(url).hostname for url in kept}
    except Exception:
        return _fail("parse-error")

    print(f"anchors {counter.count}")
    print(f"kept {len(kept)}")
    print(f"dropped {max(0, counter.count - len(kept))}")
    print(f"hosts {len(hosts)}")
    if not kept:
        return _fail("no-links")
    print("PASS search_links_view")
    return 0


if __name__ == "__main__":
    sys.exit(main())
