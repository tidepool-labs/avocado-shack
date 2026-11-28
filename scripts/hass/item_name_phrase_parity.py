#!/usr/bin/env python3
"""Compare the S3 item reader and S10 name edit form on the same phrases."""

import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.npp import edits, job


PHRASES = (
    "it's honey",
    "it is honey",
    "the item is honey",
    "item: honey",
    "product: honey",
    "the product is honey",
    "call it honey",
    "name it honey",
    "name: honey",
    "the name is honey",
    "rename it honey",
    "change the name to honey",
    "it's called honey",
    "this is honey",
    "its honey",
)
LEAD = re.compile(r"(?:called|named)\b", re.IGNORECASE)


def main(argv=None):
    # Even --help is an argument; this diagnostic only accepts a bare invocation.
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    try:
        grammar = edits.Grammar(npp.assets()[1])
    except Exception:
        # These pinned assets were not usable. Do not expose exception details.
        print("FAIL assets-unreadable")
        print("FAIL item_name_phrase_parity")
        return 1

    failed = False
    for position, phrase in enumerate(PHRASES, 1):
        s3 = job.owner_item(phrase)
        match = grammar.match(phrase)
        s10 = match[1].get("value") if match is not None and match[0] == "name" else None
        s3_reads, s10_reads = s3 is not None, s10 is not None
        print(f"name {position:02d} s3={'yes' if s3_reads else 'no'} s10={'yes' if s10_reads else 'no'}")
        if s3_reads != s10_reads:
            print(f"FAIL name-disagree {position:02d}")
            failed = True
        if any(value is not None and LEAD.match(value) for value in (s3, s10)):
            print(f"FAIL name-lead-kept {position:02d}")
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} item_name_phrase_parity")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
