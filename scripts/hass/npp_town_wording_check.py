#!/usr/bin/env python3
"""Compare NPP and maker-editor town wording offline, reporting counts only."""

import argparse
import io
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model
from hass.npp import stages
from hass.skills import makers


NAME = "npp_town_wording_check"
MAX_BYTES = 64 * 1024
MAX_LINES = 500
BUCKETS = {
    (True, True): "both",
    (True, False): "npp-only",
    (False, True): "editor-only",
    (False, False): "neither",
}


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's error detail can echo unrecognized positional arguments.
        super().error("choose exactly one input option and supply its path")


class Finding(Exception):
    """A reason safe to report without echoing input values."""


def _require_kind(path, is_kind):
    # lstat checks the argument itself, not the target of a symlink.
    try:
        mode = path.lstat().st_mode
    except (OSError, ValueError):
        raise Finding("unsafe-input") from None
    if not is_kind(mode):
        raise Finding("unsafe-input")


def _file_places(path):
    _require_kind(path, stat.S_ISREG)
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise Finding("too-large")
        text = raw.decode("utf-8")
    except (OSError, UnicodeError):
        raise Finding("unreadable-input") from None
    # Count physical lines, including blank ones, before stripping them.
    lines = io.StringIO(text, newline=None).readlines()
    if len(lines) > MAX_LINES:
        raise Finding("too-many-lines")
    return [place for line in lines if (place := line.strip())]


def _content_places(path):
    _require_kind(path, stat.S_ISDIR)
    try:
        records = content_model.load_content(path).makers
        return [records[key]["place"] for key in sorted(records)]
    except Exception:
        raise Finding("content-invalid") from None


def _counts(places):
    counts = dict.fromkeys(BUCKETS.values(), 0)
    for place in places:
        try:
            try:
                npp = stages._site_words("Maker", ["based in " + place])[0] == place
            except makers.Refusal:
                npp = False
            try:
                editor = makers.rule_town_state(place) is False
            except makers.Refusal:
                editor = False
        except Exception:
            raise Finding("check-error") from None
        counts[BUCKETS[npp, editor]] += 1
    return counts


def main(argv=None):
    parser = PrivateParser(prog=NAME, description=__doc__, allow_abbrev=False)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--places", type=Path, metavar="FILE", help="UTF-8 place list")
    source.add_argument("--content", type=Path, metavar="DIR", default=content_model.CONTENT_DIR,
                        help="content directory (normally hass/content)")
    args = parser.parse_args(argv)

    try:
        places = _file_places(args.places) if args.places is not None else _content_places(args.content)
        counts = _counts(places)
        print("places", len(places))
        for label, count in counts.items():
            print(label, count)
        disagree = counts["npp-only"] + counts["editor-only"]
        if disagree:
            raise Finding(f"disagree {disagree}")
    except Finding as error:
        print(f"FAIL {error}")
        print(f"FAIL {NAME}")
        return 1
    print(f"PASS {NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
