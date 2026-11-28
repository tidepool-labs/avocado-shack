#!/usr/bin/env python3
"""Check frozen listing picture identity and note text with offline fixtures."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.npp import picture

_PATH = "items/fixture-a.jpg"
_DIGEST = "a" * 64
_TAGGED = "sha256:" + _DIGEST

CASES = (
    ("raw", _PATH, _DIGEST, {"assets": {_PATH: _TAGGED}}),
    ("house", _PATH, _DIGEST, {"assets": {_PATH: _TAGGED}}),
    ("polished", _PATH, _DIGEST, {"assets": {_PATH: _TAGGED}}),
    ("raw", _PATH, "ab" * 32, {"assets": {_PATH: "sha256:" + "AB" * 32}}),
    ("raw", _PATH, _DIGEST, {"assets": {_PATH: _DIGEST}}),
    ("raw", _PATH, _DIGEST, {"assets": {"items/fixture-b.jpg": _TAGGED}}),
    ("raw", _PATH, _DIGEST, {}),
    ("raw", _PATH, _DIGEST, {"assets": {_PATH: "sha256:" + "b" * 64}}),
    ("legacy", _PATH, _DIGEST, {"assets": {_PATH: _TAGGED + " "}}),
)
MUST_REFUSE = frozenset({3, 4, 5, 6, 7, 8})
EXPECTED = (
    "case 0 match=yes note='picture: your own photo'",
    "case 1 match=yes note='picture: house style'",
    "case 2 match=yes note=''",
    "case 3 match=no note='picture: your own photo'",
    "case 4 match=no note='picture: your own photo'",
    "case 5 match=no note='picture: your own photo'",
    "case 6 match=no note='picture: your own photo'",
    "case 7 match=no note='picture: your own photo'",
    "case 8 match=no note=''",
)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(args)
    if args:  # Keep the no-argument contract even if argparse consumes a marker.
        parser.error(f"unrecognized arguments: {' '.join(args)}")

    failed = False
    for i, (variant, image_path, image_sha256, draft) in enumerate(CASES):
        try:
            frozen = picture.FrozenPicture(variant, image_path, image_sha256)
            matched = frozen.matches_draft(draft)
            note = frozen.note
        except Exception:
            print("FAIL check-error")
            failed = True
            continue

        line = f"case {i} match={'yes' if matched else 'no'} note={note!r}"
        print(line)
        if matched and i in MUST_REFUSE:
            print(f"FAIL match-on-other-bytes {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL match-changed {i}")
            failed = True

    print("FAIL npp_frozen_picture_match" if failed else "PASS npp_frozen_picture_match")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
