#!/usr/bin/env python3
"""Count privacy findings in listing receipts in a copied NPP media folder."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.npp.receipt import JOB_RE, read_artifact  # noqa: E402
from hass.publish_live import PATTERNS  # noqa: E402


PRIVATE_KEYS = {"cost", "quantity", "qty", "private_cost", "private_quantity"}
REASONS = ("unreadable-receipt", "private-key", "has-cost-not-bool",
           *(f"pattern-{name}" for name in PATTERNS))


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse errors can include an unexpected argument's raw value.
        super().error("invalid arguments; use --media DIR")


class ObjectPairs(list):
    """Keep even a repeated key's earlier values available to the scanner."""


def findings(receipt):
    try:
        document = json.loads(read_artifact(receipt), object_pairs_hook=ObjectPairs)
    except (OSError, ValueError, RecursionError):
        return {"unreadable-receipt"}
    if not isinstance(document, ObjectPairs):
        return {"unreadable-receipt"}

    hits = set()
    pending: list[object] = [document]
    while pending:
        value = pending.pop()
        if isinstance(value, ObjectPairs):
            for key, child in value:
                if key.casefold() in PRIVATE_KEYS:
                    hits.add("private-key")
                if key == "has_cost" and not isinstance(child, bool):
                    hits.add("has-cost-not-bool")
                pending.append(child)
        elif isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, str):
            hits.update(f"pattern-{name}" for name, rx in PATTERNS.items() if rx.search(value))
    return hits


def scan(root):
    if root.is_symlink():
        return 0, 0, ["no-npp-dir"]
    try:
        with os.scandir(root) as entries:
            jobs = [Path(entry.path) for entry in entries
                    if re.fullmatch(JOB_RE, entry.name) and entry.is_dir(follow_symlinks=False)]
    except OSError:
        return 0, 0, ["no-npp-dir"]

    counts = Counter()
    receipts = clean = 0
    for job in jobs:
        receipt = job / "receipt.json"
        try:
            receipt.lstat()
        except FileNotFoundError:
            # A job folder can contain a card but no receipt yet.
            continue
        except OSError:
            hits = {"unreadable-receipt"}
        else:
            hits = findings(receipt)
        receipts += 1
        clean += not hits
        counts.update(hits)
    return receipts, clean, [f"{reason} {counts[reason]}" for reason in REASONS if counts[reason]]


def main(argv=None):
    parser = PrivateArgumentParser(prog="npp_receipt_privacy.py", description=__doc__,
                                   allow_abbrev=False)
    parser.add_argument("--media", required=True, type=Path, metavar="DIR")
    args = parser.parse_args(argv)
    receipts, clean, failures = scan(args.media / "npp")
    print(f"receipts {receipts}")
    print(f"clean {clean}")
    for reason in failures:
        print(f"FAIL {reason}")
    print("FAIL npp_receipt_privacy" if failures else "PASS npp_receipt_privacy")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
