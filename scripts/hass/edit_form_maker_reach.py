#!/usr/bin/env python3
"""Count catalog makers that the pinned NPP edit forms cannot name."""

import argparse
import json
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hass import content_model, live_policy, npp

MAKERS = ROOT / "hass/content/makers.json"
MAKERS_CAP = 2_000_000
GRAMMAR = "hass-listing-edit/edit-grammar.json"
FORM_IDS = ("supplier", "maker")


def _valid_row(row):
    return (isinstance(row, dict)
            and all(isinstance(row.get(k), str) for k in ("name", "place"))
            and all(isinstance(row[k], str) for k in ("story", "url") if k in row))


def _read_makers():
    # lstat distinguishes a symlink (even a dangling one) from a missing file.
    try:
        info = MAKERS.lstat()
        if not stat.S_ISREG(info.st_mode):
            return {}, "input-unsafe makers"
        if info.st_size > MAKERS_CAP:
            return {}, "input-too-large makers"
        with MAKERS.open("rb") as source:
            raw = source.read(MAKERS_CAP + 1)
        if len(raw) > MAKERS_CAP:
            return {}, "input-too-large makers"
        document = json.loads(raw.decode("utf-8"))
        makers = document.get("makers") if isinstance(document, dict) else None
        if isinstance(makers, dict) and all(_valid_row(row) for row in makers.values()):
            return makers, None
    except (OSError, ValueError, RecursionError):
        pass
    return {}, "input-unreadable makers"


def _patterns():
    forms = json.loads(npp.assets()[1][GRAMMAR])["forms"]
    if not isinstance(forms, list):
        raise ValueError("forms must be a list")
    return {form["id"]: re.compile(form["pattern"], re.I)
            for form in forms if form["id"] in FORM_IDS}


def _reaches(pattern, text, **expected):
    match = pattern.fullmatch(text)
    if match is None:
        return False
    captures = match.groupdict()
    return all(captures.get(key) == value for key, value in expected.items())


def _findings(makers):
    try:
        patterns = _patterns()
    except Exception:
        yield "assets-unreadable"
        return

    for form in FORM_IDS:
        if form not in patterns:
            yield f"form-missing {form}"

    misses = dict.fromkeys(("supplier", "maker", "maker-town"), 0)
    try:
        for row in makers.values():
            name, town = row["name"], live_policy._town(row["place"])
            if "supplier" in patterns:
                misses["supplier"] += not _reaches(patterns["supplier"], f"from {name}", value=name)
            if "maker" in patterns:
                pattern = patterns["maker"]
                misses["maker"] += not _reaches(pattern, f"made by {name}", value=name)
                misses["maker-town"] += not _reaches(pattern, f"made by {name}, {town}", value=name, town=town)
    except Exception:
        yield "check-error"
        return

    for form, count in misses.items():
        if count:
            yield f"form-miss {form} {count}"

    try:
        invalid = sum(not content_model.valid_supplier(row["name"]) for row in makers.values())
    except Exception:
        yield "check-error"
    else:
        if invalid:
            yield f"supplier-invalid {invalid}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    argv = sys.argv[1:] if argv is None else argv
    parser.parse_args(argv)
    if argv:  # argparse otherwise accepts a bare end-of-options marker.
        parser.error("no arguments are accepted")
    makers, error = _read_makers()
    if error:
        findings = [error]
    else:
        print(f"makers {len(makers)}")
        findings = list(_findings(makers))
    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} edit_form_maker_reach")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
