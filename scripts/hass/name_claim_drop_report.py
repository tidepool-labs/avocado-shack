#!/usr/bin/env python3
"""Count active product names affected by NPP's claim filter, without printing names."""

import argparse
from collections import Counter
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model
from hass.npp import copy
from hass.product_claims import drop_copy_claims


REPORT = "name_claim_drop_report"
REASON = re.compile(r"[a-z][a-z ,'-]{0,79}")


class ReportParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default diagnostic can quote unrecognized arguments or values.
        super().error("invalid arguments; see --help")


def nonnegative_int(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return number


def finish(*findings):
    for finding in findings:
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} {REPORT}")
    return int(bool(findings))


def main(argv=None):
    parser = ReportParser(prog=REPORT, description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", type=Path, default=content_model.CONTENT_DIR, metavar="DIR")
    parser.add_argument("--max-emptied", type=nonnegative_int, default=0, metavar="N")
    args = parser.parse_args(argv)

    try:
        if args.content.is_symlink() or not args.content.is_dir():
            return finish("unsafe-input")
    except (OSError, ValueError):
        return finish("unsafe-input")
    try:
        content = content_model.load_content(args.content)
    except Exception:
        return finish("content-invalid")

    reasons = Counter()
    changed_label_only = emptied_label_only = changed_owner_said = 0
    invalid_reason = False
    try:
        products = sorted(content.active_products(), key=lambda product: product["id"])
        for product in products:
            name = product["name"]
            label_only, dropped = drop_copy_claims(name, "")
            owner_said, _ = drop_copy_claims(name, name)
            if label_only != name:
                changed_label_only += 1
                if not copy.plain(label_only):
                    emptied_label_only += 1
            changed_owner_said += owner_said != name
            for reason in dropped:
                if isinstance(reason, str) and REASON.fullmatch(reason):
                    reasons[reason] += 1
                else:
                    invalid_reason = True
    except Exception:
        # No partial counts or exception details on an incomplete check.
        return finish("check-error")

    print(f"products {len(products)}")
    print(f"changed-label-only {changed_label_only}")
    print(f"emptied-label-only {emptied_label_only}")
    print(f"changed-owner-said {changed_owner_said}")
    for reason, count in sorted(reasons.items()):
        print(f"reason {count} {reason}")

    findings = []
    if invalid_reason:
        findings.append("reason-invalid")
    if emptied_label_only > args.max_emptied:
        findings.append(f"emptied-names {emptied_label_only} {args.max_emptied}")
    return finish(*findings)


if __name__ == "__main__":
    sys.exit(main())
