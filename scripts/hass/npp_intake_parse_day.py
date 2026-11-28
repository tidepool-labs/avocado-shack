#!/usr/bin/env python3
"""Check pinned intake dates and the yearless best-by/bought-day boundary offline."""

import argparse
import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.skills import item_intake


TODAY = datetime.date(2026, 11, 21)
CASES = [
    ('today', False),
    ('tomorrow', False),
    ('yesterday', True),
    ('in 3 weeks', False),
    ('Dec 20', False),
    ('Dec 20', True),
    ('Jan 3rd', False),
    ('Jan 3rd', True),
    ('11/02', False),
    ('11/02', True),
    ('2027-12-20', False),
    ('best by 20 March', False),
    ('Feb 30', False),
    ('12/20/1999', False),
    ('next week', False),
]
SIDE = (4, 5, 6, 7, 8, 9, 11)
EXPECTED = (
    "case 0 day='2026-11-21'",
    "case 1 day='2026-11-22'",
    "case 2 day='2026-11-20'",
    "case 3 day='2026-12-12'",
    "case 4 day='2026-12-20'",
    "case 5 day='2025-12-20'",
    "case 6 day='2027-01-03'",
    "case 7 day='2026-01-03'",
    "case 8 day='2027-11-02'",
    "case 9 day='2026-11-02'",
    "case 10 day='2027-12-20'",
    "case 11 day='2027-03-20'",
    "case 12 day=None",
    "case 13 day=None",
    "case 14 day=None",
)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    for i, (text, past) in enumerate(CASES):
        try:
            day = item_intake.parse_day(text, TODAY, past=past)
        except Exception:
            print("FAIL check-error")
            failed = True
            break

        line = f"case {i} day={day.isoformat() if day is not None else None!r}"
        print(line)
        if i in SIDE and day is not None and (day > TODAY if past else day < TODAY):
            print(f"FAIL wrong-side-day {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL day-changed {i}")
            failed = True

    print("FAIL npp_intake_parse_day" if failed else "PASS npp_intake_parse_day")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
