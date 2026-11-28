#!/usr/bin/env python3
"""Check the S10 edit mapper's validator against the pinned schema offline."""

import argparse
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp
from hass.npp import edits


def patch(value, field="name", **extra):
    return {"field": field, "value": value, **extra}


def mapping(action, patches, ask_id=None, **extra):
    return {"action": action, "patches": patches, "ask_id": ask_id, **extra}


CASES = (
    mapping("patch", [patch("Fig Jam")]),
    mapping("ask", [], "ask_edit_unclear"),
    mapping("ask", []),
    mapping("patch", [patch("Fig Jam")], "ask_price"),
    mapping("ask", [patch("Fig Jam")], "ask_edit_unclear"),
    mapping("patch", [patch("A") for _ in range(5)]),
    mapping("patch", [patch("A") for _ in range(4)]),
    mapping("patch", [patch("a" * 81)]),
    mapping("patch", [patch("a" * 80)]),
    mapping("patch", [patch("x", field="photo")]),
    mapping("patch", [], extra=1),
    {"action": "patch", "patches": []},
    mapping("patch", [patch(5)]),
    mapping("patch", []),
    mapping("delete", []),
    [],
    mapping("patch", [patch("A", x=1)]),
)
EXPECTED = frozenset({0, 1, 6, 8, 13})  # Accepted case indices.
EXPECTED_PINS = (4, 80, 9, 6)


def check():
    schema = edits.Grammar(hass.npp.assets()[1]).schema
    passed = True
    for i, doc in enumerate(CASES):
        candidate = copy.deepcopy(doc)
        try:
            accepted = edits.valid_mapping(candidate, schema) is not None
        except Exception:
            # There was no verdict; report the indexed finding and keep checking.
            print(f"FAIL verdict {i}")
            passed = False
            continue
        print(f"case {i} {'accepted' if accepted else 'refused'}")
        if accepted != (i in EXPECTED):
            print(f"FAIL verdict {i}")
            passed = False

    props = schema["properties"]
    patches = props["patches"]
    item = patches["items"]["properties"]
    pins = (patches["maxItems"], item["value"]["maxLength"],
            len(item["field"]["enum"]), len(props["ask_id"]["enum"]))
    print("pins maxItems={} maxLength={} fields={} ask_ids={}".format(*pins))
    if pins != EXPECTED_PINS:
        print("FAIL schema-drift")
        passed = False
    return passed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)
    try:
        passed = check()
    except Exception:
        print("FAIL check-error")
        passed = False
    print(f"{'PASS' if passed else 'FAIL'} npp_edit_mapping_schema")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
