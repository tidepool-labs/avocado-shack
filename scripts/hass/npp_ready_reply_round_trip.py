#!/usr/bin/env python3
"""Check that the pinned NPP ready prompt instructs a reply the job accepts."""

import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp  # noqa: E402
from hass.npp import job, reply  # noqa: E402


CODES = ("4ed1", "a1b2c3", "abcdef123456")
VERSIONS = (1, 2, 9, 123456789)
TRAILER = "npp_ready_reply_round_trip"


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    try:
        replies = npp.assets()[2]
    except Exception:
        print("FAIL assets-unreadable")
        print(f"FAIL {TRAILER}")
        return 1

    failed = False
    try:
        for c, code in enumerate(CODES, 1):
            for version in VERSIONS:
                prompt = reply.ready_line(replies, code, version)
                instructed = re.search(r"\byes [0-9a-f]+-[0-9]+", prompt)
                if instructed is None:
                    print(f"FAIL reply-missing {c} {version}")
                    failed = True
                    continue
                match = job.YES.fullmatch(instructed[0])
                if match is None or match.groups() != (code, str(version)):
                    print(f"FAIL reply-refused {c} {version}")
                    failed = True
    except Exception:
        print("FAIL check-error")
        print(f"FAIL {TRAILER}")
        return 1

    print(f"prompts {len(CODES) * len(VERSIONS)}")
    print(f"{'FAIL' if failed else 'PASS'} {TRAILER}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
