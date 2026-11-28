#!/usr/bin/env python3
"""Report which sample edit wordings reach S10 without running a model."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.npp import edits
from hass.npp.reply import Stages


PHRASES = (
    "call it Wildflower honey",
    "change the name to Wildflower honey",
    "rename it Wildflower honey",
    "from Etto",
    "the supplier is Etto",
    "made by Etto",
    "put it in pantry",
    "move it to pantry",
    "change the category to pantry",
    "shelf: pantry",
    "use a different photo",
    "new photo",
    "reword the description",
    "make the description shorter",
)


def main(argv=None):
    argparse.ArgumentParser(add_help=False, description=__doc__).parse_args(argv)
    try:
        pinned = npp.assets()
    except Exception:
        # Report the failure class only, without asset paths or exception text.
        print("FAIL assets-unreadable")
        print("FAIL npp_edit_wording_reach")
        return 1

    port = Stages(pinned, start=None, render=None)
    grammar = edits.Grammar(pinned[1])
    missed = False
    for index, wording in enumerate(PHRASES, 1):
        if port.takes_turn(wording, "card_out"):
            edit = edits.read(grammar, wording, {})
            reading = "model" if edit.ask == "ask_edit_unclear" else "form"
            print(f"edit {index:02d} routed=yes reading={reading}")
        else:
            print(f"edit {index:02d} routed=no reading=missed")
            print(f"FAIL edit-missed {index:02d}")
            missed = True

    print(f"{'FAIL' if missed else 'PASS'} npp_edit_wording_reach")
    return int(missed)


if __name__ == "__main__":
    sys.exit(main())
