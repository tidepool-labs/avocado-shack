#!/usr/bin/env python3
"""Check the NPP stages/job contract with Conversation without opening state."""

import argparse
import ast
import inspect
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SOURCES = (ROOT / "hass/npp/stages.py", ROOT / "hass/npp/job.py")
CONVERSATION_SOURCE = ROOT / "hass/conversation.py"
NAME = "npp_port_conversation_contract"


def port_name(node):
    """Return the name for an exact self.c.<name> access, not its chain."""
    if (isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute) and node.value.attr == "c"
            and isinstance(node.value.value, ast.Name) and node.value.value.id == "self"):
        return node.attr
    return None


def used_port():
    used, keywords = set(), set()
    for source in SOURCES:
        for node in ast.walk(ast.parse(source.read_bytes())):
            name = port_name(node)
            if name is not None:
                used.add(name)
            if isinstance(node, ast.Call) and (name := port_name(node.func)) is not None:
                keywords.update((name, kw.arg) for kw in node.keywords if kw.arg is not None)
    return used, keywords


def instance_attributes():
    tree = ast.parse(CONVERSATION_SOURCE.read_bytes())
    cls = next((node for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == "Conversation"), None)
    if cls is None:
        raise ValueError("Conversation class not found")
    # Store context includes chained and unpacking assignments but not reads
    # like self.outbox.add(...) or writes through self.outbox to another object.
    pending: list[ast.AST] = list(cls.body)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.ClassDef):
            continue  # A nested class has its own instance, not Conversation's.
        if (isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store)
                and isinstance(node.value, ast.Name) and node.value.id == "self"):
            yield node.attr
        pending.extend(ast.iter_child_nodes(node))


def incompatible_keywords(conversation, class_names, keywords):
    result = set()
    signatures = {}
    for name, keyword in sorted(keywords):
        if name not in class_names:
            continue  # Instance-assigned attributes have no class method to inspect.
        if name not in signatures:
            member = inspect.getattr_static(conversation, name)
            if isinstance(member, (staticmethod, classmethod)):
                member = member.__func__
            signatures[name] = inspect.signature(member) if inspect.isroutine(member) else None
        signature = signatures[name]
        if signature is not None:
            parameter = signature.parameters.get(keyword)
            named = parameter is not None and parameter.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY,
            )
            # A catch-all **kwargs does not declare the NPP port's named option.
            if not named:
                result.add((name, keyword))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)

    used, missing, bad_keywords = set(), set(), set()
    findings = []
    try:
        used, keywords = used_port()
        assigned = set(instance_attributes())
        sys.path.insert(0, str(ROOT))
        try:
            from hass.conversation import Conversation
        finally:
            sys.path.pop(0)
        class_names = set(dir(Conversation))
        missing = used - (class_names | assigned)
        bad_keywords = incompatible_keywords(Conversation, class_names, keywords)
    except (OSError, SyntaxError, ValueError, ImportError, AttributeError, TypeError, RecursionError):
        # A source/class contract that cannot be parsed or inspected cannot pass.
        findings.append("parse-error")
    else:
        if not used:
            findings.append("none-used")
    findings.extend(f"attribute-missing {name}" for name in sorted(missing))
    findings.extend(f"keyword-missing {name}.{keyword}" for name, keyword in sorted(bad_keywords))

    print(f"port used={len(used)}")
    print(f"port missing={len(missing)} bad_keywords={len(bad_keywords)}")
    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} {NAME}")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
