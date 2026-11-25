#!/usr/bin/env python3
"""Check the model's fact reply yields only the twelve fact keys, each a plain non-empty string or nothing."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import newitem

KEYS = ("name", "maker", "place", "story", "kind", "shelf", "container", "size", "price",
        "availability", "use", "url")

# A raw reply string, None, or ('deep', n) for the string '[' * n. All made-up fixtures.
CASES = [
    '{"name": "Wildflower Honey", "maker": "Cedar Row Apiary"}',
    '{"name": "   ", "price": 7}',
    "[1, 2]",
    "not json",
    '{"name": "Honey", "secret": "x", "approved": "yes"}',
    '{"url": "https://cedarrow.example", "story": "  They keep bees.  "}',
    '{"name": ["Honey"], "size": {"oz": 12}}',
    ("deep", 100000),
    None,
    '{"name": "Honey", "name": "Organic Honey"}',
    '{"availability": true, "shelf": null}',
]

# Measured at c8cdcc95. Case 9 pins that a repeated key keeps the LAST value.
EXPECTED = [
    "case 0 facts={'name': 'Wildflower Honey', 'maker': 'Cedar Row Apiary'}",
    "case 1 facts={}",
    "case 2 facts={}",
    "case 3 facts={}",
    "case 4 facts={'name': 'Honey'}",
    "case 5 facts={'story': 'They keep bees.', 'url': 'https://cedarrow.example'}",
    "case 6 facts={}",
    "case 7 facts={}",
    "case 8 facts={}",
    "case 9 facts={'name': 'Organic Honey'}",
    "case 10 facts={}",
]

TRAILER = "npp_fact_reply_keys"


def raw_reply(case):
    return "[" * case[1] if isinstance(case, tuple) else case


def non_fact_read(got):
    """True when a key outside KEYS carries a value, or a value is not a plain non-empty string."""
    for key, value in got.items():
        if value is None:
            continue
        if key not in KEYS:
            return True
        if not isinstance(value, str) or not value or value != value.strip():
            return True
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(prog="npp_fact_reply_keys.py", description=__doc__,
                                     allow_abbrev=False)
    parser.parse_args(argv)

    findings = 0
    for index, case in enumerate(CASES):
        try:
            got = newitem.parse_facts(raw_reply(case))
            kept = {k: v for k, v in got.items() if v is not None}
            line = f"case {index} facts={kept!r}"
            unread = non_fact_read(got)
        except Exception:
            print("FAIL check-error")
            findings += 1
            break
        print(line)
        if unread:
            print(f"FAIL non-fact-read {index}")
            findings += 1
        if line != EXPECTED[index]:
            print(f"FAIL facts-changed {index}")
            findings += 1

    if findings:
        print(f"FAIL {TRAILER}")
        return 1
    print(f"PASS {TRAILER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
