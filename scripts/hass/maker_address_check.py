#!/usr/bin/env python3
"""Report Hass maker-address acceptance and extraction counts offline."""

import argparse
from io import StringIO
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.maker_site import PageError, addresses_in, check_address

MAX_BYTES = 200_000
MAX_LINES = 500


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default message can echo arbitrary command-line values.
        super().error("invalid arguments; see --help")


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL maker_address_check")
    return 1


def read_bytes(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise OSError
    # Check the opened object too: the path may have changed since lstat.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise OSError
        if info.st_size > MAX_BYTES:
            return None
        return source.read(MAX_BYTES + 1)


def main(argv=None):
    parser = PrivateParser(prog="maker_address_check.py", description=__doc__)
    parser.add_argument("--lines", required=True, type=Path, metavar="FILE")
    args = parser.parse_args(argv)
    try:
        raw = read_bytes(args.lines)
    except (OSError, ValueError):
        return fail("unsafe-input")
    if raw is None or len(raw) > MAX_BYTES:
        return fail("too-large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return fail("not-utf8")

    lines = [(k, line) for k, line in enumerate(StringIO(text, newline=None), 1) if line.strip()]
    if len(lines) > MAX_LINES:
        return fail("too-many-lines")

    refused = 0
    for k, line in lines:
        try:
            check_address(line.strip())
        except PageError:
            status = "refused"
            refused += 1
        else:
            status = "ok"
        print(f"line {k} address {status} found {len(addresses_in([line]))}")
    print(f"lines {len(lines)}")
    print(f"accepted {len(lines) - refused}")
    print(f"refused {refused}")
    if refused:
        return fail(f"refused {refused}")
    print("PASS maker_address_check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
