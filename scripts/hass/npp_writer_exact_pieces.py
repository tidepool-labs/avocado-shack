#!/usr/bin/env python3
"""Check the Hass writer's accepted pieces against offline fixtures."""

import argparse
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import newitem


FIRST = "Wildflower honey from Cedar Row Apiary."
POOL = ["Spoon it onto warm toast.", "Stir a little into tea."]
CASES = [
    (FIRST, None),
    (FIRST + " Spoon it onto warm toast.", None),
    ("wildflower  honey from cedar row apiary.  stir a little into tea.", None),
    (FIRST + " Try it on biscuits.", "on biscuits"),
    (FIRST + " Try it on biscuits.", None),
    ("Raw wildflower honey from Cedar Row Apiary.", None),
    ("Spoon it onto warm toast.", None),
    (FIRST + " Spoon it onto warm toast; it cures colds.", None),
    (FIRST + " Taste a little first, then decide how to use the rest.", None),
    ("", None),
]
MUST_REFUSE = (4, 5, 6, 7, 9)
EXPECTED = (
    "case 0 unproven=[]",
    "case 1 unproven=[]",
    "case 2 unproven=['wildflower honey from cedar row apiary.']",
    "case 3 unproven=[]",
    "case 4 unproven=['Try it on biscuits.']",
    "case 5 unproven=['Raw wildflower honey from Cedar Row']",
    "case 6 unproven=['Spoon it onto warm toast.']",
    "case 7 unproven=['Spoon it onto warm toast; it']",
    "case 8 unproven=[]",
    "case 9 unproven=['empty']",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else list(argv)
    # A bare option terminator is still an argument to this no-argument tool.
    if args == ["--"]:
        parser.error("unrecognized arguments: --")
    parser.parse_args(args)

    failed = False
    for i, (text, use) in enumerate(CASES):
        try:
            got = newitem.writer_unproven(text, FIRST, POOL, use)
        except Exception:
            print("FAIL check-error")
            failed = True
            break

        line = f"case {i} unproven={got!r}"
        print(line)
        if i in MUST_REFUSE and not got:
            print(f"FAIL unproven-sentence-passed {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL pieces-changed {i}")
            failed = True

    print("FAIL npp_writer_exact_pieces" if failed else "PASS npp_writer_exact_pieces")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
