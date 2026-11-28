#!/usr/bin/env python3
"""Check whether S3 reads makers from singular and plural possessives."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.npp import missing


CASES = (
    ("Joe's honey", "Joe"),
    ("Joe’s honey", "Joe"),
    ("Miners' honey", "Miners"),
    ("Miners’ honey", "Miners"),
    ("add Miners' honey", "Miners"),
    ("made by Miners", "Miners"),
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    parser.parse_args(args)
    if args:  # argparse accepts a bare '--'; this diagnostic takes no arguments.
        parser.error("no arguments are accepted")

    failed = False
    for i, (text, expected) in enumerate(CASES):
        try:
            got = missing._owner_maker([text], "Honey")
        except Exception:
            print(f"case {i} maker=none")
            print("FAIL check-error")
        else:
            print(f"case {i} maker={got or 'none'}")
            if got == expected:
                continue
            reason = "maker-missed" if got is None else "maker-wrong"
            print(f"FAIL {reason} {i}")
        failed = True

    if failed:
        print("FAIL npp_plural_possessive_maker")
        return 1
    print("PASS npp_plural_possessive_maker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
