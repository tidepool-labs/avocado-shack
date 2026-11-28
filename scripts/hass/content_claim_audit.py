#!/usr/bin/env python3
"""Screen active product descriptions in an offline catalog copy."""

import argparse
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model, live_policy, product_claims


ORIGIN = "origin/organic"


class AuditParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's usual error can echo an unrecognized argument or path.
        super().error("expected --content DIR (see --help)")


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL content_claim_audit")
    return 1


def main(argv=None):
    parser = AuditParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", type=Path, required=True, help="read-only copy of hass/content")
    directory = parser.parse_args(argv).content
    if directory.is_symlink() or not directory.is_dir():
        return fail("unsafe-input")
    try:
        products = content_model.load_content(directory).products
    except (content_model.ContentError, UnicodeError, OSError):
        return fail("content-invalid")
    if not isinstance(products, list):
        return fail("content-invalid")

    active = malformed = 0
    totals = Counter()
    origins = []
    findings = []
    for product in products:
        if not isinstance(product, dict):
            malformed += 1
            continue
        if product.get("status") != "active":
            continue
        active += 1
        description = product.get("description")
        names = live_policy._names([{"before": None, "after": product}])
        _, kinds = product_claims.protected(description if isinstance(description, str) else "", product, names)
        if not kinds:
            continue
        labels = sorted(kind.replace(" ", "_") for kind in kinds)
        totals.update(labels)
        product_id = product.get("id")
        # The loader checks envelopes, not records. Never echo arbitrary text as an ID.
        if not isinstance(product_id, str) or not content_model.ID_RE.fullmatch(product_id):
            product_id = "-"
        if kinds == {ORIGIN}:
            origins.append(product_id)
        else:
            findings.append((product_id, ",".join(labels)))

    print(f"active {active}")
    if malformed:
        print(f"note malformed {malformed}")
    for label, count in sorted(totals.items()):
        print(f"kind {label} {count}")
    print(f"note origin {len(origins)}")
    for product_id in sorted(origins):
        print(f"origin {product_id}")
    for product_id, labels in sorted(findings):
        print(f"claim {product_id} {labels}")
    if findings:
        return fail(f"claim {len(findings)}")
    print("PASS content_claim_audit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
