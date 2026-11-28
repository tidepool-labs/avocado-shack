#!/usr/bin/env python3
"""Check pinned maker-fact row rules against the offline extraction checker."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import npp
from hass.npp import research


NAME = "npp_facts_rows_enforced"
ASSET = "hass-maker-research/facts.schema.json"
ROW = {"slot": "makes", "value": "honey", "url": "https://ettofarm.example/",
       "quote": "Etto Farm makes honey."}
FIELD_KEYWORDS = {"type", "enum", "minLength", "maxLength"}


def _matches(value, spec):
    """Select witnesses for the pinned string constraints, not an acceptance oracle."""
    return (isinstance(value, str)
            and ("enum" not in spec or value in spec["enum"])
            and ("minLength" not in spec or len(value) >= spec["minLength"])
            and ("maxLength" not in spec or len(value) <= spec["maxLength"]))


def _seed(field, spec):
    if spec["type"] != "string":
        raise ValueError("unsupported field type")
    current = ROW.get(field)
    if _matches(current, spec):
        return current
    if "enum" in spec:
        return next(value for value in spec["enum"] if _matches(value, spec))
    # A tighter pin may invalidate ROW; keep that failure separate from the probes.
    candidate = "x" * spec.get("minLength", min(1, spec.get("maxLength", 1)))
    if not _matches(candidate, spec):
        raise ValueError("no valid string seed")
    return candidate


def _outside_enum(spec, seed):
    length_spec = {k: v for k, v in spec.items() if k != "enum"}
    if _matches("phone", length_spec) and "phone" not in spec["enum"]:
        return "phone"
    # One more distinct string than the enum has entries is enough to find a miss
    # at this allowed length, if such strings exist in the search alphabet.
    for index in range(len(spec["enum"]) + 1):
        if not seed or index >= 0xD800 - ord("a"):
            break
        candidate = chr(ord("a") + index) + seed[1:]
        if candidate not in spec["enum"]:
            return candidate
    raise ValueError("no isolated enum witness")


def _cases(schema, facts, seed):
    items = facts["items"]
    limit = facts["maxItems"]
    extra = "id"
    while extra in seed:
        extra += "_"
    missing = "quote" if "quote" in items["required"] else items["required"][0]
    yield "top.additionalProperties", {"facts": [seed], "id": 0}, schema
    yield "facts.type", {"facts": seed}, schema
    yield "facts.maxItems", {"facts": [seed] * (limit + 1)}, schema
    yield "items.additionalProperties", {"facts": [seed | {extra: 0}]}, schema
    yield "items.required", {"facts": [{k: v for k, v in seed.items() if k != missing}]}, schema
    for field, spec in items["properties"].items():
        for keyword in ("enum", "minLength", "maxLength", "type"):
            if keyword not in spec:
                continue
            probe_schema = schema
            if keyword == "type":
                value = 1
                if "enum" in spec and value not in spec["enum"]:
                    # A string-only enum would reject the integer on its own.
                    # Widen just that enum in a copy to exercise the type check alone.
                    probe_schema = deepcopy(schema)
                    probe_schema["properties"]["facts"]["items"]["properties"][field]["enum"].append(value)
            elif keyword == "enum":
                value = _outside_enum(spec, seed[field])
            else:
                size = spec[keyword] + (-1 if keyword == "minLength" else 1)
                if size < 0:
                    raise ValueError("no negative length witness")
                value = "x" * size
                if not _matches(value, {k: v for k, v in spec.items() if k != keyword}):
                    raise ValueError("length witness violates another constraint")
            yield f"{field}.{keyword}", {"facts": [seed | {field: value}]}, probe_schema


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    if args:
        parser.error("unrecognized arguments: " + " ".join(args))
    findings = []
    sites = refused = 0

    def check_error():
        if "check-error" not in findings:
            findings.append("check-error")

    def check(result, schema, reason, *, expect_refused=False):
        nonlocal sites, refused
        sites += expect_refused
        try:
            rejected = research._rows(result, schema) is None
        except Exception:
            check_error()
            return
        refused += expect_refused and rejected
        if rejected != expect_refused:
            findings.append(reason)

    try:
        _, files, _ = npp.assets()
        schema = json.loads(files[ASSET])
        check({"facts": [ROW.copy()]}, schema, "base-refused")
        facts = schema["properties"]["facts"]
        items = facts["items"]
        fields = items["properties"]
        for keyword in sorted(set().union(*fields.values()) - FIELD_KEYWORDS):
            findings.append(f"unknown-keyword {keyword}")
        # Unhandled structural edits must not silently license a partial PASS.
        if (schema["type"] != "object" or schema["additionalProperties"] is not False
                or schema["required"] != ["facts"] or set(schema["properties"]) != {"facts"}
                or set(facts) != {"type", "maxItems", "items"} or facts["type"] != "array"
                or set(items) != {"type", "additionalProperties", "required", "properties"}
                or items["type"] != "object" or items["additionalProperties"] is not False
                or set(items["required"]) != set(fields)
                or type(facts["maxItems"]) is not int or facts["maxItems"] < 0):
            raise ValueError("unsupported facts schema shape")
        seed = {field: _seed(field, spec) for field, spec in fields.items()}
        check({"facts": [seed] * facts["maxItems"]}, schema, "limit-refused")
        for rule, result, probe_schema in _cases(schema, facts, seed):
            check(result, probe_schema, f"not-enforced {rule}", expect_refused=True)
    except Exception:
        check_error()

    for finding in findings:
        print(f"FAIL {finding}")
    print(f"facts sites={sites} refused={refused}")
    print(f"{'FAIL' if findings else 'PASS'} {NAME}")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
