#!/usr/bin/env python3
"""Check common spellings of half-and-half against the offline NPP number screen."""

import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.npp import private_numbers


VARIANTS = (
    "half-and-half",
    "half and half",
    "Half & Half",
    "half & half",
    "half n half",
    "half 'n' half",
    "half-n-half",
    "half/half",
    "Half and Half cream",
    "organic half-and-half",
    "half-and-half creamer",
    "half-&-half",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    failed = False
    for index, spelling in enumerate(VARIANTS, 1):
        try:
            reason = private_numbers.problem(spelling)
        except Exception:
            # Report a fixed finding without exposing the exception or its input.
            print("FAIL check-error")
            failed = True
            continue
        if reason is not None and (
            not isinstance(reason, str) or not re.fullmatch(r"[a-z-]{1,40}", reason)
        ):
            print("FAIL check-error")
            failed = True
            continue

        print(f"idiom {index:02d} problem={reason if reason is not None else 'none'}")
        if reason is not None:
            print(f"FAIL idiom-refused {index:02d}")
            failed = True

    print("FAIL npp_idiom_variants" if failed else "PASS npp_idiom_variants")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
