#!/usr/bin/env python3
"""Check the private intake reads commerce numbers and free-text notes only when strictly well formed.

Offline and read-only: it calls only `item_intake.commerce_answers` and `item_intake._text_value`
on fixed made-up inputs and compares each answer with the pinned one.
"""

import argparse
import os
import sys

sys.dont_write_bytecode = True  # a plain run (no -B) must leave no __pycache__ inside the repository

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from hass.skills import item_intake  # noqa: E402


NAME = "npp_intake_commerce_text"

CASES = [
    ("commerce", None, {"price_cents": 799, "cost_cents": 450, "quantity": 12}),
    ("commerce", None, {"price_cents": 799, "cost_cents": None, "quantity": None}),
    ("commerce", None, {"price_cents": 7.99, "cost_cents": None, "quantity": None}),
    ("commerce", None, {"price_cents": True, "cost_cents": None, "quantity": None}),
    ("commerce", None, {"price_cents": 799, "cost_cents": None, "quantity": 100001}),
    ("commerce", None, {"price_cents": 799, "cost_cents": None, "quantity": None, "approved": True}),
    ("commerce", None, {"price_cents": -1, "cost_cents": None, "quantity": None}),
    ("commerce", None, ["price_cents", 799]),
    ("text", "ingredients", "honey"),
    ("text", "claims", "none"),
    ("text", "variety", "none"),
    ("text", "ingredients", "honey\u200b and wax"),
    ("text", "ingredients", "x" * 401),
    ("text", "origin", "<script>"),
]

# Cases the intake must refuse: no commerce fact, no text answer.
MUST_REFUSE = (2, 3, 4, 5, 6, 7, 11, 12, 13)

_CHARACTERS = "I can't use one of the characters in that. Could you say it again in plain words?"
EXPECTED = [
    "case 0 commerce={'price': '7.99', 'cost': '4.50', 'qty': 12, 'qty_unit': 'each'}",
    "case 1 commerce={'price': '7.99'}",
    "case 2 commerce={}",
    "case 3 commerce={}",
    "case 4 commerce={}",
    "case 5 commerce={}",
    "case 6 commerce={}",
    "case 7 commerce={}",
    "case 8 text=('honey', None)",
    "case 9 text=('none', None)",
    "case 10 text=('', None)",
    f"case 11 text=(None, \"{_CHARACTERS}\")",
    "case 12 text=(None, 'That is a bit long for my notes. Could you shorten it?')",
    f"case 13 text=(None, \"{_CHARACTERS}\")",
]


def check():
    """Return the stdout lines for one run and whether a finding was printed."""
    lines = []
    failed = False
    for index, (kind, key, value) in enumerate(CASES):
        try:
            if kind == "commerce":
                got = item_intake.commerce_answers(value)
                unsafe = bool(got)
            else:
                got = item_intake._text_value(key, value)
                unsafe = got[0] is not None
        except Exception:
            lines.append("FAIL check-error")
            return lines, True
        line = f"case {index} {kind}={got!r}"
        lines.append(line)
        if index in MUST_REFUSE and unsafe:
            lines.append(f"FAIL unsafe-answer-read {index}")
            failed = True
        if line != EXPECTED[index]:
            lines.append(f"FAIL intake-changed {index}")
            failed = True
    return lines, failed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    lines, failed = check()
    lines.append(f"{'FAIL' if failed else 'PASS'} {NAME}")
    for line in lines:
        print(line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
