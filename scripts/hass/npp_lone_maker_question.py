#!/usr/bin/env python3
"""Check a maker never goes live without a new product, and the unsaid-value question names at most two values.

Offline and read-only: calls only the pure `live_policy._lone_makers` and
`live_policy.unsaid_question` on fixed fixtures and compares each answer with
the pinned line. Run as `python3 -B scripts/hass/npp_lone_maker_question.py`.
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import live_policy  # noqa: E402

NAME = "npp_lone_maker_question"

CASES = [
    ('ops', [{'op': 'product.add', 'args': {'name': 'Plum Jam', 'producerKey': 'cedar-row'}},
             {'op': 'maker.add', 'args': {'key': 'cedar-row', 'name': 'Cedar Row Apiary'}}]),
    ('ops', [{'op': 'maker.add', 'args': {'key': 'cedar-row', 'name': 'Cedar Row Apiary'}}]),
    ('ops', [{'op': 'product.add', 'args': {'name': 'Fig Jam', 'producerKey': 'harbor'}},
             {'op': 'maker.add', 'args': {'key': 'cedar-row', 'name': 'Cedar Row Apiary'}}]),
    ('ops', [{'op': 'maker.add', 'args': {'key': 'a'}}, {'op': 'maker.add', 'args': {'key': 'b'}}]),
    ('ops', [{'op': 'maker.add', 'args': 'cedar-row'}]),
    ('ops', [{'op': 'product.add', 'args': {'name': 'Plum Jam', 'producerKey': 'cedar-row'}}]),
    ('ops', []),
    ('values', ['Cedar Row Apiary']),
    ('values', ['Cedar Row Apiary', 'Fillmore', 'Ojai']),
    ('values', ['Cedar Row Apiary', 'Fillmore']),
]

# Cases whose draft puts a maker live on its own: the policy must refuse each.
MUST_REFUSE = (1, 2, 3, 4)

_LONE = "['not live: maker.add without a new product']"
_TAIL = (" in your message, and a brand, a maker or a town only goes on the website in your own words. "
         "Send the change again with it in your own words, or without it.'")
EXPECTED = [
    "case 0 lone=[]",
    "case 1 lone=" + _LONE,
    "case 2 lone=" + _LONE,
    "case 3 lone=" + _LONE,
    "case 4 lone=" + _LONE,
    "case 5 lone=[]",
    "case 6 lone=[]",
    "case 7 question='You didn\\'t say \\ue000\"Cedar Row Apiary\"\\ue001" + _TAIL,
    "case 8 question='You didn\\'t say \\ue000\"Cedar Row Apiary\"\\ue001 and \\ue000\"Fillmore\"\\ue001"
    " (and a few more)" + _TAIL,
    "case 9 question='You didn\\'t say \\ue000\"Cedar Row Apiary\"\\ue001 and \\ue000\"Fillmore\"\\ue001" + _TAIL,
]


def fail(reason):
    print(f"FAIL {reason}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    findings = 0
    for index, (kind, value) in enumerate(CASES):
        try:
            if kind == "ops":
                got = live_policy._lone_makers(value)
                line = f"case {index} lone={got!r}"
            else:
                got = live_policy.unsaid_question(value)
                line = f"case {index} question={got!r}"
        except Exception:
            fail("check-error")
            findings += 1
            break
        print(line)
        if kind == "ops" and index in MUST_REFUSE and not got:
            fail(f"lone-maker-allowed {index}")
            findings += 1
        if line != EXPECTED[index]:
            fail(f"lone-changed {index}")
            findings += 1
    if findings:
        print(f"FAIL {NAME}")
        return 1
    print(f"PASS {NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
