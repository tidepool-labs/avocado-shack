#!/usr/bin/env python3
"""Check offline parity between selected picture variants, the job gate, and pinned notes."""

import argparse
import ast
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
PHOTOS = "hass/ops/photos.py"
JOB = "hass/npp/job.py"
STAGES = "hass/npp/stages.py"
EXPECTED_NOTE_PARTS = {"raw": "picture_own_photo", "house": "picture_house"}


def _unique_definition(body, kind, name):
    matches = [node for node in body if isinstance(node, kind) and node.name == name]
    return matches[0] if len(matches) == 1 else None


def _function_nodes(function):
    """Walk the function body, without matching in a nested definition."""
    pending = list(reversed(function.body))
    while pending:
        node = pending.pop()
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            yield node
            pending.extend(reversed(list(ast.iter_child_nodes(node))))


def _string(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _chosen(tree):
    select = _unique_definition(tree.body, ast.FunctionDef, "select_variant")
    if select is None:
        return None
    nodes = list(_function_nodes(select))
    assignments = {}
    for node in nodes:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        value = node.value
        if isinstance(target, ast.Tuple) and target.elts and isinstance(value, ast.Tuple) and value.elts:
            target, value = target.elts[0], value.elts[0]
        if isinstance(target, ast.Name) and target.id == "variant":
            assignments[target] = _string(value)
    # Do not certify a partial set if a variant assignment became nonliteral
    # or moved to an unsupported assignment form.
    stores = {node for node in nodes if isinstance(node, ast.Name) and node.id == "variant"
              and isinstance(node.ctx, (ast.Store, ast.Del))}
    if not assignments or stores != assignments.keys() or None in assignments.values():
        return None
    return set(assignments.values())


def _accepted(tree):
    jobs = _unique_definition(tree.body, ast.ClassDef, "Jobs")
    finish = _unique_definition(jobs.body, ast.FunctionDef, "finish") if jobs else None
    if finish is None:
        return None
    matches = [node for node in _function_nodes(finish)
               if isinstance(node, ast.Compare) and isinstance(node.left, ast.Attribute)
               and node.left.attr == "variant" and isinstance(node.left.value, ast.Name)
               and node.left.value.id == "result" and isinstance(node.ops[0], (ast.In, ast.NotIn))]
    if len(matches) != 1:
        return None
    (match,) = matches
    if len(match.ops) != 1 or not isinstance(match.ops[0], ast.In):
        return None
    (variants,) = match.comparators
    if not isinstance(variants, ast.Tuple):
        return None
    words = {_string(item) for item in variants.elts}
    return words if None not in words else None


def _note_parts(tree):
    stages = _unique_definition(tree.body, ast.ClassDef, "ProductionStages")
    render = _unique_definition(stages.body, ast.FunctionDef, "render_listing") if stages else None
    if render is None:
        return None

    # Recognize the guarded write in the method body, not a matching ternary
    # elsewhere. The literal arms are evidence; their order is not assumed.
    note_guards = [node for node in render.body if isinstance(node, ast.If)
                   and isinstance(node.test, ast.Attribute) and node.test.attr == "note"
                   and isinstance(node.test.value, ast.Name) and node.test.value.id == "frozen"]
    if len(note_guards) != 1:
        return None
    match note_guards[0]:
        case ast.If(orelse=[], body=[ast.Assign(
            targets=[ast.Subscript(value=ast.Name(id="parts") as target, slice=ast.IfExp(
                test=ast.Compare(left=ast.Attribute(value=ast.Name(id="frozen"), attr="variant"),
                                 ops=[ast.Eq()], comparators=[ast.Constant(value="raw")]),
                body=ast.Constant(value=str(raw)), orelse=ast.Constant(value=str(house))))],
            value=ast.Dict(keys=[]),
        )]):
            if ({raw, house} == set(EXPECTED_NOTE_PARTS.values())
                    and _known_parts_flow(render, note_guards[0], target, {raw, house})):
                return {"raw": raw, "house": house}
    return None


def _known_parts_flow(render, guard, target, picture_keys):
    """Refuse a decoy write if the ready prompt uses different or later-mutated parts."""
    index = render.body.index(guard)
    if not index or not isinstance(render.body[-1], ast.Return):
        return False
    match render.body[index - 1]:
        case ast.Assign(targets=[ast.Name(id="parts") as initial], value=ast.Dict(keys=[])):
            allowed = {initial, target}
        case _:
            return False
    match render.body[-1]:
        case ast.Return(value=ast.Call(func=ast.Name(id="Card"), args=[*_, ast.Call(
            func=ast.Name(id="compose"), args=[_, ast.Name(id="parts") as output], keywords=[],
        )])):
            allowed.add(output)
        case _:
            return False
    for node in ast.walk(render):
        match node:
            case ast.Subscript(value=ast.Name(id="parts") as other,
                               slice=ast.Constant(value=str(key)), ctx=ast.Store()) if key not in picture_keys:
                allowed.add(other)
    return all(node in allowed for node in ast.walk(render) if isinstance(node, ast.Name) and node.id == "parts")


def _print_variants(label, variants):
    print(f"variants {label}={','.join(sorted(variants))}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = list(sys.argv[1:] if argv is None else argv)
    parser.parse_args(args)
    if args:  # argparse may consume a bare end-of-options marker.
        parser.error("no arguments are accepted")

    findings = []
    sources = {}
    for label, path, extract in (("chosen", PHOTOS, _chosen), ("accepted", JOB, _accepted),
                                 ("note_parts", STAGES, _note_parts)):
        try:
            found = extract(ast.parse((ROOT / path).read_bytes()))
        except (OSError, SyntaxError, ValueError, RecursionError):
            findings.append("parse-error")
            continue
        if found is None:
            findings.append(f"variants-not-found {path}")
        else:
            sources[label] = found
            if label != "note_parts":
                _print_variants(label, found)

    notes = parts = None
    try:
        from hass.npp import picture
        notes = picture._NOTES
        if not isinstance(notes, dict) or not all(isinstance(key, str) for key in notes):
            raise ValueError("invalid variant notes")
    except (ImportError, OSError, SyntaxError, ValueError, AttributeError):
        findings.append("parse-error")
        notes = None
    try:
        from hass import npp
        parts = npp.assets()[2]["brackets"]["parts"]
        if not isinstance(parts, dict):
            raise ValueError("invalid bracket parts")
    except (ImportError, OSError, SyntaxError, ValueError, TypeError, KeyError, IndexError, RecursionError):
        findings.append("parse-error")
        parts = None

    if notes is not None:
        _print_variants("noted", notes)
    if "chosen" in sources and "accepted" in sources:
        findings.extend(f"variant-not-accepted {v}" for v in sorted(sources["chosen"] - sources["accepted"]))
    if "chosen" in sources and notes is not None:
        findings.extend(f"note-without-variant {v}" for v in sorted(notes.keys() - sources["chosen"]))
    if notes is not None and parts is not None and "note_parts" in sources:
        differing = [part for v, part in sources["note_parts"].items()
                     if v not in notes or part not in parts or notes[v] != parts[part]
                     or part != EXPECTED_NOTE_PARTS[v]]
        print(f"variants note_words={'differ' if differing else 'same'}")
        findings.extend(f"note-words-differ {part}" for part in differing)

    for finding in dict.fromkeys(findings):
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} npp_picture_variant_parity")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
