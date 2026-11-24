#!/usr/bin/env python3
"""Judge a saved check-runs capture against a release SHA, offline."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def reject_constant(_value):
    raise ValueError


def read_json(path):
    with path.open(encoding="utf-8") as source:
        return json.load(source, object_pairs_hook=unique_object,
                         parse_constant=reject_constant)


def index_runs(runs, sha):
    by_name = {}
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError
        name, head, status = (run[key] for key in ("name", "head_sha", "status"))
        conclusion, completed_at = run["conclusion"], run["completed_at"]
        if (not all(isinstance(value, str) and value for value in (name, head, status))
                or (conclusion is not None and not isinstance(conclusion, str))
                or (completed_at is not None and not isinstance(completed_at, str))):
            raise ValueError
        completed = None
        if status == "completed":
            if completed_at is None:
                raise ValueError
            completed = datetime.fromisoformat(completed_at)
            if completed.tzinfo is None:
                raise ValueError
            completed = completed.astimezone(timezone.utc)
        matching = by_name.setdefault(name, [])
        if head == sha:
            matching.append((completed, conclusion))
    return by_name


def finding(matching):
    if matching is None:
        return "missing-check"
    if not matching:
        return "wrong-head"
    if any(completed is None for completed, _ in matching):
        return "not-completed"
    latest = max(completed for completed, _ in matching)
    conclusions = {conclusion for completed, conclusion in matching if completed == latest}
    if len(conclusions) > 1:
        return "ambiguous"
    if conclusions != {"success"}:
        return "not-success"
    return None


def finish(failed):
    print(f"{'FAIL' if failed else 'PASS'} install_ci_receipt")
    return int(failed)


def refuse(reason):
    print(f"FAIL {reason}")
    return finish(True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checks", required=True, type=Path, metavar="FILE",
                        help="saved check-runs JSON object")
    parser.add_argument("--required", required=True, type=Path, metavar="FILE",
                        help="JSON array of public check names (printed in the receipt)")
    parser.add_argument("--sha", required=True, metavar="SHA", help="40 lowercase hex digits")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        return refuse("bad-sha")

    try:
        required = read_json(args.required)
        capture = read_json(args.checks)
        if (not isinstance(required, list)
                or not required
                or not all(isinstance(name, str) and name.strip() and name.isprintable()
                           for name in required)
                or not isinstance(capture, dict)):
            raise ValueError
        total, runs = capture["total_count"], capture["check_runs"]
        if type(total) is not int or total < 0 or not isinstance(runs, list):
            raise ValueError
        if total > len(runs):
            return refuse("truncated")
        by_name = index_runs(runs, args.sha)
    except (OSError, ValueError, KeyError, RecursionError, OverflowError):
        return refuse("bad-json")

    failed = False
    for name in dict.fromkeys(required):
        reason = finding(by_name.get(name))
        if reason:
            print(f"FAIL {reason} {name}")
            failed = True
        else:
            print(f"{name} success")
    return finish(failed)


if __name__ == "__main__":
    raise SystemExit(main())
