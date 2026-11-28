#!/usr/bin/env python3
"""Check three live-policy detectors against fixed, offline NPP copy fixtures."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import live_policy


CASES = [
    "call eight oh five five five five one two",
    "call 805 five five five one two",
    "two jars and one loaf",
    "the freshest honey in town",
    "best served warm",
    "the honest harvest loaf",
    "the tastiest jam",
    "\u043erganic honey",  # Cyrillic о followed by Latin letters.
    "plain wildflower honey",
    "world famous salsa",
]
MUST_FLAG = (0, 1, 3, 6, 7, 9)
EXPECTED = (
    "case 0 spelled=yes superlative=no mixed=no",
    "case 1 spelled=yes superlative=no mixed=no",
    "case 2 spelled=no superlative=no mixed=no",
    "case 3 spelled=no superlative=yes mixed=no",
    "case 4 spelled=no superlative=no mixed=no",
    "case 5 spelled=no superlative=no mixed=no",
    "case 6 spelled=no superlative=yes mixed=no",
    "case 7 spelled=no superlative=no mixed=yes",
    "case 8 spelled=no superlative=no mixed=no",
    "case 9 spelled=no superlative=yes mixed=no",
)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    for i, sentence in enumerate(CASES):
        try:
            spelled = live_policy._spelled_number(sentence)
            superlative = live_policy._superlative(sentence)
            mixed = live_policy._mixed_script(sentence)
        except Exception:
            print("FAIL check-error")
            failed = True
            break

        line = (f"case {i} spelled={'yes' if spelled else 'no'} "
                f"superlative={'yes' if superlative else 'no'} mixed={'yes' if mixed else 'no'}")
        print(line)
        if i in MUST_FLAG and not (spelled or superlative or mixed):
            print(f"FAIL disguise-passed {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL detector-changed {i}")
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_claim_disguise_words")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
