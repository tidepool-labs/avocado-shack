#!/usr/bin/env python3
"""Screen active catalog copy locally without printing the copy or its numbers."""

import argparse
from collections import Counter
from pathlib import Path
import re
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.content_model import ID_RE, load_and_validate
from hass.npp.private_numbers import problem


FIELDS = ("name", "description")
REASON_RE = re.compile(r"^[a-z-]{1,30}$")


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse can echo unrecognized arguments, including private input paths.
        super().error("expected --content DIR (see --help)")


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL catalog_number_screen")
    return 1


def main(argv=None):
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", required=True, type=Path, metavar="DIR",
                        help="local copy of the Hass content directory")
    directory = parser.parse_args(argv).content
    try:
        # lstat deliberately examines the argument itself without following a symlink.
        if not stat.S_ISDIR(directory.lstat().st_mode):
            return fail("unsafe-input")
    except (OSError, ValueError):
        return fail("unsafe-input")
    try:
        content = load_and_validate(directory, None)
    except (OSError, ValueError):  # Includes ContentError and decode errors.
        return fail("content-invalid")

    counts = {field: Counter() for field in FIELDS}
    notes = []
    active = screened = flagged = invalid_ids = 0
    for product in content.products:
        status = product.get("status")
        if not isinstance(status, str) or status != "active":
            continue
        active += 1
        flagged_fields = []
        for field in FIELDS:
            reason = problem(product[field])
            screened += 1
            if reason is None:
                counts[field]["clean"] += 1
            else:
                flagged += 1
                flagged_fields.append(field)
                if isinstance(reason, str) and REASON_RE.fullmatch(reason):
                    counts[field][reason] += 1
        if flagged_fields:
            product_id = product.get("id")
            if isinstance(product_id, str) and ID_RE.fullmatch(product_id):
                notes.extend((field, product_id) for field in flagged_fields)
            else:
                invalid_ids += 1

    print(f"active {active}")
    print(f"screened {screened}")
    for field in FIELDS:
        for reason, count in sorted(counts[field].items()):
            print(f"count {field} {reason} {count}")
    for field, product_id in notes:
        print(f"note flagged {field} {product_id}")
    if invalid_ids:
        print(f"note invalid-id {invalid_ids}")
    if flagged:
        return fail(f"flagged {flagged}")
    print("PASS catalog_number_screen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
