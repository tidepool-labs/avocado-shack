#!/usr/bin/env python3
"""Check undo draft classification and change IDs on offline fixtures."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import live_policy


CASES = [
    {"ops": [{"op": "history.revert", "args": {"changeId": "chg-1"}}]},
    {"ops": [
        {"op": "history.revert", "args": {"changeId": "chg-1"}},
        {"op": "history.revert", "args": {"changeId": "chg-2"}},
    ]},
    {"ops": [
        {"op": "history.revert", "args": {"changeId": "chg-1"}},
        {"op": "product.edit", "args": {"id": "p-1"}},
    ]},
    {"ops": []},
    {"ops": [{"op": "history.revert"}]},
    {"ops": [{"op": "history.revert", "args": "chg-1"}]},
    {"ops": "history.revert"},
    {"ops": [{"op": "History.Revert", "args": {"changeId": "chg-1"}}]},
    {},
    ["history.revert"],
]
MUST_REFUSE = (2, 3, 6, 7, 8, 9)
EXPECTED = (
    "case 0 undo=yes undone=['chg-1']",
    "case 1 undo=yes undone=['chg-1', 'chg-2']",
    "case 2 undo=no undone=[]",
    "case 3 undo=no undone=[]",
    "case 4 undo=yes undone=[None]",
    "case 5 undo=yes undone=[None]",
    "case 6 undo=no undone=[]",
    "case 7 undo=no undone=[]",
    "case 8 undo=no undone=[]",
    "case 9 undo=no undone=[]",
)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)

    failed = False
    for i, draft in enumerate(CASES):
        try:
            undo = live_policy.is_undo(draft)
            ids = live_policy.undone(draft) if isinstance(draft, dict) else []
        except Exception:
            print("FAIL check-error")
            failed = True
            break

        line = f"case {i} undo={'yes' if undo else 'no'} undone={ids!r}"
        print(line)
        if undo and i in MUST_REFUSE:
            print(f"FAIL mixed-as-undo {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL undo-changed {i}")
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} npp_undo_draft_shape")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
