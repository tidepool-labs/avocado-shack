#!/usr/bin/env python3
"""Check pinned refusal reasons for synthetic special titles and deal lines."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model


CASES = [
    ('Honey week', False),
    ('Two jars for $15', True),
    ('Two jars for $15', False),
    ('Call 000 555 0100 today', False),
    ('Write to shop at mail dot com', True),
    ('See cedarrow.com for more', False),
    ('<b>Honey</b> week', False),
    ('Honey\u2028week', False),
    (' Honey week', False),
    ('ab', False),
    ('Honey\u200bweek', False),
    ('10 - 15 - 20 percent off', True),
    (12, False),
]
MUST_REFUSE = (2, 3, 4, 5, 6, 7, 8, 9, 10, 12)
EXPECTED = (
    "case 0 problem=None",
    "case 1 problem=None",
    "case 2 problem='may not contain a price; put it in the deal line'",
    "case 3 problem='may not contain a phone number'",
    "case 4 problem='may not contain a web address'",
    "case 5 problem='may not contain a web address'",
    "case 6 problem=\"contains forbidden text '<'\"",
    "case 7 problem='must be one line'",
    "case 8 problem='must not be empty or start or end with a space'",
    "case 9 problem='needs at least 3 letters'",
    "case 10 problem='contains invisible or control character U+200B'",
    "case 11 problem=None",
    "case 12 problem='must be a string'",
)


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)

    failed = False
    for i, (value, deal) in enumerate(CASES):
        try:
            why = content_model.special_text_problem(value, deal=deal)
        except Exception:
            print("FAIL check-error")
            failed = True
            break

        line = f"case {i} problem={why!r}"
        print(line)
        if why is None and i in MUST_REFUSE:
            print(f"FAIL contact-in-special {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL special-changed {i}")
            failed = True

    if failed:
        print("FAIL npp_special_text_contact")
        return 1
    print("PASS npp_special_text_contact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
