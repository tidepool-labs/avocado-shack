#!/usr/bin/env python3
"""Report whether copied store hours read for open-now status and JSON-LD."""

import argparse
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.content_model import ContentError, load_and_validate  # noqa: E402
from hass.sitegen import parse_hours  # noqa: E402

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class ReportParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse can include raw argument values in its error message.
        super().error("invalid arguments; see --help")


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL store_hours_report")
    return 1


def main(argv=None):
    parser = ReportParser(prog="store_hours_report.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", required=True, metavar="DIR", help="copied Hass content directory")
    args = parser.parse_args(argv)
    content_dir = Path(args.content)
    try:
        is_directory = bool(args.content) and stat.S_ISDIR(content_dir.lstat().st_mode)
    except (OSError, ValueError):
        is_directory = False
    if not is_directory:
        return fail("unsafe-input")

    try:
        content = load_and_validate(content_dir, None)
    except (ContentError, UnicodeDecodeError, OSError):
        return fail("content-invalid")

    lines = content.store["hours"]
    print(f"lines {len(lines)}")
    parsed = parse_hours(lines)
    days = parsed["days"]
    if days is None:
        errors = parsed["errors"]
        for error in errors:
            print(f"unreadable line {error['line']}")
        return fail(f"hours-unreadable {len(errors)}")

    unnamed = [name for name, day in zip(WEEKDAYS, days) if day is None]
    closed = sum(day is not None and day.get("closed", False) for day in days)
    opened = len(days) - closed - len(unnamed)
    print(f"open {opened}")
    print(f"closed {closed}")
    print(f"unnamed {len(unnamed)}")
    for name in unnamed:
        print(f"note unnamed {name}")
    if not opened:
        print("note no-open-day")
    print("PASS store_hours_report")
    return 0


if __name__ == "__main__":
    sys.exit(main())
