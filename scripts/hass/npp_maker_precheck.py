#!/usr/bin/env python3
"""Check whole pilot captions for maker matches without printing their text."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.npp.missing import _maker, _owner_maker


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse can include raw arguments (including paths) in its diagnostic.
        super().error("invalid arguments; see --help")


def _read(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("expected a regular file, not a symlink")
    return path.read_text(encoding="utf-8")


def _reject_constant(_value):
    raise ValueError("not a JSON number")


def _object(text):
    value = json.loads(text, parse_constant=_reject_constant)
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def main(argv=None):
    parser = PrivateParser(prog="npp_maker_precheck.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", required=True, type=Path, metavar="DIR")
    parser.add_argument("--captions", required=True, type=Path, metavar="FILE")
    args = parser.parse_args(argv)
    print("note whole-caption")
    failed = False

    try:
        lines = [line for line in _read(args.captions).split("\n") if line.strip()]
    except (OSError, ValueError):
        lines = []
    if not lines:
        print("FAIL bad-captions")
        failed = True

    try:
        makers = _object(_read(args.content / "makers.json")).get("makers")
        if not isinstance(makers, dict) or not all(
            isinstance(record, dict) and isinstance(record.get("name"), str)
            for record in makers.values()
        ):
            raise ValueError("invalid makers schema")
    except (OSError, ValueError, RecursionError):
        print("FAIL unreadable makers")
        makers = None
        failed = True

    for i, line in enumerate(lines, 1):
        try:
            row = _object(line)
            item, caption = row.get("item"), row.get("caption")
            if not isinstance(item, str) or not isinstance(caption, str):
                raise ValueError("expected string item and caption")
        except (ValueError, RecursionError):
            print(f"FAIL bad-line {i}")
            failed = True
            continue
        if makers is None:
            continue
        state = _maker(_owner_maker([caption], item), {}, makers).state
        print(f"caption {i} maker {state}")
        if state == "near":
            print(f"FAIL near {i}")
            failed = True

    print("FAIL npp_maker_precheck" if failed else "PASS npp_maker_precheck")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
