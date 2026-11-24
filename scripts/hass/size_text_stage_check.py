#!/usr/bin/env python3
"""Compare label-size acceptance in Hass identify (S2) and copy (S5), offline."""

import argparse
import errno
from io import StringIO
import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import interpreter_local, npp
from hass.npp import copy, identify


MAX_BYTES = 16 * 1024
MAX_LINES = 200
ASSET = "hass-product-identify/"


class InputError(Exception):
    """An input failure with a fixed, safe-to-print reason."""


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default diagnostics may quote private arguments.
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: invalid arguments\n")


def read_sizes(path):
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            raise InputError("unsafe-input")
    except (FileNotFoundError, NotADirectoryError):
        raise InputError("unsafe-input") from None
    except (OSError, ValueError):
        raise InputError("unreadable-input") from None

    def open_regular(name, flags):
        # Refuse a replacement symlink and do not block on a replacement FIFO.
        return os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK)

    try:
        with open(path, "rb", opener=open_regular) as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise InputError("unsafe-input")
            data = source.read(MAX_BYTES + 1)
    except OSError as exc:
        reason = "unsafe-input" if exc.errno in (errno.ELOOP, errno.EISDIR) else "unreadable-input"
        raise InputError(reason) from None
    if len(data) > MAX_BYTES:
        raise InputError("too-large")

    try:
        text = data.decode("utf-8")
    except UnicodeError:
        raise InputError("unreadable-input") from None
    # Count physical lines (including blanks), not just the sizes retained.
    lines = list(StringIO(text, newline=None))
    if len(lines) > MAX_LINES:
        raise InputError("too-many-lines")
    return [size for line in lines if (size := line.strip())]


def kept_by_s2(size, schema):
    raw = {
        "is_product": True,
        "kind": "food",
        "item": "Raspberry jam",
        "brand_on_label": None,
        "size_text": size,
        "label_words": [],
        "visible_claims": [],
        "category_guess": "pantry",
        "has_person_or_screen": False,
        "confidence": {"kind": 0.9, "item": 0.9, "brand": 0.9, "size": 0.9, "category": 0.9},
    }
    try:
        return identify._normalize(raw, schema)["size_text"] == size
    except interpreter_local._Failed:
        return False


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL size_text_stage_check")
    return 1


def main(argv=None):
    parser = PrivateParser(prog="size_text_stage_check.py", description=__doc__, allow_abbrev=False)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--sizes", metavar="FILE", help="read UTF-8 label sizes from a file")
    sources.add_argument("--examples", action="store_true", help="use the pinned identify examples")
    args = parser.parse_args(argv)

    try:
        sizes = read_sizes(args.sizes) if args.sizes is not None else []
    except InputError as exc:
        return fail(str(exc))
    try:
        _, files, _ = npp.assets()
        schema = json.loads(files[ASSET + "identify.schema.json"])
        if not isinstance(schema, dict):
            return fail("assets-invalid")
        if args.examples:
            examples = json.loads(files[ASSET + "examples.json"])["examples"]
            if not isinstance(examples, list):
                return fail("assets-invalid")
            sizes = [size for row in examples if (size := row["output"]["size_text"]) is not None]
            if not all(isinstance(size, str) for size in sizes):
                return fail("assets-invalid")
    except Exception:
        return fail("assets-invalid")

    counts: dict[str, int] = dict.fromkeys(("both", "s2-only", "s5-only", "neither"), 0)
    buckets = {(True, True): "both", (True, False): "s2-only",
               (False, True): "s5-only", (False, False): "neither"}
    try:
        for size in sizes:
            pair = kept_by_s2(size, schema), copy.SIZE.fullmatch(size) is not None
            counts[buckets[pair]] += 1
    except Exception:
        return fail("check-error")

    print(f"sizes {len(sizes)}")
    for bucket, count in counts.items():
        print(f"{bucket} {count}")
    if disagreements := counts["s2-only"] + counts["s5-only"]:
        return fail(f"stage-disagree {disagreements}")
    print("PASS size_text_stage_check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
