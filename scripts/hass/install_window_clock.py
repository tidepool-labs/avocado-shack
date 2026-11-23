#!/usr/bin/env python3
"""Check an attended install JSON Lines log against the kit's time budgets."""

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import re


SWITCH_BUDGET = timedelta(minutes=30)
LISTING_BUDGET = timedelta(minutes=10)
STEPS = ("switch", "listing-1", "listing-2", "listing-3")
UTC_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:[.,]\d{1,6})?)?Z", re.ASCII)


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Keep argparse's usage exit without echoing raw argument values.
        super().error("expected --log FILE and --now ISO")


def utc_time(value):
    if not isinstance(value, str) or not UTC_TIMESTAMP.fullmatch(value):
        raise ValueError("bad-time")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def reject_constant(_value):
    raise ValueError("not a JSON constant")


def read_events(path, findings):
    events = {step: {} for step in STEPS}
    try:
        with path.open("rb") as source:
            for line in source:
                try:
                    row = json.loads(line.decode("utf-8"), object_pairs_hook=unique_object,
                                     parse_constant=reject_constant)
                except (ValueError, RecursionError):
                    findings.append("bad-json")
                    continue
                if (not isinstance(row, dict) or not {"step", "event", "at"} <= row.keys()
                        or row["event"] not in ("start", "end")):
                    findings.append("bad-json")
                    continue
                step, event = row["step"], row["event"]
                if step not in STEPS:
                    findings.append("unknown-step")
                    continue
                try:
                    at = utc_time(row["at"])
                except ValueError:
                    findings.append("bad-time")
                    continue
                if event in events[step]:
                    findings.append("duplicate-event")
                elif event == "end" and "start" not in events[step]:
                    findings.append("end-without-start")
                else:
                    events[step][event] = at
    except (OSError, ValueError):
        findings.append("bad-json")
    return events


def report(events, now, findings):
    earlier = []
    for index, step in enumerate(STEPS):
        start = events[step].get("start")
        if start is None:
            continue
        end = events[step].get("end")
        if start > now or (end is not None and end > now):
            findings.append("bad-time")
            continue
        if index:
            previous_start = events[STEPS[index - 1]].get("start")
            if previous_start is None or start < previous_start:
                findings.append(f"out-of-order {step}")
            # Touching boundaries are serial; an unclosed predecessor still blocks a start.
            if any((prior_end is None or start < prior_end)
                   and (start >= prior_start or end is None or end > prior_start)
                   for prior_start, prior_end in earlier):
                findings.append(f"overlap {step}")

        elapsed = (now if end is None else end) - start
        if elapsed < timedelta(0):
            findings.append("end-before-start")
            # A malformed interval has no usable duration; do not print a negative clock.
            elapsed = timedelta(0)
        else:
            earlier.append((start, end))
        budget = LISTING_BUDGET if index else SWITCH_BUDGET
        status = "open" if end is None else "ok"
        if elapsed > budget:
            status = "over"
            findings.append(f"over {step}")
        minutes, seconds = divmod(elapsed.days * 86400 + elapsed.seconds, 60)
        print(f"{step} {minutes:02d}:{seconds:02d} {status}")


def main(argv=None):
    parser = ArgumentParser(prog="install_window_clock.py", description=__doc__)
    parser.add_argument("--log", required=True, type=Path, metavar="FILE")
    parser.add_argument("--now", required=True, metavar="ISO", help="UTC timestamp ending in Z")
    args = parser.parse_args(argv)
    findings = []
    try:
        now = utc_time(args.now)
    except ValueError:
        findings.append("bad-time")
    else:
        report(read_events(args.log, findings), now, findings)
    for finding in findings:
        print(f"FAIL {finding}")
    print("FAIL install_window_clock" if findings else "PASS install_window_clock")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
