#!/usr/bin/env python3
"""Check that the two NPP ready-prompt builders agree, offline and read-only."""

import argparse
import ast
from itertools import product
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import npp

JOB_SOURCE = ROOT / "hass/npp/job.py"
PICTURES = (None, "picture_own_photo", "picture_house")
OTHER_PARTS = ("basic_wording", "story_not_found", "maker_left_off")

# Pin the builder through its handoff to self.reply, not just the appearance
# of a template and a cap elsewhere in finish. ASTs ignore line numbers,
# comments, whitespace and quote style; structural changes need reinspection.
READY_BRANCH = ast.parse('''
if card_path is not None:
    text = self.replies["prompts"]["ready"].format(code=jid, n=version["n"])
    if result.note and len(result.note) + 2 <= self.replies["caps"]["bracket_max_chars"]:
        text += f" ({result.note})"
    row = self.reply(job, text, pid, [str(card_path)])
''').body[0]


def part_subsets():
    for picture, *flags in product(PICTURES, (False, True), (False, True), (False, True)):
        parts = {key: {} for key, on in zip(OTHER_PARTS, flags) if on}
        if picture is not None:
            parts[picture] = {}
        yield parts


def has_inline_shape(tree):
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Jobs"]
    if len(classes) != 1:
        return False
    methods = [node for node in classes[0].body if isinstance(node, ast.FunctionDef) and node.name == "finish"]
    if len(methods) != 1:
        return False

    assert isinstance(READY_BRANCH, ast.If)
    assignment = READY_BRANCH.body[0]
    assert isinstance(assignment, ast.Assign) and isinstance(assignment.value, ast.Call)
    statements = [ast.dump(node) for node in READY_BRANCH.body]
    ready_format = ast.dump(assignment.value.func)
    card_check = ast.dump(READY_BRANCH.test)
    matches = formats = 0
    for node in ast.walk(methods[0]):
        if isinstance(node, ast.Call) and ast.dump(node.func) == ready_format:
            formats += 1
        if (isinstance(node, ast.If) and ast.dump(node.test) == card_check
                and [ast.dump(stmt) for stmt in node.body[:len(statements)]] == statements):
            matches += 1
    return matches == formats == 1


def compare_ready_lines():
    subsets = list(part_subsets())
    mismatches = []
    check_error = False
    try:
        # reply imports job. Defer it so broken job source cannot prevent
        # the CLI from reporting the separate parse check.
        from hass.npp import reply

        replies = npp.assets()[2]
    except Exception:
        return len(subsets), mismatches, True

    for index, parts in enumerate(subsets):
        try:
            a = reply.ready_line(replies, "abcd", 1, parts)
            note = reply.compose(replies, parts)
            b = replies["prompts"]["ready"].format(code="abcd", n=1)
            if note and len(note) + 2 <= replies["caps"]["bracket_max_chars"]:
                b += f" ({note})"
        except Exception:
            # Asset or builder errors may contain values we must not print.
            check_error = True
            continue
        if a != b:
            mismatches.append(index)
    return len(subsets), mismatches, check_error


def main(argv=None):
    # No supported arguments, including the otherwise implicit help switches.
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    total, mismatches, check_error = compare_ready_lines()
    print(f"ready subsets={total} mismatched={len(mismatches)}")
    for index in mismatches:
        print(f"FAIL ready-mismatch {index}")
    if check_error:
        print("FAIL check-error")

    try:
        tree = ast.parse(JOB_SOURCE.read_text(encoding="utf-8"))
    except (OSError, ValueError, SyntaxError, RecursionError):
        inline_shape, reason = False, "parse-error"
    else:
        inline_shape = has_inline_shape(tree)
        reason = None if inline_shape else "inline-shape-changed"
    print(f"ready inline_shape={'yes' if inline_shape else 'no'}")
    if reason:
        print(f"FAIL {reason}")

    failed = bool(mismatches or check_error or reason)
    print(f"{'FAIL' if failed else 'PASS'} npp_ready_line_parity")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
