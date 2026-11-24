#!/usr/bin/env python3
"""Check two saved service captures for a fresh start and no intervening restarts."""

import argparse
from collections import defaultdict
from itertools import groupby
from pathlib import Path
import re
import sys


STATES = {".service": ("active", "running"), ".timer": ("active", "waiting")}
NUMBERS = ("NRestarts", "MainPID", "ExecMainStartTimestampMonotonic")
KEYS = {"Id", "ActiveState", "SubState", *NUMBERS}
UNIT_NAME = re.compile(r"[A-Za-z0-9:_.@\\-]+\.[A-Za-z]+")
STATE = re.compile(r"[a-z][a-z0-9-]*")


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # Keep argparse's usage exit without echoing untrusted argv values.
        super().error("invalid or missing arguments (see --help)")


def read_capture(path):
    units = defaultdict(list)
    for nonblank, lines in groupby(path.read_text(encoding="utf-8").split("\n"),
                                   key=lambda line: bool(line.strip(" \t"))):
        if not nonblank:
            continue
        fields = {}
        for line in lines:
            key, sep, value = line.partition("=")
            if not sep or key not in KEYS or key in fields:
                raise ValueError
            fields[key] = value
        unit = fields.get("Id", "")
        if not UNIT_NAME.fullmatch(unit) or not all(
            STATE.fullmatch(fields.get(key, "")) for key in ("ActiveState", "SubState")
        ):
            raise ValueError
        if unit.endswith(".service"):
            for key in NUMBERS:
                value = fields.get(key, "")
                if not re.fullmatch(r"[0-9]+", value):
                    raise ValueError
                fields[key] = int(value)
        units[unit].append(fields)
    if not units:
        raise ValueError
    return units


def unit_findings(first, second, state, installed):
    counts = (len(first), len(second))
    if 0 in counts:
        yield "missing-unit"
    if max(counts) > 1:
        yield "duplicate-unit"
    if counts != (1, 1):
        return
    a, b = first[0], second[0]
    if any((row["ActiveState"], row["SubState"]) != state for row in (a, b)):
        yield "not-active"
    if state == STATES[".service"]:
        if a["NRestarts"] != b["NRestarts"]:
            yield "restarted"
        if min(a["MainPID"], b["MainPID"]) <= 0:
            yield "missing-process"
        if a["MainPID"] != b["MainPID"]:
            yield "pid-changed"
        if min(a["ExecMainStartTimestampMonotonic"], b["ExecMainStartTimestampMonotonic"]) <= installed:
            yield "stale-start"


def finish(failed):
    print(f"{'FAIL' if failed else 'PASS'} install_service_restart")
    return int(failed)


def main(argv=None):
    parser = Parser(prog="install_service_restart.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--first", required=True, type=Path, help="capture just after start")
    parser.add_argument("--second", required=True, type=Path, help="later capture")
    parser.add_argument("--installed-mono", required=True, type=int, metavar="INT",
                        help="install time in monotonic microseconds")
    parser.add_argument("--unit", action="append", required=True, metavar="NAME",
                        help="service or timer unit to check (repeat for each unit)")
    args = parser.parse_args(argv)
    if args.installed_mono < 0 or any(
        not UNIT_NAME.fullmatch(unit) or Path(unit).suffix not in STATES for unit in args.unit
    ):
        print("FAIL bad-capture")
        return finish(True)

    captures = []
    for path in (args.first, args.second):
        try:
            captures.append(read_capture(path))
        except (OSError, ValueError):
            print("FAIL bad-capture")
    if len(captures) != 2:
        return finish(True)

    first, second = captures
    failed = False
    for unit in dict.fromkeys(args.unit):
        findings = list(unit_findings(first.get(unit, ()), second.get(unit, ()),
                                      STATES[Path(unit).suffix], args.installed_mono))
        if args.unit.count(unit) > 1 and "duplicate-unit" not in findings:
            findings.append("duplicate-unit")
        for reason in findings:
            print(f"FAIL {reason} {unit}")
        if not findings:
            print(f"{unit} ok")
        failed |= bool(findings)
    return finish(failed)


if __name__ == "__main__":
    sys.exit(main())
