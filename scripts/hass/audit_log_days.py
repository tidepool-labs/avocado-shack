#!/usr/bin/env python3
"""Count audit day files by UTC date without opening or deleting them."""

import argparse
from datetime import date, datetime, timezone
import os
from pathlib import Path
import re


DAY_FILE = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2})\.jsonl")
UTC_ORIGIN = datetime(1, 1, 1, tzinfo=timezone.utc)


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's original diagnostic can include unrecognized argument values.
        super().error("invalid arguments; see --help")


def day_count(value):
    digits = value.lstrip("0")
    if re.fullmatch(r"[0-9]{1,5}", digits):
        days = int(digits)
        if 1 <= days <= 36500:
            return days
    raise argparse.ArgumentTypeError("expected a whole number from 1 to 36500")


def aware_time(value):
    # fromisoformat also accepts arbitrary single-character separators.
    if "T" in value or " " in value:
        try:
            now = datetime.fromisoformat(value)
        except ValueError:
            pass
        else:
            if now.utcoffset() is not None:
                return now
    raise argparse.ArgumentTypeError("expected a timezone-aware ISO-8601 time")


def audit_names(state):
    # Pin both directories and refuse symlinks at either leaf. No entry is opened.
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    state_fd = os.open(state, flags)
    try:
        audit_fd = os.open("audit", flags, dir_fd=state_fd)
        try:
            # Type from the directory entry itself (no symlink follow, no open),
            # so a directory, symlink or FIFO named like a log is never a log.
            with os.scandir(audit_fd) as entries:
                return [(e.name, e.is_file(follow_symlinks=False)) for e in entries]
        finally:
            os.close(audit_fd)
    finally:
        os.close(state_fd)


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL audit_log_days")
    return 1


def main(argv=None):
    parser = PrivateParser(prog="audit_log_days.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--state", type=Path, required=True, help="state directory")
    parser.add_argument("--days", type=day_count, required=True, help="whole days (1-36500)")
    parser.add_argument("--now", type=aware_time, help="timezone-aware ISO-8601 time (default: current UTC)")
    args = parser.parse_args(argv)
    now = args.now if args.now is not None else datetime.now(timezone.utc)
    try:
        names = audit_names(args.state)
    except FileNotFoundError:
        return fail("no-audit-dir")
    except OSError:
        return fail("unsafe-audit-dir")

    # Convert the cutoff to a UTC day ordinal. The next midnight must be on
    # or before that day; integer arithmetic also handles calendar endpoints.
    cutoff_day = (now - UTC_ORIGIN).days + 1 - args.days
    files = older = invalid = other = 0
    oldest = None
    for name, regular in names:
        match = DAY_FILE.fullmatch(name)
        if match is None or not regular:
            other += 1
            continue
        try:
            day = date.fromisoformat(match[1])
        except ValueError:
            invalid += 1
            continue
        files += 1
        older += day.toordinal() < cutoff_day
        if oldest is None or day < oldest:
            oldest = day

    print(f"days {args.days}")
    print(f"files {files}")
    print(f"older {older}")
    print(f"oldest {oldest if oldest is not None else 'null'}")
    print(f"note invalid-dates {invalid}")
    print(f"note other-names {other}")
    print("deletes 0")
    print("PASS audit_log_days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
