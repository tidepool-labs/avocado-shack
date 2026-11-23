#!/usr/bin/env python3
"""Compare the pinned Hass TLD set with a saved IANA list (offline)."""

import argparse
import os
from pathlib import Path
import re
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import tlds  # noqa: E402


MAX_BYTES = 1_000_000
ENDING = re.compile(r"(?:[a-z0-9-]{1,63}|xn--[a-z0-9-]{1,59})")
VERSION = re.compile(r"\bVersion ([0-9]+)\b")


class InputError(ValueError):
    """An input refusal with a fixed, path-free reason."""


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's original diagnostic can include unrecognized path arguments.
        super().error("expected --iana FILE")


def read_iana(path):
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            raise InputError("unsafe-input")
        # Recheck the opened file; a replaced leaf must not follow a symlink
        # or block on a FIFO between lstat and open.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise InputError("unsafe-input")
            if metadata.st_size > MAX_BYTES:
                raise InputError("too-large")
            with open(fd, "rb", closefd=False) as source:
                raw = source.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise InputError("too-large")
        finally:
            os.close(fd)
    except OSError:
        raise InputError("unsafe-input") from None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise InputError("not-utf8") from None


def version(text):
    match = VERSION.search(text)
    return match[1] if match else "none"


def compare(text):
    iana_version = None
    endings = set()
    malformed = 0
    for number, line in enumerate(text.split("\n"), 1):
        line = line.removesuffix("\r")
        if line.startswith("#"):
            if iana_version is None:
                iana_version = version(line)
        elif line.strip():
            ending = line.lower()
            if ENDING.fullmatch(ending):
                endings.add(ending)
            else:
                malformed += 1
                if malformed <= 5:
                    print(f"FAIL iana-malformed {number}")
    if malformed > 5:
        print(f"note more-malformed {malformed - 5}")
    if not endings:
        print("FAIL iana-empty")

    added = endings - tlds.TLDS
    removed = tlds.TLDS - endings
    print(f"iana-version {iana_version or 'none'}")
    print(f"pinned-version {version(tlds.__doc__ or '')}")
    print(f"iana {len(endings)}")
    print(f"pinned {len(tlds.TLDS)}")
    print(f"added {len(added)}")
    print(f"removed {len(removed)}")
    for label, changes in (("added", added), ("removed", removed)):
        for ending in sorted(changes)[:20]:
            print(f"note {label} {ending}")
    if added or removed:
        print(f"FAIL stale added {len(added)} removed {len(removed)}")
    return not (malformed or not endings or added or removed)


def main(argv=None):
    parser = ArgumentParser(prog="tlds_freshness_check.py", description=__doc__,
                            allow_abbrev=False)
    parser.add_argument("--iana", required=True, metavar="FILE", help="saved IANA list")
    args = parser.parse_args(argv)
    try:
        passed = compare(read_iana(args.iana))
    except InputError as error:
        print(f"FAIL {error}")
        passed = False
    print(f"{'PASS' if passed else 'FAIL'} tlds_freshness_check")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
