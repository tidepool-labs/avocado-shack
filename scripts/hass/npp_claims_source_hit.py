#!/usr/bin/env python3
"""Check the NPP source-backing pins against synthetic owner text, offline."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hass import claims


CASES = [
    ("brand", "Harbor Lane Farm", "add the harbor lane honey"),
    ("brand", "Harbor Lane Farm", "add the new honey"),
    ("brand", "Harbor Lane Farm", "not harbor, not lane, not farm"),
    ("brand", "Harbor Lane Farm", "it is not harbor lane honey"),
    ("brand", "Producer not identified", "add the honey"),
    ("url", "https://www.harborlane.example/honey", "their site is harborlane.example"),
    ("url", "https://harborlane.example", "their site is harborlane.example.org"),
    ("url", "https://harborlane.example", "see sub.harborlane.example"),
    ("url", "", "anything"),
    ("place", "Fillmore, CA", "from fillmore"),
    ("brand", "The Co", "add some honey"),
]
MUST_HIT = (1, 2, 3, 6, 7, 8)  # These cases must report an unbacked value.
EXPECTED = (
    "case 0 unbacked=no",
    "case 1 unbacked=yes",
    "case 2 unbacked=yes",
    "case 3 unbacked=yes",
    "case 4 unbacked=no",
    "case 5 unbacked=no",
    "case 6 unbacked=yes",
    "case 7 unbacked=yes",
    "case 8 unbacked=yes",
    "case 9 unbacked=no",
    "case 10 unbacked=no",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    parser.parse_args(args)
    if args:  # argparse accepts a bare '--' even without positional arguments.
        parser.error("no arguments accepted")

    failed = False
    for i, (field, new, owner) in enumerate(CASES):
        try:
            unbacked = claims._source_hit(field, new, owner)
        except Exception:
            print("FAIL check-error")
            failed = True
            break
        line = f"case {i} unbacked={'yes' if unbacked else 'no'}"
        print(line)
        if i in MUST_HIT and not unbacked:
            print(f"FAIL unbacked-source {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL source-changed {i}")
            failed = True

    print("FAIL npp_claims_source_hit" if failed else "PASS npp_claims_source_hit")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
