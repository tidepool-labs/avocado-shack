#!/usr/bin/env python3
"""Check a short reply is read without the model only when it is just the asked value.

Offline drift guard for ``openreq.cheap_answer``: runs 14 fixed replies through it
(no ask, content, aliases or today) and reports a finding when a long or
"says more" reply is read by code alone, or when any pinned answer moves.
Read only: no model, network, process or file access.
"""

import argparse
from pathlib import Path
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.skills import openreq  # noqa: E402

NAME = "npp_short_answer_cheap"

CASES = [
    ("shelf", "pantry"),
    ("shelf", "the pantry shelf"),
    ("shelf", "pantry and call it Honey Pot"),
    ("shelf", "pantry, also rename it"),
    ("availability", "sold out"),
    ("availability", "limited"),
    ("clock", "9am"),
    ("clock", "9am then 5pm too"),
    ("shelf", "one two three four five six seven eight nine ten eleven twelve pantry"),
    ("day", "tomorrow"),
    ("product_ref", "the honey"),
    ("name", "Honey"),
    ("shelf", ""),
    ("shelf", 7),
]

# Cases whose reply is long, says more than the answer, or needs context the
# check does not give: the model must read them, so code alone must not.
MUST_MODEL = (2, 3, 7, 8, 9, 10, 11, 12, 13)

EXPECTED = [
    "case 0 cheap=(True, 'pantry')",
    "case 1 cheap=(True, 'pantry')",
    "case 2 cheap=(False, None)",
    "case 3 cheap=(False, None)",
    "case 4 cheap=(True, 'no')",
    "case 5 cheap=(True, 'limited')",
    "case 6 cheap=(True, '09:00')",
    "case 7 cheap=(False, None)",
    "case 8 cheap=(False, None)",
    "case 9 cheap=(False, None)",
    "case 10 cheap=(False, None)",
    "case 11 cheap=(False, None)",
    "case 12 cheap=(False, None)",
    "case 13 cheap=(False, None)",
]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    failed = False
    for index, (kind, text) in enumerate(CASES):
        try:
            got = openreq.cheap_answer(types.SimpleNamespace(kind=kind), text)
        except Exception:
            print("FAIL check-error")
            print(f"FAIL {NAME}")
            return 1
        line = f"case {index} cheap={got!r}"
        print(line)
        if index in MUST_MODEL and got[0] is True:
            print(f"FAIL long-answer-read {index}")
            failed = True
        if line != EXPECTED[index]:
            print(f"FAIL cheap-changed {index}")
            failed = True
    print(f"FAIL {NAME}" if failed else f"PASS {NAME}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
