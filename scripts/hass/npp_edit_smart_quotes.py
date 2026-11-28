#!/usr/bin/env python3
"""Compare S10 edit fields for iPhone smart punctuation and straight marks offline."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp
from hass.npp import edits


PAIRS = (
    ("made by joe’s farm", "made by joe's farm"),
    ("call it grandma’s jam", "call it grandma's jam"),
    ("made by miners, o’brien", "made by miners, o'brien"),
    ("This is from ‘miners’.", "This is from 'miners'."),
    ("This is from “miners”.", 'This is from "miners".'),
    ("call it “Wildflower Honey”", 'call it "Wildflower Honey"'),
)


def check():
    try:
        grammar = edits.Grammar(hass.npp.assets()[1])
    except Exception:
        print("FAIL check-error")
        return False

    passed = True
    for index, (curly_text, straight_text) in enumerate(PAIRS):
        results = []
        for text in (straight_text, curly_text):
            try:
                edit = edits.read(grammar, text, {})
            except Exception:
                print("FAIL check-error")
                passed = False
            else:
                fields = tuple(field for field, _ in edit.patch)
                results.append((fields, ",".join(fields) or edit.ask or edit.reply))
        if len(results) != 2:
            continue  # An unreadable check already has a finding.
        (straight_fields, straight), (curly_fields, curly) = results
        print(f"case {index} straight={straight} curly={curly}")
        if straight_fields and straight_fields != curly_fields:
            print(f"FAIL curly-not-read {index}")
            passed = False
    return passed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    options = sys.argv[1:] if argv is None else argv
    if options:  # Reject even a bare '--', which argparse otherwise consumes.
        parser.error("unrecognized arguments")
    passed = check()
    print(f"{'PASS' if passed else 'FAIL'} npp_edit_smart_quotes")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
