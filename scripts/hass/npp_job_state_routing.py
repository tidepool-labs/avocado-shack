#!/usr/bin/env python3
"""Check that the NPP turn router uses only active, unambiguous job states."""

import argparse
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass.npp import job, reply


NAME = "npp_job_state_routing"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    raw_active = job.ACTIVE
    if not isinstance(raw_active, str) or not re.fullmatch(r"'[a-z_]+'(?:,'[a-z_]+')*", raw_active):
        print("FAIL active-unreadable")
        print(f"FAIL {NAME}")
        return 1

    active = re.findall(r"'([a-z_]+)'", raw_active)
    question, edit = reply.QUESTION_STATES, reply.EDIT_STATES
    print(f"states active={len(active)} question={len(question)} edit={len(edit)}")

    failed = False
    for state in (*question, *edit):
        if state not in active:
            print(f"FAIL routed-inactive {state}")
            failed = True
    for state in question:
        if state in edit:
            print(f"FAIL state-overlap {state}")
            failed = True
    for state in active:
        if state not in question and state not in edit:
            print(f"unrouted {state}")

    print(f"{'FAIL' if failed else 'PASS'} {NAME}")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
