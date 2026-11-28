#!/usr/bin/env python3
"""Check editor and listing validator value shapes against NPP receipt rules."""

import argparse
import ast
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import editor  # noqa: E402
from hass.npp import evidence  # noqa: E402


def _name_literal(call):
    target, first = call.func, call.args[0]
    if isinstance(target, ast.Name) and target.id == "Verdict":
        if not isinstance(first, ast.Tuple) or len(first.elts) != 1:
            return None
        first = first.elts[0]
    elif not (isinstance(target, ast.Attribute) and target.attr == "append"
              and isinstance(target.value, ast.Name)
              and target.value.id in ("problems", "warnings")):
        return None
    return first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None


def _check_names(path):
    tree = ast.parse(path.read_bytes())
    # ast.walk is breadth-first; sort calls by location to keep source order.
    calls = sorted((node for node in ast.walk(tree) if isinstance(node, ast.Call) and node.args),
                   key=lambda node: (node.lineno, node.col_offset))
    return [name for call in calls if (name := _name_literal(call)) is not None]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    if args:
        parser.error("no arguments are accepted")

    findings = []

    def accepts(rules, key, value):
        try:
            return bool(evidence._accepts(rules[key], value))
        except Exception:
            # A broken rule is not a refusal; do not print its exception text.
            findings.append("check-error")
            return None

    dh = editor._draft_hash({"base": "sha256:" + "0" * 64, "ops": []})
    cid = "chg-" + dh[7:19]
    for label, rules, key, value, reason in (
        ("draft_hash", evidence._APPROVAL, "draft_hash", dh, "draft-hash-refused"),
        ("draft_hash_hex", evidence._APPROVAL, "draft_hash", dh[7:], None),
        ("change_id", evidence._APPROVAL, "change_id", cid, "change-id-refused"),
        ("commit", evidence._PUBLISH, "commit", "a" * 40, None),
    ):
        ok = accepts(rules, key, value)
        if ok is not None:
            print(f"evidence {label}={'ok' if ok else 'refused'}")
        if ok is False and reason is not None:
            findings.append(reason)

    try:
        names = _check_names(ROOT / "hass/npp/validate.py")
    except (OSError, SyntaxError, ValueError, RecursionError):
        findings.append("parse-error")
    else:
        if not names:
            findings.append("no-check-names")
        refused = 0
        complete = True
        for name in names:
            ok = accepts(evidence._CHECK, "name", name)
            if ok is None:
                complete = False
            elif not ok:
                refused += 1
                findings.append(f"check-name-refused {name}")
        if complete:
            print(f"evidence check_names={len(names)} refused={refused}")

    # Count literal occurrences above, but report each distinct finding once.
    for reason in dict.fromkeys(findings):
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} npp_evidence_value_fit")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
