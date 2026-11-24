#!/usr/bin/env python3
"""Check one saved snapshot, never the current state of a service.

Usage: python3 scripts/hass/install_quiescence.py SNAPSHOT.json

The UTF-8 JSON file must be regular (not a symlink) and contain an array
of four observations in any order.
Each observation has exactly these fields (example row):
    {"unit": "hass-health.service", "exit_code": 3,
     "stdout": "inactive\n", "stderr": ""}
Keep stdout and stderr separate. Only literal `inactive`, with or without
its single terminating LF, counts. Exit 0 means the snapshot passes; exit 1
means the snapshot does not establish that all four units were inactive.
"""

import argparse
import json
import os
from pathlib import Path
import stat


UNITS = frozenset({
    "hass-receiver.service", "hass-worker.service",
    "hass-health.timer", "hass-health.service",
})
FIELDS = {"unit", "exit_code", "stdout", "stderr"}
MAX_BYTES = 8192


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def snapshot_passes(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return False
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(MAX_BYTES + 1)
        finally:
            os.close(fd)
        if len(data) > MAX_BYTES:
            return False
        rows = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object)
    except (OSError, ValueError, RecursionError):
        return False

    if not isinstance(rows, list) or len(rows) != len(UNITS):
        return False
    remaining = set(UNITS)
    for row in rows:
        if not isinstance(row, dict) or row.keys() != FIELDS:
            return False
        unit = row["unit"]
        if not isinstance(unit, str) or unit not in remaining:
            return False
        if (type(row["exit_code"]) is not int or row["exit_code"] != 3
                or row["stdout"] not in ("inactive", "inactive\n")
                or row["stderr"] != ""):
            return False
        remaining.remove(unit)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check saved unit observations only.")
    parser.add_argument("snapshot", type=Path, help="saved UTF-8 JSON observations")
    args = parser.parse_args(argv)
    if snapshot_passes(args.snapshot):
        print("PASS: All four units were reported inactive in the saved snapshot.")
        return 0
    print("FAIL: The saved snapshot does not establish that all four units were inactive.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
