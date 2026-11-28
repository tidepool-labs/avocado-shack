#!/usr/bin/env python3
"""Compare the NPP timing pins with the reserves used by the card code."""

import argparse
import ast
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
STAGES = Path("hass/npp/stages.py")
GUARD = Path("hass/npp/__init__.py")
SOURCES = "hass-maker-research/sources.json"
NAME = "npp_stage_time_budgets"

sys.path.insert(0, str(REPO))


class ConstantNotFound(ValueError):
    """The expected source site was missing, ambiguous or not a literal."""


def _one(items):
    items = list(items)
    if len(items) != 1:
        raise ConstantNotFound
    return items[0]


def _definition(scope, kind, name):
    return _one(node for node in scope.body if isinstance(node, kind) and node.name == name)


def _expression(text):
    return ast.dump(ast.parse(text, mode="eval").body)


def _integer(value):
    if type(value) is not int:
        raise ValueError("expected integer seconds")
    return value


def _literal(nodes):
    node = _one(nodes)
    if not isinstance(node, ast.Constant) or type(node.value) is not int:
        raise ConstantNotFound
    return node.value


def _subtracted(scope, expression):
    left = _expression(expression)
    return _literal(node.right for node in ast.walk(scope)
                    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub)
                    and ast.dump(node.left) == left)


def _compared(scope, expression, operator):
    left = _expression(expression)
    return _literal(node.comparators[0] for node in ast.walk(scope)
                    if isinstance(node, ast.Compare) and len(node.ops) == 1
                    and isinstance(node.ops[0], operator) and ast.dump(node.left) == left)


def _stage_constants(tree):
    stages = _definition(tree, ast.ClassDef, "ProductionStages")
    research = _definition(stages, ast.FunctionDef, "_research")
    picture = _definition(stages, ast.FunctionDef, "_picture")
    render = _definition(stages, ast.FunctionDef, "render_listing")
    remaining = "self._remaining(work)"
    return (
        _subtracted(research, remaining + " - self.pinned[0]['steps']['copy_select']['timeout_s']"),
        _subtracted(picture, remaining),
        _compared(render, remaining, ast.Lt),
    )


def _cap_guard(tree):
    assets = _definition(tree, ast.FunctionDef, "assets")
    return _compared(assets, "pins['segment']['cap_s']", ast.NotEq)


def _report(findings):
    for finding in dict.fromkeys(findings):
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} {NAME}")
    return int(bool(findings))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    argv = sys.argv[1:] if argv is None else argv
    parser.parse_args(argv)
    if argv:  # argparse otherwise accepts a bare end-of-options marker.
        parser.error("this command takes no arguments")

    findings = []
    constants = {}
    for path, extract in ((STAGES, _stage_constants), (GUARD, _cap_guard)):
        try:
            constants[path] = extract(ast.parse((REPO / path).read_bytes()))
        except ConstantNotFound:
            findings.append(f"constant-not-found {path.as_posix()}")
        except (OSError, SyntaxError, ValueError):
            findings.append("parse-error")

    try:
        import hass.npp
        from hass import photo_polish

        pins, files, _ = hass.npp.assets()
        steps = pins["steps"]
        research_pin = _integer(steps["research_extract"]["stage_budget_s"])
        research_sources = _integer(json.loads(files[SOURCES])["fetch"]["stage_budget_seconds"])
        copy_timeout = _integer(steps["copy_select"]["timeout_s"])
        cap = _integer(pins["segment"]["cap_s"])
        polish = _integer(photo_polish.TIMEOUT_S)
        hard = _integer(steps["picture"]["hard_s"])
    except (OSError, SyntaxError, ValueError, KeyError, TypeError, ImportError, AttributeError) as exc:
        # The real loader rejects a cap mismatch before it can return any pins.
        # Do not bypass its verification to recover the rejected values.
        reason = ("cap-guard-drift" if GUARD in constants and isinstance(exc, ValueError)
                  and str(exc) == "invalid NPP segment cap" else "parse-error")
        return _report([*findings, reason])

    print(f"budget research pin={research_pin} sources={research_sources}")
    if research_pin != research_sources:
        findings.append("research-budget-drift")

    overrun = False
    if STAGES in constants:
        research_slack, picture_slack, copy_slack = constants[STAGES]
        pinned_slack = copy_timeout + research_slack
        # Show the divergent reserve if just the copy threshold changed.
        code_slack = picture_slack if picture_slack != pinned_slack else copy_slack
        print(f"budget slack code={code_slack} pinned={pinned_slack}")
        if picture_slack != pinned_slack or copy_slack != pinned_slack:
            findings.append("slack-drift")
        # Check both advertised and effective research budgets when they disagree.
        overrun = max(research_pin, research_sources) + pinned_slack > cap
    if GUARD in constants:
        guard = constants[GUARD]
        print(f"budget cap pin={cap} guard={guard}")
        if cap != guard:
            findings.append("cap-guard-drift")
    print(f"budget polish timeout={polish} hard={hard}")
    if overrun:
        findings.append("budget-overrun")
    return _report(findings)


if __name__ == "__main__":
    sys.exit(main())
