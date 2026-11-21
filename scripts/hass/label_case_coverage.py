#!/usr/bin/env python3
"""Report aggregate coverage of the offline label-reader case set."""

import argparse
from collections import Counter
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import label_eval  # noqa: E402
from hass.content_model import CATEGORIES  # noqa: E402


class CoverageParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse may include raw argument values in its diagnostic.
        super().error("invalid arguments; use --help for usage")


def positive_int(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def fail(reasons):
    for reason in reasons:
        print(f"FAIL {reason}")
    print("FAIL label_case_coverage")
    return 1


def main(argv=None):
    parser = CoverageParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--min", required=True, type=positive_int, help="minimum cases per category")
    parser.add_argument("--cases", type=Path, help="case file (defaults to the repo fixture)")
    args = parser.parse_args(argv)
    path = label_eval.CASES if args.cases is None else args.cases
    try:
        regular = stat.S_ISREG(path.lstat().st_mode)
    except (OSError, ValueError):
        regular = False
    if not regular:
        return fail(["unsafe-input"])
    try:
        cases = label_eval.load_cases(path)
    except Exception:
        return fail(["cases-invalid"])

    expected = [case["expected"] for case in cases]
    counts = Counter(row.get("category") for row in expected if "category" in row)
    print(f"cases {len(cases)}")
    for category in CATEGORIES:
        print(f"category {category} {counts[category]}")
    other = sum(count for category, count in counts.items() if category not in CATEGORIES)
    print(f"note other-category {other}")
    fields = (f"{field} {sum(field in row for row in expected)}" for field in ("name", "brand", "category"))
    print("fields", " ".join(fields))

    thin = [f"thin-category {category} {counts[category]}" for category in CATEGORIES
            if counts[category] < args.min]
    if thin:
        return fail(thin)
    print("PASS label_case_coverage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
