#!/usr/bin/env python3
"""Compare deterministic S10 patches with direct listing reads in the card renderer."""

import argparse
import ast
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
STAGES_PATH = ROOT / "hass/npp/stages.py"
sys.path.insert(0, str(ROOT))

from hass import npp
from hass.npp import edits

RENDER_METHODS = {"render_listing", "_picture", "_candidate"}
RENDER_HELPERS = {"_picture", "_candidate"}


def patched_fields():
    files = npp.assets()[1]
    grammar = edits.Grammar(files)
    fields = {field for field, _ in edits.price_patch({"price": "5.00", "sold_by": "pound"})}
    for form in json.loads(files[edits.GRAMMAR])["forms"]:
        for example in form["examples"]:
            result = edits.read(grammar, example["text"], {"price": "5.00", "sold_by": "item"})
            fields.update(field for field, _ in result.patch)
    return fields


def named(node, name):
    return isinstance(node, ast.Name) and node.id == name


def render_reads():
    """Return direct keys (or None on parse failure) and any opaque reads/calls."""
    try:
        module = ast.parse(STAGES_PATH.read_bytes())
    except (OSError, SyntaxError, ValueError, RecursionError):
        return None, ["parse-error"]

    stages = next((node for node in module.body
                   if isinstance(node, ast.ClassDef) and node.name == "ProductionStages"), None)
    methods = {node.name: node for node in stages.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))} if stages else {}
    if not RENDER_METHODS <= methods.keys():
        return None, ["parse-error"]

    keys, escapes = set(), []
    dynamic = False
    for method in RENDER_METHODS:
        for node in ast.walk(methods[method]):
            if isinstance(node, ast.Subscript) and named(node.value, "listing"):
                key = node.slice
            elif isinstance(node, ast.Call):
                callee = node.func
                if any(named(arg, "listing") for arg in (*node.args, *(kw.value for kw in node.keywords))):
                    if not (isinstance(callee, ast.Attribute) and named(callee.value, "self")
                            and callee.attr in RENDER_HELPERS):
                        escapes.append((node.lineno, node.col_offset, ast.unparse(callee)))
                if not (isinstance(callee, ast.Attribute) and named(callee.value, "listing")
                        and callee.attr == "get"):
                    continue
                key = node.args[0] if node.args else None
            else:
                continue
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.add(key.value)
            else:
                dynamic = True

    findings = [] if keys else ["parse-error"]
    if dynamic:
        findings.append("dynamic-read")
    findings.extend(f"listing-escapes {callee}" for _, _, callee in sorted(escapes))
    return keys or None, findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)
    try:
        fields = patched_fields()
    except Exception:  # An incomplete edit check must not expose example text or exception details.
        findings = ["check-error"]
    else:
        reads, findings = render_reads()
        if reads is not None:
            for field in sorted(fields):
                print(f"field {field} read={'yes' if field in reads else 'no'}")
            findings.extend(f"unread-field {field}" for field in sorted(fields - reads))

    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} npp_edit_field_reach")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
