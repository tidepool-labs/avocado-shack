#!/usr/bin/env python3
"""Replay maker research using saved pages and recorded verdicts, offline."""

import argparse
from datetime import date
import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import maker_site
from hass import npp
from hass.npp.research import parse_page, research


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's default diagnostics can echo unknown arguments verbatim.
        super().error("invalid arguments (see --help)")


def read_text(path):
    # Open without following a leaf symlink, and don't block on special files.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, encoding="utf-8") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("expected a regular file")
        return stream.read()


def reject_constant(_token):
    raise ValueError("not a JSON number")


def load_manifest(path):
    tape = json.loads(read_text(path), parse_constant=reject_constant)
    if (not isinstance(tape, dict) or not {"search", "pages", "extract", "verify"} <= tape.keys()
            or not all(isinstance(tape[key], dict) for key in ("search", "pages", "verify"))
            or not all(isinstance(urls, list) for urls in tape["search"].values())):
        raise ValueError("invalid manifest")
    return tape


def load_page(directory, entry):
    name, retrieved = entry["file"], entry["retrieved"]
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError("expected a plain page filename")
    if date.fromisoformat(retrieved).isoformat() != retrieved:
        raise ValueError("expected a retrieval date")
    return retrieved, read_text(directory / name)


def fail():
    print("FAIL npp_research_dryrun")
    return 1


def main(argv=None):
    parser = PrivateArgumentParser(prog="npp_research_dryrun.py", description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--maker", default="")
    parser.add_argument("--town", default="")
    parser.add_argument("--owner-url", default="")
    args = parser.parse_args(argv)

    try:
        tape = load_manifest(args.manifest)
    except (OSError, ValueError, RecursionError):
        print("FAIL manifest-unreadable")
        return fail()

    pages = {}
    # Validate even unused entries, but count only requests made by research.
    for index, (url, entry) in enumerate(tape["pages"].items(), 1):
        try:
            pages[url] = load_page(args.manifest.parent, entry)
        except (OSError, ValueError, KeyError, TypeError):
            print(f"FAIL page-missing {index}")
    try:
        pinned = npp.assets()
    except Exception:
        # The asset loader's exception may include private paths or contents.
        print("FAIL assets-refused")
        return fail()
    if len(pages) != len(tape["pages"]):
        return fail()

    fetched = 0

    def search(query, _limit, _seconds):
        return tape["search"].get(query, [])

    def fetch(url, _seconds):
        nonlocal fetched
        if url not in pages:
            raise maker_site.PageError("unreachable")
        fetched += 1
        return parse_page(url, *pages[url])

    def extract(_name, _blocks, _seconds):
        return tape["extract"]

    def verify(_name, slot, value, _quote, _seconds):
        return tape["verify"].get(f"{slot}|{value}", "unclear")

    result = research(pinned, search=search, fetch=fetch, extract=extract, verify=verify,
                      owner_maker=args.maker, owner_town=args.town, owner_url=args.owner_url,
                      clock=lambda: 0.0)
    print(f"queries {len(result.receipt['queries'])}")
    print(f"fetched {fetched}")
    print(f"facts-kept {len(result.facts)}")
    for fact in result.facts:
        print(f"kept {fact['slot']}")
    for key, value in result.receipt.items():
        if isinstance(value, (list, dict)):
            print(f"receipt {key} items {len(value)}")
        else:
            print(f"receipt {key} {value}")
    print("PASS npp_research_dryrun")
    return 0


if __name__ == "__main__":
    sys.exit(main())
