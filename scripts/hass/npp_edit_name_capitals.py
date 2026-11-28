#!/usr/bin/env python3
"""Report unwanted capitals after apostrophes in S10 name edits, offline."""

import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp  # noqa: E402
from hass.npp import edits  # noqa: E402


CASES = (
    ("from joe's honey", "supplier"),
    ("made by joe's farm", "maker"),
    ("made by miners, o'brien's corner", "makerTown"),
    ("made by o'neill farm, paso robles", "maker"),
    ("from Joe's Honey", "supplier"),
    ("made by miners orchards, st. helena", "makerTown"),
)
CAPITAL_AFTER_APOSTROPHE = re.compile(r"['’][A-Z](?![a-z])")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    if args:
        parser.error("no arguments are accepted")

    failed = False
    try:
        grammar = edits.Grammar(hass.npp.assets()[1])
    except Exception:
        # Do not echo exception text from the repository loader or reader.
        print("FAIL check-error")
        failed = True
    else:
        for i, (text, field) in enumerate(CASES):
            try:
                edit = edits.read(grammar, text, {})
                value = dict(edit.patch).get(field)
                reason = None
                if value is None:
                    reason = "no-patch"
                elif CAPITAL_AFTER_APOSTROPHE.search(value):
                    reason = "capital-after-apostrophe"
            except Exception:
                print("FAIL check-error")
                failed = True
                continue
            print(f"case {i} {field} {value!r}")
            if reason:
                print(f"FAIL {reason} {i}")
                failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_edit_name_capitals")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
