#!/usr/bin/env python3
"""Check offline that NPP model pins fit receipt evidence and the judge rubric."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.npp import evidence


def findings():
    try:
        pins, files, _ = npp.assets()
    except Exception:
        # Loader failures must not disclose source paths, asset data or digests.
        yield "assets-unreadable"
        return

    steps = pins.get("steps")
    if not isinstance(steps, dict) or not all(isinstance(pin, dict) for pin in steps.values()):
        yield "assets-unreadable"
        return

    for name, pin in steps.items():
        try:
            evidence.Evidence().model(name, pin.get("model"), None)
        except (ValueError, TypeError):
            print(f"step {name} recordable=no")
            yield f"step-unrecordable {name}"
        else:
            print(f"step {name} recordable=yes")

    if "judge" not in steps:
        yield "judge-missing"
        return
    try:
        rubric_judge = json.loads(files["hass-style-judge/rubric.json"])["judge"]
    except (KeyError, ValueError, TypeError, RecursionError):
        yield "assets-unreadable"
        return
    if not isinstance(rubric_judge, dict):
        yield "assets-unreadable"
        return
    for field in ("model", "effort"):
        if (field not in rubric_judge or field not in steps["judge"]
                or rubric_judge[field] != steps["judge"][field]):
            yield f"judge-drift {field}"


def main(argv=None):
    # Even --help is an argument; the only supported invocation has none.
    parser = argparse.ArgumentParser(add_help=False)
    parser.parse_args(argv)

    failed = False
    for reason in findings():
        print(f"FAIL {reason}")
        failed = True
    print("FAIL npp_model_pin_agreement" if failed else "PASS npp_model_pin_agreement")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
