#!/usr/bin/env python3
"""Screen a local catalog copy without reporting product text or private amounts."""

import argparse
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import content_model
from hass.npp import private_numbers


TEXT_FIELDS = ("name", "brand", "displayBrand", "description", "imageAlt")


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error can quote unrecognized arguments verbatim.
        super().error("invalid arguments")


def read_private(path: Path) -> set[Decimal]:
    amounts = set()
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                amount = Decimal(line.strip())
                if not amount.is_finite():
                    raise ValueError("non-finite amount")
                amounts.add(amount)
    return amounts


def fail(reason: str) -> int:
    print(f"FAIL {reason}")
    print("FAIL content_number_scan")
    return 1


def report(products: list[dict], private: set[Decimal]) -> int:
    active = fields = malformed = 0
    findings = defaultdict(list)
    notes = []
    counts: Counter[str] = Counter()
    for product in products:
        if not isinstance(product, dict):
            malformed += 1
            continue
        if product.get("status") != "active":
            continue
        active += 1
        product_id = product.get("id")
        # The loader checks envelopes, not individual IDs. Never echo an invalid ID.
        if not isinstance(product_id, str) or not content_model.ID_RE.fullmatch(product_id):
            product_id = "-"
        for field in TEXT_FIELDS:
            text = product.get(field)
            if not isinstance(text, str):
                continue
            fields += 1
            reason = private_numbers.problem(text, private)
            if reason is None:
                continue
            counts[reason] += 1
            if reason in ("number-unclear", "unsupported-number"):
                notes.append((product_id, field, reason))
            else:
                findings[reason].append((product_id, field))

    print(f"active {active}")
    print(f"fields {fields}")
    if malformed:
        print(f"note malformed {malformed}")
    for reason, count in sorted(counts.items()):
        print(f"reason {reason} {count}")
    for product_id, field, reason in sorted(notes):
        print(f"number {product_id} {field} {reason}")
    failed = False
    for reason, label, failure in (("money", "money", "money-in-text"),
                                   ("private-number", "private", "private-number")):
        if counts[reason]:
            for product_id, field in sorted(findings[reason]):
                print(f"{label} {product_id} {field}")
            print(f"FAIL {failure} {counts[reason]}")
            failed = True
    print("FAIL content_number_scan" if failed else "PASS content_number_scan")
    return int(failed)


def main(argv=None) -> int:
    parser = PrivateArgumentParser(prog="content_number_scan.py", description=__doc__)
    parser.add_argument("--content", required=True, type=Path, help="copy of a hass/content directory")
    parser.add_argument("--private-file", type=Path, help="optional UTF-8 file of decimal amounts, one per line")
    args = parser.parse_args(argv)
    try:
        if not stat.S_ISDIR(args.content.lstat().st_mode) or (
            args.private_file is not None and not stat.S_ISREG(args.private_file.lstat().st_mode)
        ):
            return fail("unsafe-input")
    except (OSError, ValueError):
        return fail("unsafe-input")

    try:
        content = content_model.load_content(args.content)
    except (ValueError, OSError):  # Includes ContentError and decoding failures.
        return fail("content-invalid")
    if not isinstance(content.products, list):
        return fail("content-invalid")

    try:
        private = set() if args.private_file is None else read_private(args.private_file)
    except (InvalidOperation, OSError, ValueError):
        return fail("bad-private-file")
    return report(content.products, private)


if __name__ == "__main__":
    sys.exit(main())
