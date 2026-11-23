#!/usr/bin/env python3
"""Report hike status and stale scheduled events from a read-only content copy."""

import argparse
from datetime import date, datetime
from pathlib import Path
from stat import S_ISDIR
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model


class ReportParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse diagnostics can echo raw arguments, including input paths.
        super().error("invalid arguments (see --help)")


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL events_state_report")
    return 1


def main(argv=None):
    parser = ReportParser(prog="events_state_report.py", description=__doc__)
    parser.add_argument("--content", required=True, type=Path, metavar="DIR",
                        help="copy of the Hass content directory")
    parser.add_argument("--today", type=date.fromisoformat, metavar="YYYY-MM-DD",
                        help="report date (defaults to the shop's Pacific date)")
    args = parser.parse_args(argv)
    try:
        is_directory = S_ISDIR(args.content.lstat().st_mode)  # Don't follow a symlink.
    except OSError:
        is_directory = False
    if not is_directory:
        return fail("unsafe-input")
    try:
        content = content_model.load_and_validate(args.content, None)
    except (content_model.ContentError, UnicodeDecodeError, OSError):
        return fail("content-invalid")

    today = args.today or content_model.shop_today()
    events = content.community["events"]
    counts = dict.fromkeys(content_model.EVENT_STATUSES, 0)
    stale = []
    stale_count = invalid_ids = no_recap = no_note = no_capacity = 0
    for event in events:
        status = event["status"]
        counts[status] += 1
        event_id = event.get("id")
        safe_id = isinstance(event_id, str) and bool(content_model.ID_RE.fullmatch(event_id))
        if not safe_id:
            invalid_ids += 1
        if status == "scheduled":
            starts = datetime.fromisoformat(event["startsAt"])
            days = (today - starts.astimezone(content_model.SHOP_TZ).date()).days
            if days > 0:
                stale_count += 1
                if safe_id:
                    stale.append((event_id, days))
            if event.get("rsvpEnabled") is True and "capacity" not in event:
                no_capacity += 1
        elif status == "completed" and not event.get("recap", "").strip():
            no_recap += 1
        elif status == "cancelled" and "cancelNote" not in event:
            no_note += 1

    print(f"events {len(events)}")
    for status, count in counts.items():
        print(f"{status} {count}")
    for event_id, days in sorted(stale):
        print(f"stale {event_id} {days}")
    print(f"note completed-no-recap {no_recap}")
    print(f"note cancelled-no-note {no_note}")
    print(f"note rsvp-no-capacity {no_capacity}")
    if invalid_ids:
        print(f"note invalid-id {invalid_ids}")
    if stale_count:
        return fail(f"stale-scheduled {stale_count}")
    print("PASS events_state_report")
    return 0


if __name__ == "__main__":
    sys.exit(main())
