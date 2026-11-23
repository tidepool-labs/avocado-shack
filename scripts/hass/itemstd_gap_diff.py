#!/usr/bin/env python3
"""Compare new item-standard gaps between two saved content directories."""

import argparse
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model, itemstd  # noqa: E402


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse can include raw arguments in its error message.
        super().error("invalid arguments (see --help)")


def is_directory(path):
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except (OSError, ValueError):
        return False


def active_missing(report):
    missing = {}
    for row in report["products"]:
        if row["status"] == "active":
            missing.setdefault(row["id"], set()).update(row["missing"])
    return missing


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL itemstd_gap_diff")
    return 1


def main(argv=None):
    parser = PrivateArgumentParser(prog="itemstd_gap_diff.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--before", required=True, type=Path, metavar="DIR")
    parser.add_argument("--after", required=True, type=Path, metavar="DIR")
    args = parser.parse_args(argv)
    if not (is_directory(args.before) and is_directory(args.after)):
        return fail("unsafe-input")
    try:
        before = itemstd.report_for(args.before)
        after = itemstd.report_for(args.after)
    except (itemstd.ReportError, OSError, ValueError):
        return fail("content-invalid")

    for label, field in (("active", "products_active"), ("gaps", "products_with_an_information_gap")):
        print(f"{label} before {before['summary'][field]} after {after['summary'][field]}")

    before_missing = active_missing(before)
    after_missing = active_missing(after)
    codes = [code for code in itemstd.ASK_ORDER if code in itemstd.CODES]
    added = invalid_ids = 0
    for product_id, missing in sorted(after_missing.items()):
        new_gaps = missing.difference(before_missing.get(product_id, ()))
        valid_id = content_model.ID_RE.fullmatch(product_id) is not None
        if not valid_id:
            invalid_ids += 1
        for code in codes:
            if code in new_gaps:
                added += 1
                if valid_id:
                    print(f"gap {product_id} {code}")
    if invalid_ids:
        print(f"note invalid-id {invalid_ids}")
    if added:
        return fail(f"gap-added {added}")
    print("PASS itemstd_gap_diff")
    return 0


if __name__ == "__main__":
    sys.exit(main())
