#!/usr/bin/env python3
"""Report counts from a read-only copy of the Hass release books."""

import argparse
from collections import Counter
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import release_journal


class ReportParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's diagnostic can echo arbitrary input, including paths.
        super().error("expected --books DIR; see --help")


def books_path(value):
    if not value or "\0" in value:
        raise argparse.ArgumentTypeError("expected a directory path")
    return Path(value)


def entry_mode(path):
    try:
        return path.lstat().st_mode
    except FileNotFoundError:
        return None


def print_counts(journals, undos):
    states = Counter(j["state"] for j in journals)
    kinds = Counter(j["kind"] for j in journals)
    days = Counter(j["today"] for j in journals if j["push_attempts"])
    ids = {j["change_id"] for j in journals}
    print(f"journals {len(journals)}")
    for state in sorted(release_journal.STATES):
        if states[state]:
            print(f"state {state} {states[state]}")
    for kind in ("change", "undo", "baseline"):
        if kinds[kind]:
            print(f"kind {kind} {kinds[kind]}")
    print(f"open {sum(n for state, n in states.items() if state not in release_journal.CLOSED)}")
    print(f"unconfirmed {states['unconfirmed'] + states['unknown']}")
    for day, n in sorted(days.items()):
        print(f"pushed-day {day} {n}")
    print(f"note undo-orig-missing {sum(j['orig'] not in ids for j in undos)}")


def report(root):
    releases, anchor = root / "releases", root / "publish.json"
    try:
        mode = entry_mode(root)
        if mode is None or not stat.S_ISDIR(mode):
            return ["unsafe-books"]
        mode = entry_mode(releases)
        if mode is not None and not stat.S_ISDIR(mode):
            return ["unsafe-books"]
        paths = list(releases.iterdir()) if mode is not None else []
    except OSError:
        return ["unsafe-books"]

    findings = []
    journals = []
    bad = 0
    for path in paths:
        if path.name.startswith(".release-"):
            continue
        try:
            record = release_journal.validate(release_journal.read(path))
        except release_journal.BooksError:
            bad += 1
            continue
        if path.name == record["change_id"] + ".json":
            journals.append(record)
        else:
            bad += 1
    if bad:
        findings.append(f"bad-journal {bad}")

    try:
        if entry_mode(anchor) is None:
            if mode is None:
                print("books absent")
                return findings
            findings.append("anchor-missing")
        elif not bad:
            release_journal.derive(release_journal.read(anchor), journals)
    except (OSError, release_journal.BooksError):
        if not bad:
            findings.append("books-inconsistent")

    undos = [j for j in journals if j["kind"] == "undo"]
    if not bad:
        print_counts(journals, undos)
    live_undos = Counter(j["orig"] for j in undos if j["state"] == "live" and j["orig"] is not None)
    if duplicates := sum(n >= 2 for n in live_undos.values()):
        findings.append(f"undone-twice {duplicates}")
    return findings


def main(argv=None):
    parser = ReportParser(prog="release_books_report", description=__doc__, allow_abbrev=False)
    parser.add_argument("--books", required=True, type=books_path, metavar="DIR",
                        help="Hass state copy. The reader admits only regular files owned by "
                             f"the current user, with mode 0600 and at most {release_journal.MAX_BYTES} "
                             "bytes; preserve mode 0600 when copying.")
    findings = report(parser.parse_args(argv).books)
    for finding in findings:
        print(f"FAIL {finding}")
    print("FAIL release_books_report" if findings else "PASS release_books_report")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
