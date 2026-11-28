#!/usr/bin/env python3
"""Check the pinned S2 schema against the real photo-answer validator, offline."""

import argparse
import copy
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import npp
from hass.npp import identify


BASE = {
    "is_product": True,
    "kind": "food",
    "item": "Honey",
    "brand_on_label": None,
    "size_text": None,
    "label_words": [],
    "visible_claims": [],
    "category_guess": None,
    "has_person_or_screen": False,
    "confidence": dict.fromkeys(("kind", "item", "brand", "size", "category"), 0.5),
}
ANNOTATIONS = {"title", "$comment", "description"}
TOOL = "npp_identify_schema_enforced"


def _sites(rule, path=()):
    for keyword, value in rule.items():
        if keyword == "properties":
            for name, child in value.items():
                yield from _sites(child, (*path, name))
        elif keyword == "items":
            # The first element is the witness for a homogeneous item schema.
            yield from _sites(value, (*path, 0))
        elif keyword not in ANNOTATIONS:
            yield path, keyword, rule


def _json_path(path):
    return "$" + "".join(
        f".{key}" if isinstance(key, str) and key.isidentifier() else f"[{json.dumps(key)}]"
        for key in path
    )


def _schema_at(schema, path):
    for key in path:
        schema = schema["items"] if isinstance(key, int) else schema["properties"][key]
    return schema


def _break_type(rule, _value):
    expected = rule["type"]
    allowed = [expected] if isinstance(expected, str) else expected
    # In particular, True must not pass a numeric schema as the number 1.
    return next(sample for kind, sample in (
        ("boolean", True), ("null", None), ("number", 1), ("string", "x"),
        ("array", []), ("object", {}),
    ) if kind not in allowed)


def _text(rule):
    least = rule.get("minLength", 0)
    most = rule.get("maxLength", max(1, least))
    if not 0 <= least <= most:
        raise ValueError("no string witness")
    return "x" * min(max(1, least), most)


def _break_enum(rule, _value):
    # The pinned enums allow strings. Choose one within the length bounds.
    expected = rule["type"]
    if "string" not in ([expected] if isinstance(expected, str) else expected):
        raise ValueError("no supported enum witness")
    length = len(_text(rule))
    return next(char * length for char in "abcdefghijklmnopqrstuvwxyz"
                if char * length not in rule["enum"])


def _break_required(rule, value):
    value.pop(rule["required"][0])
    return value


def _break_additional(rule, value):
    if rule["additionalProperties"] is not False:
        raise ValueError("no closed-object witness")
    name = "extra"
    while name in rule["properties"] or name in value:
        name += "_"
    value[name] = None
    return value


def _break_min_length(rule, _value):
    if rule["minLength"] <= 0:
        raise ValueError("no shorter string witness")
    return "x" * (rule["minLength"] - 1)


def _break_max_items(rule, _value):
    item = rule["items"]
    if item["type"] != "string" or "enum" in item:
        raise ValueError("no supported array witness")
    return [_text(item)] * (rule["maxItems"] + 1)


MUTATIONS = {
    "type": _break_type,
    "enum": _break_enum,
    "required": _break_required,
    "additionalProperties": _break_additional,
    "minLength": _break_min_length,
    "maxLength": lambda rule, _: "x" * (rule["maxLength"] + 1),
    "maxItems": _break_max_items,
    "minimum": lambda rule, _: math.nextafter(rule["minimum"], -math.inf),
    "maximum": lambda rule, _: math.nextafter(rule["maximum"], math.inf),
}


def _probe(schema, path, keyword, rule):
    answer = copy.deepcopy(BASE)
    if not path:
        answer = MUTATIONS[keyword](rule, answer)
    else:
        parent = answer
        for key in path[:-1]:
            parent = parent[key]
        key = path[-1]
        if isinstance(key, int):
            if not isinstance(parent, list) or parent or _schema_at(schema, path[:-1])["maxItems"] < 1:
                raise ValueError("no isolated first-item witness")
            parent.append(MUTATIONS[keyword](rule, None))
        else:
            parent[key] = MUTATIONS[keyword](rule, parent[key])

    if keyword != "enum" and "enum" in rule:
        # A wrong-type value is also outside a well-typed enum. Remove just
        # that sibling rule so the enum cannot mask a different check.
        schema = copy.deepcopy(schema)
        del _schema_at(schema, path)["enum"]
    return identify._valid(answer, schema)


def _findings():
    _, files, _ = npp.assets()
    schema = json.loads(files[identify.ASSET + "identify.schema.json"])
    if not identify._valid(copy.deepcopy(BASE), schema):
        return ["base-refused"]

    sites = list(_sites(schema))
    keywords = {keyword for _, keyword, _ in sites}
    print(f"schema keywords={','.join(sorted(keywords))}")
    findings = []
    refused = 0
    for path, keyword, rule in sites:
        if keyword not in MUTATIONS:
            reason = f"unknown-keyword {keyword}"
            if reason not in findings:
                findings.append(reason)
            continue
        try:
            accepted = _probe(schema, path, keyword, rule)
        except Exception:
            if "check-error" not in findings:
                findings.append("check-error")
            continue
        if accepted:
            findings.append(f"not-enforced {_json_path(path)} {keyword}")
        else:
            refused += 1
    print(f"schema sites={len(sites)} refused={refused}")
    return findings


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)
    if argv:  # argparse consumes a bare '--' even though it is not an option here.
        parser.error("no arguments accepted")
    try:
        findings = _findings()
    except Exception:
        findings = ["check-error"]
    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} {TOOL}")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
