#!/usr/bin/env python3
"""Check product claim receipts in offline copies; report counts only."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model, media, product_claims  # noqa: E402


SOURCES = (("label", "labelSource", "labels"), ("owner", "ownerSource", "owner-claims"))
FINDINGS = ("bad-provenance", "receipt-missing", "receipt-unsafe", "receipt-mismatch")


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse can include unrecognized argument values in its diagnostic.
        super().error("invalid arguments; see --help")


def safe_directory(path, *, optional=False):
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except FileNotFoundError:
        return optional
    except OSError:
        return False


def receipt_result(folder, kind, provenance):
    photo, text = provenance["photo"], provenance["text"]
    suffix = ""
    if kind == "owner":
        suffix = "-" + hashlib.sha256(json.dumps(text, sort_keys=True).encode()).hexdigest()
    path = folder / (photo + suffix + ".json")
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            return "receipt-unsafe"
        if info.st_size > media.SIDECAR_MAX:
            return "receipt-mismatch"
        # Never follow a replacement leaf or block waiting on a FIFO.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return "receipt-unsafe"
            raw = stream.read(media.SIDECAR_MAX + 1)
    except FileNotFoundError:
        return "receipt-missing"
    except OSError:
        return "receipt-unsafe"

    if len(raw) > media.SIDECAR_MAX:
        return "receipt-mismatch"
    try:
        receipt = json.loads(raw)
    except (ValueError, RecursionError):
        return "receipt-mismatch"
    if not isinstance(receipt, dict) or receipt.get("source") != kind or receipt.get("photo") != photo:
        return "receipt-mismatch"
    lines = receipt.get("text")
    if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
        return "receipt-mismatch"
    return "receipts-ok" if set(text).issubset(lines) else "receipt-mismatch"


def finish(reasons):
    for reason in reasons:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if reasons else 'PASS'} claim_receipts_check")
    return int(bool(reasons))


def main(argv=None):
    parser = PrivateParser(prog="claim_receipts_check.py", description=__doc__)
    parser.add_argument("--content", required=True, type=Path, help="copied content directory")
    parser.add_argument("--media", required=True, type=Path, help="copied media directory")
    args = parser.parse_args(argv)

    if not (safe_directory(args.content) and safe_directory(args.media)
            and all(safe_directory(args.media / folder, optional=True) for _, _, folder in SOURCES)):
        return finish(["unsafe-input"])
    try:
        products = content_model.load_content(args.content).products
    except (ValueError, OSError, RecursionError):  # includes ContentError and decode errors
        return finish(["content-invalid"])
    if not isinstance(products, list):
        return finish(["content-invalid"])

    counts = Counter()
    for product in products:
        if not isinstance(product, dict):
            counts["malformed"] += 1
            continue
        for kind, field, folder in SOURCES:
            if field not in product:
                continue
            counts[f"{kind}-sourced"] += 1
            provenance = product[field]
            if not product_claims.valid_source(provenance, kind):
                counts["bad-provenance"] += 1
                continue
            counts[receipt_result(args.media / folder, kind, provenance)] += 1

    for key in ("label-sourced", "owner-sourced", "receipts-ok"):
        print(f"{key} {counts[key]}")
    if counts["malformed"]:
        print(f"note malformed {counts['malformed']}")
    return finish([f"{key} {counts[key]}" for key in FINDINGS if counts[key]])


if __name__ == "__main__":
    raise SystemExit(main())
