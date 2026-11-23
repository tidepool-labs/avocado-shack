#!/usr/bin/env python3
"""Replay recorded picture reads offline and report outcomes without the text."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.npp.private_numbers import picture_problem


MAX_BYTES = 1_000_000
MAX_LINES = 2000
REASON = re.compile(r"[a-z-]{1,30}")


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's default diagnostics can echo paths in rejected arguments.
        super().error("expected --reads FILE")


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL picture_number_screen")
    return 1


def load_bytes(path):
    if not stat.S_ISREG(os.lstat(path).st_mode):
        raise OSError
    # Check the opened descriptor too: a raced replacement must not be
    # followed if it's a symlink or block on open if it's a FIFO.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise OSError
        if info.st_size > MAX_BYTES:
            return None
        return source.read(MAX_BYTES + 1)


def reject_constant(_token):
    raise ValueError


def outcome(line):
    try:
        row = json.loads(line, parse_constant=reject_constant)
    except (ValueError, RecursionError):
        return "malformed"
    if not isinstance(row, dict):
        return "malformed"
    label_words = row.get("label_words", [])
    if not isinstance(label_words, list):
        return "malformed"
    reason = picture_problem(row.get("read"), row.get("source_read"), label_words)
    if reason is None:
        return "clean"
    return reason if isinstance(reason, str) and REASON.fullmatch(reason) else "other"


def main(argv=None):
    parser = PrivateArgumentParser(prog="picture_number_screen.py", description=__doc__,
                                   allow_abbrev=False)
    parser.add_argument("--reads", required=True, metavar="FILE", help="recorded reads in JSONL")
    args = parser.parse_args(argv)

    try:
        data = load_bytes(args.reads)
    except (OSError, ValueError):
        return fail("unsafe-input")
    if data is None or len(data) > MAX_BYTES:
        return fail("too-large")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return fail("not-utf8")
    # Use physical line numbers; Unicode separators inside JSON strings are text.
    rows = [(k, line) for k, line in enumerate(text.split("\n"), 1) if line.strip()]
    if len(rows) > MAX_LINES:
        return fail("too-many-lines")

    counts = Counter()
    not_clean = 0
    for k, line in rows:
        result = outcome(line)
        print(f"line {k} {result}")
        counts[result] += 1
        not_clean += result != "clean"
    print(f"reads {len(rows)}")
    for result, count in counts.items():
        print(f"count {result} {count}")
    if not_clean:
        return fail(f"not-clean {not_clean}")
    print("PASS picture_number_screen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
