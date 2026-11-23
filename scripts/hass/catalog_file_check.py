#!/usr/bin/env python3
"""Check a copied catalog against validated content without writing either input."""

import argparse
from collections import Counter
import json
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model


MAX_CATALOG_BYTES = 5_000_000
PUBLIC_FIELDS = frozenset(content_model.PRODUCT_PUBLIC_FIELDS + content_model.PRODUCT_OPTIONAL_PUBLIC) | {
    "availabilityState", "availabilityCheckedOn",
}


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # The standard diagnostic may echo raw argv, including private paths.
        super().error("invalid arguments (see --help)")


def _fail(reason):
    print(f"FAIL {reason}")
    print("FAIL catalog_file_check")
    return 1


def _reject_constant(_token):
    raise ValueError("not a JSON constant")


def _assignment(line, prefix):
    if not line.startswith(prefix) or not line.endswith(";"):
        raise ValueError("invalid assignment")
    return json.loads(line[len(prefix):-1], parse_constant=_reject_constant)


def _check(records, freshness, content):
    statuses = {p["id"]: p["status"] for p in content.products}
    active = {product_id for product_id, status in statuses.items() if status == "active"}
    print(f"records {len(records)}")
    print(f"active {len(active)}")

    extra_fields = not_active = invalid_ids = 0
    ids = Counter()
    inactive_details = []
    for record in records:
        extra_fields += bool(record.keys() - PUBLIC_FIELDS)
        product_id = record.get("id")
        if isinstance(product_id, str):
            ids[product_id] += 1
        if not isinstance(product_id, str) or not content_model.ID_RE.fullmatch(product_id):
            invalid_ids += 1
            not_active += 1
            continue
        status = statuses.get(product_id, "unknown")
        if status != "active":
            not_active += 1
            inactive_details.append((product_id, status))

    missing = active - ids.keys()
    duplicates = sum(count > 1 for count in ids.values())
    for product_id, status in sorted(inactive_details):
        print(f"not-active {product_id} {status}")
    for product_id in sorted(missing):
        # Validated content guarantees that each active ID matches ID_RE.
        print(f"missing {product_id}")
    if invalid_ids:
        print(f"note invalid-id {invalid_ids}")

    failed = False
    for reason, count in (("catalog-extra-field", extra_fields), ("catalog-not-active", not_active),
                          ("catalog-missing", len(missing)), ("catalog-duplicate", duplicates)):
        if count:
            print(f"FAIL {reason} {count}")
            failed = True
    if freshness.keys() != {"selectionCheckedOn"}:
        print("FAIL freshness-shape")
        failed = True

    print("FAIL catalog_file_check" if failed else "PASS catalog_file_check")
    return int(failed)


def main(argv=None):
    parser = ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--catalog", required=True, type=Path, metavar="FILE")
    parser.add_argument("--content", required=True, type=Path, metavar="DIR")
    args = parser.parse_args(argv)
    try:
        info = args.catalog.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CATALOG_BYTES
                or not stat.S_ISDIR(args.content.lstat().st_mode)):
            return _fail("unsafe-input")
    except (OSError, ValueError):
        return _fail("unsafe-input")

    try:
        content = content_model.load_and_validate(args.content, None)
    except (ValueError, OSError):  # Includes ContentError and UnicodeDecodeError.
        return _fail("content-invalid")

    try:
        with args.catalog.open("rb") as source:
            raw = source.read(MAX_CATALOG_BYTES + 1)
        if len(raw) > MAX_CATALOG_BYTES:
            return _fail("unsafe-input")
        first, second = raw.decode("utf-8").replace("\r\n", "\n").removesuffix("\n").split("\n")
        records = _assignment(first, "const catalog=")
        freshness = _assignment(second, "const catalogFreshness=")
        if (not isinstance(records, list) or not all(isinstance(item, dict) for item in records)
                or not isinstance(freshness, dict)):
            return _fail("catalog-unreadable")
    except (OSError, ValueError, RecursionError):
        return _fail("catalog-unreadable")
    return _check(records, freshness, content)


if __name__ == "__main__":
    sys.exit(main())
