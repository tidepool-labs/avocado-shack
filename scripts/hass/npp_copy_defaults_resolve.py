#!/usr/bin/env python3
"""Check that pinned NPP fallback template IDs resolve to the expected fields."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import npp


ASSET = "hass-listing-copy/copy-templates.json"
FIELDS = ("name", "imageAlt", "description", "story")


def id_list(value):
    if not isinstance(value, list):
        raise ValueError("expected a list of template IDs")
    return value


def check():
    _, files, _ = npp.assets()
    spec = json.loads(files[ASSET])
    defaults = spec["defaults"]
    if not isinstance(defaults, dict) or not isinstance(spec["templates"], list):
        raise ValueError("invalid copy template document")
    # Match Writer's lookup, including which row wins if an ID is repeated.
    templates = {row["id"]: row for row in spec["templates"]}
    refs = {field: [] for field in FIELDS}
    findings = []
    for field in FIELDS:
        if field not in defaults:
            findings.append(f"default-key-missing {field}")
            continue
        value = defaults[field]
        if field == "description":
            refs[field] = [key for ladder in value.values() for key in id_list(ladder)]
        elif field == "story":
            refs[field] = id_list(value["order"])
        else:
            refs[field] = [value]
        for key in refs[field]:
            if not isinstance(key, str) or not key or not key.isprintable() or any(c.isspace() for c in key):
                raise ValueError("invalid template ID")
            if key not in templates:
                findings.append(f"default-missing {field} {key}")
            elif templates[key]["field"] != field:
                findings.append(f"default-wrong-field {field} {key}")

    name = (refs["name"] or ["-"])[0]
    alt = (refs["imageAlt"] or ["-"])[0]
    total = sum(map(len, refs.values()))
    print(f"defaults refs={total} name={name} imageAlt={alt} "
          f"description={len(refs['description'])} story={len(refs['story'])}")
    return findings


def main(argv=None):
    # This is a zero-argument check; even argparse's automatic help is disabled.
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    try:
        findings = check()
    except Exception:
        # Do not leak exceptions from the asset loader or a malformed document.
        findings = ["check-error"]
    for reason in findings:
        print(f"FAIL {reason}")
    print("FAIL npp_copy_defaults_resolve" if findings else "PASS npp_copy_defaults_resolve")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
