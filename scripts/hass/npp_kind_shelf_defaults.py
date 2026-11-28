#!/usr/bin/env python3
"""Check pinned NPP kind, shelf and description-default agreement offline."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import content_model
from hass import npp
from hass.npp import copy


def context(kind, shelf):
    return copy.Context(kind=kind, category=shelf, variant="raw", item="Example product")


def accepted_kinds(writer, kinds, shelves):
    accepted = set()

    def select(_step, _prompt, _schema, _options):
        accepted.add(kind)
        return None

    for kind in sorted(kinds | {"tool"}):
        # A missing default shelf must not be replaced with a valid one.
        shelf = "pantry" if kind == "tool" else shelves.get(kind, "-")
        writer.write(context(kind, shelf), select)
    return accepted


def check(info, findings):
    pinned = npp.assets()
    _, files, _ = pinned
    identify = json.loads(files["hass-product-identify/identify.schema.json"])
    kinds = set(identify["properties"]["kind"]["enum"])
    missing = json.loads(files["hass-missing-info/missing-info.json"])
    shelves = missing["kind_default_category"]
    writer = copy.Writer(pinned)
    descriptions = writer.spec["defaults"]["description"]
    accepted = accepted_kinds(writer, kinds, shelves)

    info.append("kinds " + " ".join(
        f"{source}={','.join(sorted(values))}"
        for source, values in (("identify", kinds), ("defaults", shelves), ("copy", accepted))
    ))
    if not kinds == shelves.keys() == accepted:
        findings.append("kind-sets-differ")
    for kind, shelf in sorted(shelves.items()):
        if shelf not in content_model.CATEGORIES:
            findings.append(f"shelf-unknown {kind}")

    for key in sorted(kinds | shelves.keys() | {"flowers"}):
        ctx = context("fresh", "flowers") if key == "flowers" else context(key, shelves.get(key, "-"))
        ids = descriptions.get(key)
        if not isinstance(ids, list) or not ids:
            # No ID exists to report as rung-missing; the ladder cannot qualify.
            findings.append("check-error")
            ids = []
        count = 0
        for template_id in ids:
            row = writer.templates.get(template_id)
            if row is None or row.get("field") != "description":
                findings.append(f"rung-missing {key} {template_id}")
            elif not copy.eligible(row, ctx):
                findings.append(f"rung-ineligible {key} {template_id}")
            else:
                count += 1
        info.append(f"kind {key} shelf={ctx.category} rungs={count}/{len(ids)}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    parser.parse_args(args)
    if args:  # argparse normally accepts a bare end-of-options marker.
        parser.error("no arguments expected")

    info, findings = [], []
    try:
        check(info, findings)
    except Exception:
        # Asset/check exceptions may contain paths or data; report only the fixed reason.
        findings.append("check-error")

    for line in info:
        print(line)
    for finding in dict.fromkeys(findings):
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} npp_kind_shelf_defaults")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
