#!/usr/bin/env python3
"""Report existing-maker text excluded by the NPP card's panel claim rule."""

import argparse
import json
from pathlib import Path
import stat
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass.npp import validate


MAKERS = ROOT / "hass/content/makers.json"
MAKERS_CAP = 2_000_000
FIELDS = ("name", "place", "story")
REPORT = "npp_maker_panel_report"


class InputError(ValueError):
    """A fixed diagnostic that contains no input data."""


def _reject_constant(_value):
    raise ValueError("invalid JSON constant")


def _read_makers():
    try:
        info = MAKERS.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise InputError("input-unsafe makers")
        if info.st_size > MAKERS_CAP:
            raise InputError("input-too-large makers")
        with MAKERS.open("rb") as source:
            raw = source.read(MAKERS_CAP + 1)
        if len(raw) > MAKERS_CAP:
            raise InputError("input-too-large makers")
        doc = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except InputError:
        raise
    except (OSError, ValueError, RecursionError):
        raise InputError("input-unreadable makers") from None

    makers = doc.get("makers") if isinstance(doc, dict) else None
    if not isinstance(makers, dict) or any(
        not isinstance(row, dict)
        or any(not isinstance(row.get(field), str) for field in ("name", "place"))
        or any(not isinstance(row.get(field, ""), str) for field in ("story", "url"))
        for row in makers.values()
    ):
        raise InputError("input-unreadable makers")
    return makers


def _audit(makers):
    counts = dict.fromkeys((*FIELDS, "origin"), 0)
    findings = []

    def clean(value):
        try:
            return validate._panel_clean(value)
        except Exception:
            if "check-error" not in findings:
                findings.append("check-error")
            return None

    for number, row in enumerate(makers.values(), 1):
        place_clean = None
        for field in FIELDS:
            value = row.get(field)
            if not value:
                continue
            result = clean(value)
            if field == "place":
                place_clean = result
            if result is False:
                counts[field] += 1
                findings.append(f"panel-unshown {number} {field}")
        # As in listing(), a clean derived line cannot rescue an unclean place.
        if place_clean is False or (place_clean and clean("Based in " + row["place"]) is False):
            counts["origin"] += 1
            findings.append(f"origin-unshown {number}")
    return counts, findings


def main(argv=None):
    parser = argparse.ArgumentParser(prog=REPORT, description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    if args:
        parser.error("no arguments accepted")

    try:
        makers = _read_makers()
    except InputError as error:
        findings = [str(error)]
    else:
        counts, findings = _audit(makers)
        print(f"makers {len(makers)}")
        for field, count in counts.items():
            print(f"unshown-{field} {count}")

    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} {REPORT}")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
