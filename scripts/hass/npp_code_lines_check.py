#!/usr/bin/env python3
"""Check the owner-facing lines defined in NPP code, offline."""

import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hass import npp, voice
from hass.npp import job, missing, picture


def main(argv=None):
    # The command has no options, including an automatic help flag.
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)

    raw, house = picture._NOTES["raw"], picture._NOTES["house"]
    duplicate = missing.DUPLICATE
    lines = (("expired", job.EXPIRED), ("duplicate", duplicate),
             ("note-raw", raw), ("note-house", house))
    for name, text in lines:
        sentences = len(re.findall(r"[.!?](?:\s|$)", text))
        print(f"line {name} chars={len(text)} sentences={sentences}")

    findings = []
    for name, text in lines:
        if voice.check(text):
            findings.append(f"voice {name}")
        if re.search(r"\d", text):
            findings.append(f"digit {name}")

    try:
        templates = npp.assets()[2]
        cap = templates["caps"]["question_max_chars"]
        parts = templates["brackets"]["parts"]
        own_photo, house_style = parts["picture_own_photo"], parts["picture_house"]
        if type(cap) is not int or not all(isinstance(part, str) for part in (own_photo, house_style)):
            raise ValueError("unusable reply templates")
    except Exception:
        # Do not echo asset errors: only the stable finding belongs in the report.
        findings.append("assets-unreadable")
    else:
        if len(duplicate) > cap:
            findings.append("too-long duplicate")
        if raw != own_photo:
            findings.append("note-drift raw")
        if house != house_style:
            findings.append("note-drift house")

    for finding in findings:
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} npp_code_lines_check")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
