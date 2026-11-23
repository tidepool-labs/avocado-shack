#!/usr/bin/env python3
"""Check a copied producers file against validated content without changing either."""

import argparse
import json
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.content_model import MAKER_FIELDS, load_and_validate


MAX_BYTES = 5_000_000
FIELDS = (*MAKER_FIELDS, "hidden")
JS_PREFIX = "const producers="
ABSENT = object()


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's original message can echo an input path or an unknown flag.
        super().error("invalid arguments; see --help")


def reject_constant(_token):
    raise ValueError("not a JSON value")


def parse_producers(path, raw):
    text = raw.decode("utf-8")
    if path.name.endswith(".js"):
        text = text.removesuffix("\n")
        if not text.startswith(JS_PREFIX + "{") or not text.endswith("};"):
            raise ValueError("invalid JS wrapper")
        text = text[len(JS_PREFIX):-1]
    elif not path.name.endswith(".json"):
        raise ValueError("invalid file suffix")
    records = json.loads(text, parse_constant=reject_constant)
    if not isinstance(records, dict):
        raise ValueError("expected a JSON object")
    return records


def differing_fields(actual, expected):
    if not isinstance(actual, dict):
        return ["other"]
    # Validated records contain strings and (for hidden) a boolean; don't
    # let Python's True == 1 treat a numeric hidden flag as unchanged.
    fields = []
    for field in FIELDS:
        left, right = actual.get(field, ABSENT), expected.get(field, ABSENT)
        if type(left) is not type(right) or left != right:
            fields.append(field)
    if (actual.keys() ^ expected.keys()).difference(FIELDS):
        fields.append("other")
    return fields


def finish(*findings):
    for finding in findings:
        print(f"FAIL {finding}")
    print("FAIL producers_file_check" if findings else "PASS producers_file_check")
    return 1 if findings else 0


def main(argv=None):
    parser = PrivateParser(prog="producers_file_check", description=__doc__, allow_abbrev=False)
    parser.add_argument("--producers", required=True, type=Path, metavar="FILE")
    parser.add_argument("--content", required=True, type=Path, metavar="DIR")
    args = parser.parse_args(argv)

    try:
        source = args.producers.lstat()
        if (not stat.S_ISREG(source.st_mode) or source.st_size > MAX_BYTES
                or not stat.S_ISDIR(args.content.lstat().st_mode)):
            return finish("unsafe-input")
    except (OSError, ValueError):
        return finish("unsafe-input")

    try:
        makers = load_and_validate(args.content, None).makers
    except (OSError, ValueError):  # Includes ContentError and UTF-8 decode errors.
        return finish("content-invalid")

    try:
        with args.producers.open("rb") as source_file:
            raw = source_file.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return finish("unsafe-input")
        listed = parse_producers(args.producers, raw)
    except (OSError, ValueError, RecursionError):
        return finish("producers-unreadable")

    hidden = {key for key, maker in makers.items() if "hidden" in maker}
    visible = makers.keys() - hidden
    print(f"listed {len(listed)}")
    print(f"visible {len(visible)}")
    print(f"hidden {len(hidden)}")

    changed = 0
    for number, key in enumerate(sorted(makers), 1):
        if key not in listed:
            continue
        fields = differing_fields(listed[key], makers[key])
        for field in fields:
            print(f"differs maker#{number} {field}")
        if fields and key in visible:
            changed += 1

    counts = (
        ("hidden-maker", len(hidden & listed.keys())),
        ("maker-missing", len(visible - listed.keys())),
        ("unknown-maker", len(listed.keys() - makers.keys())),
        ("maker-differs", changed),
    )
    return finish(*(f"{reason} {count}" for reason, count in counts if count))


if __name__ == "__main__":
    sys.exit(main())
