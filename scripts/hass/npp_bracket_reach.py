#!/usr/bin/env python3
"""Report whether each ready-prompt bracket part fits on its own."""

import argparse
import json
from pathlib import Path
from string import Formatter
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.npp import reply

IDENTIFY_SCHEMA = "hass-product-identify/identify.schema.json"
SOURCES: dict[tuple[str, str], tuple[str, ...] | int] = {
    ("maker_left_off_label", "brand"): ("properties", "brand_on_label", "maxLength"),
    ("claim_left_off", "claim"): ("properties", "visible_claims", "items", "maxLength"),
}


def source_max(schema, source):
    # Integer entries are direct limits; paths read the current checked schema.
    if isinstance(source, tuple):
        for component in source:
            schema = schema[component]
        source = schema
    if type(source) is not int or source < 0:
        raise ValueError("invalid maxLength")
    return source


def report(schema, replies, parts):
    lines = []
    failed = False
    for key, text in parts.items():
        fields = {field for _, field, _, _ in Formatter().parse(text) if field is not None}
        if not fields:
            lines.append(f"part {key} fixed chars={len(text)}")
            reason = None if reply.compose(replies, {key: {}}) else "part-too-long"
        else:
            field = next(iter(fields))
            source = SOURCES.get((key, field)) if len(fields) == 1 else None
            if source is None:
                reason = "part-unmapped"
            else:
                maximum = source_max(schema, source)
                shown = next((n for n in range(200, 0, -1)
                              if reply.compose(replies, {key: {field: 'x' * n}})), 0)
                lines.append(f"part {key} shown-max={shown} source-max={maximum}")
                reason = "part-unreachable" if shown < maximum else None
        if reason is not None:
            lines.append(f"FAIL {reason} {key}")
            failed = True
    return failed, lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)
    try:
        _, files, replies = npp.assets()
    except Exception:
        # The asset reader's exception text is not part of this report.
        failed, lines = True, ["FAIL assets-unreadable"]
    else:
        try:
            schema = json.loads(files[IDENTIFY_SCHEMA])
            parts = replies["brackets"]["parts"]
            if not isinstance(parts, dict):
                raise ValueError("expected bracket parts object")
            failed, lines = report(schema, replies, parts)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, RecursionError):
            failed, lines = True, ["FAIL assets-unreadable"]
    for line in lines:
        print(line)
    print(f"{'FAIL' if failed else 'PASS'} npp_bracket_reach")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
