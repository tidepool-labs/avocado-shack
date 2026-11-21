#!/usr/bin/env python3
"""Report offline interpreter corpus coverage without printing case text."""

import argparse
from collections import Counter
from pathlib import Path
import re
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import nl_eval  # noqa: E402

TAG = re.compile(r"[a-z0-9][a-z0-9-]{0,40}")


class CoverageParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse diagnostics can echo raw argument values, including paths.
        super().error("expected --min with a positive integer and optional --corpus FILE")


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return number


def finish(findings):
    for finding in findings:
        print(f"FAIL {finding}")
    print("FAIL nl_intent_coverage" if findings else "PASS nl_intent_coverage")
    return int(bool(findings))


def main(argv=None):
    parser = CoverageParser(prog="nl_intent_coverage.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--min", required=True, type=positive_int, metavar="N")
    parser.add_argument("--corpus", type=Path, default=nl_eval.CORPUS, metavar="FILE")
    args = parser.parse_args(argv)

    try:
        regular = stat.S_ISREG(args.corpus.lstat().st_mode)
    except (OSError, ValueError):
        regular = False
    if not regular:
        return finish(["unsafe-input"])

    try:
        rows = nl_eval.load_corpus(args.corpus)
    except Exception:
        # Any loader error is a finding; exception details are not report data.
        return finish(["corpus-invalid"])

    intents = Counter(row["intent"] for row in rows)
    print(f"cases {len(rows)}")
    print(f"intents {len(nl_eval.INTENTS)}")
    findings = []
    for name in sorted(nl_eval.INTENTS):
        count = intents[name]
        print(f"intent {name} {count}")
        if count < args.min:
            findings.append(f"thin-intent {name} {count}")

    tags = Counter(tag for row in rows for tag in row.get("tags", ()) if TAG.fullmatch(tag))
    for name, count in sorted(tags.items(), key=lambda item: (-item[1], item[0]))[:30]:
        print(f"tag {name} {count}")
    odd = sum(len(row.get("tags", ())) for row in rows) - sum(tags.values())
    if odd:
        print(f"note odd-tag {odd}")
    return finish(findings)


if __name__ == "__main__":
    sys.exit(main())
