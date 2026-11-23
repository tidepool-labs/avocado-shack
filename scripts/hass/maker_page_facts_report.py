#!/usr/bin/env python3
"""Report which maker facts and story sentences Hass finds in saved HTML, offline."""

import argparse
from datetime import date
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import maker_site  # noqa: E402


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse can include raw values in errors, notably for unrecognized arguments.
        super().error("invalid arguments; see --help")


def maker_name(value):
    name = " ".join(value.split())
    if not 1 <= len(name) <= 80:
        raise argparse.ArgumentTypeError("expected a name of 1–80 characters")
    return name


def iso_day(value):
    try:
        day = date.fromisoformat(value)
    except ValueError:
        day = None
    if day is None or day.isoformat() != value:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD")
    return day


def open_regular(path, flags):
    # Do not follow a replacement symlink or block on a replacement FIFO.
    return os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK)


def report(path, name, day, town):
    try:
        info = path.lstat()
    except (OSError, ValueError):
        return "unsafe-input"
    if not stat.S_ISREG(info.st_mode):
        return "unsafe-input"
    limit = maker_site.MAX_BYTES
    if info.st_size > limit:
        return "too-large"
    try:
        with open(path, "rb", opener=open_regular) as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                return "unsafe-input"
            data = source.read(limit + 1)
    except OSError:
        return "unreadable-input"
    if len(data) > limit:
        return "too-large"
    try:
        markup = data.decode("utf-8")
    except UnicodeDecodeError:
        return "not-utf8"

    blocks = maker_site.extract(markup)
    page = {"blocks": blocks}
    found = maker_site.facts(name, page, town=town or "", today=day)
    story = maker_site.draft_story(name, page, town=town or "", today=day)
    print(f"blocks {len(blocks)}")
    for key in ("makes", "since", "town"):
        if key != "town" or town is not None:
            print(f"fact {key} {'yes' if key in found else 'no'}")
    if story is None:
        print("story none")
        return "no-story"
    print(f"story sentences {len(story['sentences'])}")
    return None


def main(argv=None):
    parser = PrivateArgumentParser(
        prog="maker_page_facts_report.py", description=__doc__, allow_abbrev=False,
    )
    parser.add_argument("--html", type=Path, required=True, metavar="FILE")
    parser.add_argument("--name", type=maker_name, required=True, metavar="NAME")
    parser.add_argument("--today", type=iso_day, required=True, metavar="YYYY-MM-DD")
    parser.add_argument("--town", metavar="TOWN")
    args = parser.parse_args(argv)
    reason = report(args.html, args.name, args.today, args.town)
    if reason is not None:
        print(f"FAIL {reason}")
        print("FAIL maker_page_facts_report")
        return 1
    print("PASS maker_page_facts_report")
    return 0


if __name__ == "__main__":
    sys.exit(main())
