#!/usr/bin/env python3
"""Check Hass's status answers against a synthetic draft/install matrix."""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import owner_answers, voice


def aware_time(value):
    try:
        now = datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected an ISO time with a UTC offset") from None
    if now.utcoffset() is None:
        raise argparse.ArgumentTypeError("expected an ISO time with a UTC offset")
    return now


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--now", required=True, type=aware_time, metavar="ISO",
                        help="fixture time with a UTC offset")
    now = parser.parse_args(argv).now
    try:
        installed_at = (now - timedelta(hours=1)).isoformat()
    except OverflowError:
        parser.error("--now must allow an install time one hour earlier")

    installs = (
        ("none", None),
        ("installed", {"state": "installed", "installed_at": installed_at}),
        ("failed", {"state": "failed", "reason": "write failed"}),
        ("odd", {"state": "weird"}),
    )
    rows = 0
    failed = False
    for state in (*owner_answers.KNOWN, None, "bogus"):
        for label, install in installs:
            key = f"{'none' if state is None else state} {label}"
            live = success = False
            broken = True
            findings = []
            try:
                answer = owner_answers.did_it_work(
                    {"state": state, "summary": "Honey jar", "reason": ""},
                    None if install is None else install.copy(), now,
                )
            except Exception:
                findings.append("answer-error")
            else:
                try:
                    live = voice.claims_live(answer)
                    success = voice.claims_success(answer)
                    broken = bool(voice.check(answer))
                except Exception:
                    # An unreadable voice result cannot certify the row.
                    findings.append("voice")
                else:
                    expect_live = state in owner_answers.SAVED and label == "installed"
                    if live and not expect_live:
                        findings.append("false-live")
                    if expect_live and not live:
                        findings.append("missing-live")
                    if success and (state not in owner_answers.SAVED or label == "failed"):
                        findings.append("false-success")
                    if broken:
                        findings.append("voice")

            print(f"row {key} live {'yes' if live else 'no'} success {'yes' if success else 'no'} "
                  f"voice {'broken' if broken else 'ok'}")
            rows += 1
            for reason in findings:
                print(f"FAIL {reason} {key}")
                failed = True

    print(f"rows {rows}")
    print(f"{'FAIL' if failed else 'PASS'} owner_answers_truth_matrix")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
