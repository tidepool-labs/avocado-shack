#!/usr/bin/env python3
"""Replay the S7 public-text checks on existing maker records, offline."""

import argparse
import json
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass.npp import private_numbers, validate

MAKERS = ROOT / "hass/content/makers.json"
MAKERS_CAP = 2_000_000
FIELDS = ("name", "place", "story", "url")
REASON = re.compile(r"[a-z][a-z-]{0,40}")
CHECK = "npp_existing_maker_text_check"


def _reject_constant(_token):
    raise ValueError("non-JSON constant")


def _load_makers():
    try:
        info = MAKERS.lstat()
        if not stat.S_ISREG(info.st_mode):
            return None, "input-unsafe"
        if info.st_size > MAKERS_CAP:
            return None, "input-too-large"
        with MAKERS.open("rb") as source:
            raw = source.read(MAKERS_CAP + 1)
        if len(raw) > MAKERS_CAP:
            return None, "input-too-large"
        document = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except (OSError, ValueError, RecursionError):
        return None, "input-unreadable"

    makers = document.get("makers") if isinstance(document, dict) else None
    if not isinstance(makers, dict) or any(
        not isinstance(record, dict)
        or not isinstance(record.get("name"), str)
        or not isinstance(record.get("place"), str)
        or any(key in record and not isinstance(record[key], str) for key in ("story", "url"))
        for record in makers.values()
    ):
        return None, "input-unreadable"
    return makers, None


def _finding(number, key, value):
    try:
        reason = (
            "contact" if validate._contact(value) else
            private_numbers.problem(value, frozenset(), digits_allowed=(key == "story"))
        )
    except Exception:
        return "check-error"
    if reason is None:
        return None
    if key not in FIELDS:
        return "field-invalid"
    if not isinstance(reason, str) or not REASON.fullmatch(reason):
        return "reason-invalid"
    return f"maker-text {number} {key} {reason}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        parser.error("no arguments accepted")

    makers, error = _load_makers()
    if makers is None:
        print(f"FAIL {error} makers")
        print(f"FAIL {CHECK}")
        return 1

    print(f"makers {len(makers)}")
    print(f"values {sum(isinstance(value, str) for record in makers.values() for value in record.values())}")
    failed = False
    for number, record in enumerate(makers.values(), 1):
        for key, value in record.items():
            if isinstance(value, str) and (finding := _finding(number, key, value)) is not None:
                print(f"FAIL {finding}")
                failed = True

    print(f"{'FAIL' if failed else 'PASS'} {CHECK}")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
