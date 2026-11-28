#!/usr/bin/env python3
"""Compare the intake and edit maker readings on fixed synthetic wordings."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.npp import edits, missing, private_numbers


WORDINGS = (
    "made by Etto Farm",
    "made by Etto Farm or Bee Farm",
    "made by maybe Etto Farm",
    "made by perhaps Etto Farm",
    "made by probably Etto Farm",
    "made by Etto Farm I think",
    "made by Etto Farm I guess",
    "made by never Etto Farm",
    "made by Etto Farm rather than Bee Farm",
    "made by Etto Farm instead",
    "made by Etto Farm but not sure",
    "made by either Etto Farm or Bee Farm",
)


def main(argv=None):
    # Even --help is an argument: this checker only accepts a bare invocation.
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)

    try:
        grammar = edits.Grammar(npp.assets()[1])
    except Exception:
        print("FAIL check-error")
        print("FAIL npp_maker_hedge_parity")
        return 1

    failed = False
    for number, wording in enumerate(WORDINGS, 1):
        try:
            kept = missing._owner_maker([wording], "Honey") is not None
            public_words = private_numbers.finance(wording).public_words
            edit = edits.read(grammar, public_words, {})
            patched = any(field == "maker" for field, _ in edit.patch)
        except Exception:
            # Exception details may include input text; report only the failure.
            print("FAIL check-error")
            failed = True
            continue

        s3 = "kept" if kept else "none"
        s10 = "patch" if patched else "ask"
        print(f"maker {number:02d} s3={s3} s10={s10}")
        if kept != patched:
            print(f"FAIL hedge-split {number:02d}")
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_maker_hedge_parity")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
