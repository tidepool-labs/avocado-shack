#!/usr/bin/env python3
"""Report drift between the NPP pins and the model steps duplicated in code."""

import argparse
import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

EDITS_SOURCE = ROOT / "hass/npp/edits.py"
FIELDS = ("model", "effort", "timeout_s")


def _edit_map_default(tree):
    mappers = [node for node in tree.body
               if isinstance(node, ast.FunctionDef) and node.name == "codex_mapper"]
    if len(mappers) != 1:
        return None
    matches = []
    pending: list[ast.AST] = list(mappers[0].body)
    while pending:
        node = pending.pop()
        # A fallback in a nested scope is not the mapper's fallback.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        pending.extend(ast.iter_child_nodes(node))
        match node:
            case ast.BoolOp(op=ast.Or(), values=[ast.Name(id="step"), ast.Dict() as literal]):
                matches.append(literal)
    if len(matches) != 1:
        return None
    try:
        default = ast.literal_eval(matches[0])
        fields = tuple(default[field] for field in FIELDS)
    except (KeyError, ValueError, TypeError, RecursionError):
        return None
    model, effort, timeout_s = fields
    if not isinstance(model, str) or not isinstance(effort, str) or type(timeout_s) not in (int, float):
        return None
    return fields


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    from hass import npp, photo_polish

    findings = []
    default = None
    try:
        tree = ast.parse(EDITS_SOURCE.read_bytes())
    except (OSError, ValueError, SyntaxError, RecursionError):
        findings.append("parse-error")
    else:
        default = _edit_map_default(tree)
        if default is None:
            findings.append("default-not-found")

    try:
        steps = npp.assets()[0]["steps"]
        pinned_edit = tuple(steps["edit_map"][field] for field in FIELDS)
        pinned_picture = steps["picture"]["model"]
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        # A pins/asset read or parse refusal also prevents a comparison.
        if "parse-error" not in findings:
            findings.append("parse-error")
    else:
        if default is not None:
            print("step edit_map default={}/{}/{} pinned={}/{}/{}".format(*default, *pinned_edit))
            for field, code, pin in zip(FIELDS, default, pinned_edit):
                if code != pin or type(code) is not type(pin):
                    findings.append(f"edit-map-default-drift {field}")
        picture = getattr(photo_polish, "MODEL", None)
        if isinstance(picture, str):
            print(f"step picture code={picture} pinned={pinned_picture}")
        if not isinstance(picture, str) or picture != pinned_picture:
            findings.append("picture-model-drift")

    for reason in findings:
        print(f"FAIL {reason}")
    print("FAIL npp_model_step_defaults" if findings else "PASS npp_model_step_defaults")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
