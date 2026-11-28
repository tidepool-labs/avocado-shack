#!/usr/bin/env python3
"""Compare NPP money screens offline without printing the fixture text."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.npp import evidence, picture, private_numbers


PHRASES = (
    "$4", "4 dollars", "4 bucks", "50 cents", "50c", "4.99", "4,99", "4 . 99",
    "\u20ac4", "\u00a34", "\u00a5400", "4 usd", "USD 4", "\u00a250", "4 euros",
    "4.5", "12.50 lb",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    failed = False
    yes_no = ("no", "yes")
    for index, phrase in enumerate(PHRASES, 1):
        picture_money = bool(picture._MONEY.search(phrase))
        try:
            s7_money = private_numbers.problem(phrase) == "money"
        except Exception:
            # Do not expose the exception text or report an unread screen as "no".
            print("FAIL check-error")
            failed = True
            continue
        evidence_private = bool(evidence._PRIVATE.search(phrase))
        print(f"money {index:02d} picture={yes_no[picture_money]} "
              f"s7={yes_no[s7_money]} evidence={yes_no[evidence_private]}")
        if picture_money != s7_money:
            print(f"FAIL money-disagree {index:02d}")
            failed = True

    print("FAIL npp_money_screen_parity" if failed else "PASS npp_money_screen_parity")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
