#!/usr/bin/env python3
"""Check the counts in saved live self-test stdout without printing details."""

import argparse
from collections import Counter
from pathlib import Path
import re


STATUSES = ("PASS", "WARN", "FAIL", "SKIP")
SUMMARY = re.compile(r"HASS-SELFTEST \S+ pass=([0-9]+) warn=([0-9]+) fail=([0-9]+) skip=([0-9]+)")


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default diagnostic can echo unexpected arguments (including paths).
        super().error("expected --stdout FILE; see --help")


def check_capture(path):
    counts = Counter()
    warnings = []
    failures = []
    last = ""
    other = 0
    try:
        if not path.is_file():
            return ["no-file"]
        with path.open(encoding="utf-8", errors="replace") as source:
            for raw in source:
                line = raw.removesuffix("\n")
                if line.strip():
                    last = line
                status, _, rest = line.partition(" ")
                if status not in STATUSES:
                    other += 1
                    continue
                counts[status] += 1
                check = rest.lstrip(" ").partition(" ")[0]
                if status == "WARN":
                    warnings.append(check)
                elif status == "FAIL":
                    failures.append(check)
    except OSError:
        return ["no-file"]

    summary = SUMMARY.fullmatch(last)
    print(f"checks {sum(counts.values())}")
    for check in warnings:
        print(f"warn {check}")
    if summary is not None:
        other -= 1  # The matched final summary is not an 'other' line.
    print(f"note other-lines {other}")

    # Compare decimal values without imposing an int digit limit or rejecting leading zeros.
    reported = [value.lstrip("0") or "0" for value in summary.groups()] if summary else []
    findings = [] if reported else ["no-summary"]
    for status, value in zip(STATUSES, reported):
        if value != str(counts[status]):
            findings.append(f"count-mismatch {status.lower()}")
    if not findings and not counts["PASS"]:
        findings.append("no-passing-check")
    findings.extend(f"failed-check {check}" for check in failures)
    if reported and reported[2] != "0":
        findings.append(f"summary-fail {reported[2]}")
    return findings


def main(argv=None):
    parser = PrivateArgumentParser(prog="selftest_summary_check.py", description=__doc__)
    parser.add_argument("--stdout", required=True, type=Path, metavar="FILE", help="saved stdout (read only)")
    args = parser.parse_args(argv)
    findings = check_capture(args.stdout)
    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} selftest_summary_check")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
