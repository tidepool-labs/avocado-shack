#!/usr/bin/env python3
"""Check pinned S2 photo-read examples against the offline normalizer."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import npp
from hass.npp import identify


NAME = "npp_identify_example_check"


def _report_example(number, raw, normalized):
    changed = sorted(key for key in raw if raw[key] != normalized[key])
    print(f"example {number} changed={','.join(changed) or 'none'}")
    failed = False
    for key in changed:
        before, after = raw[key], normalized[key]
        if key == "confidence":
            for score in sorted(before.keys() | after.keys()):
                if (score not in before or score not in after
                        or before[score] != after[score]):
                    print(f"FAIL example-confidence {number} {score}")
                    failed = True
        elif (key == "item" and isinstance(before, str) and isinstance(after, str)
              and before.casefold() == after.casefold()):
            print(f"retitle {number}")
        else:
            print(f"FAIL example-rewritten {number} {key}")
            failed = True
    return failed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    if args:
        parser.error(f"unrecognized arguments: {' '.join(args)}")

    try:
        files = npp.assets()[1]
        examples = json.loads(files['hass-product-identify/examples.json'])['examples']
        schema = json.loads(files['hass-product-identify/identify.schema.json'])
        if not isinstance(examples, list):
            raise ValueError("expected an examples list")
    except Exception:
        print("FAIL assets-unreadable")
        print(f"FAIL {NAME}")
        return 1

    failed = False
    for index, example in enumerate(examples, 1):
        number = f"{index:02d}"
        try:
            raw = example["output"]
            normalized = identify._normalize(raw, schema)
        except Exception:
            print(f"FAIL check-error {number}")
            failed = True
            continue
        if _report_example(number, raw, normalized):
            failed = True

    print(f"{'FAIL' if failed else 'PASS'} {NAME}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
