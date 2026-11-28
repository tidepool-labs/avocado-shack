#!/usr/bin/env python3
"""Compare the two S10 supplier readings on unsure words, offline."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.npp import edits


WORDS = (
    "or", "maybe", "probably", "think", "guess", "not", "either",
    "please", "change", "add", "remove", "replace", "instead",
)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    try:
        grammar = edits.Grammar(npp.assets()[1])
    except Exception:  # Unusable assets must not leak an exception's details.
        print("FAIL assets-unreadable")
        print("FAIL supplier_hedge_parity")
        return 1

    failed = False
    for word in WORDS:
        name = f"Etto {word} Farm"
        text = "from " + name
        match = grammar.match(text)
        if match is None or match[0] != "supplier":
            print(f"FAIL supplier-form-missing {word}")
            failed = True
            continue

        asks = edits.read(grammar, text, {}).ask is not None
        keeps = grammar.supplier("This is from " + name) is not None
        form = "ask" if asks else "patch"
        sentence = "keep" if keeps else "drop"
        print(f"hedge {word} form={form} sentence={sentence}")
        if asks == keeps:
            print(f"FAIL hedge-disagree {word}")
            failed = True

    print("FAIL supplier_hedge_parity" if failed else "PASS supplier_hedge_parity")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
