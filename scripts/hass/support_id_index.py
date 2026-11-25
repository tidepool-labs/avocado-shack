#!/usr/bin/env python3
"""Check every hass/health.py check id has a SUPPORT.md section, and the reverse.

Read-only and offline: health.py is parsed with ast, never imported or run.
Output is `ids ...` counts, one `FAIL <reason>` line per finding, then a trailer.
"""

import argparse
import ast
from pathlib import Path
import re
import sys


HEALTH = "hass/health.py"
SUPPORT = "docs/hass/SUPPORT.md"
TRAILER = "support_id_index"
ID = r"[A-Za-z0-9][A-Za-z0-9_.-]*"
HEADING = re.compile(rf"### `({ID})`[ \t]*")


def read_input(repo, relative):
    path = repo / relative
    try:
        return path.read_bytes() if path.is_file() else None
    except OSError:
        return None


def code_ids(tree):
    """Return (ids, unresolved) for the bare `_problem(...)` call sites."""
    ids, unresolved = set(), 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "_problem"):
            continue
        first = node.args[0] if node.args else None
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            ids.add(first.value)  # any string literal is a known id (C7)
        else:  # a variable, expression, f-string, starred or keyword-only id
            unresolved += 1
    return ids, unresolved


def printable(name):
    """Keep one finding on one ASCII line: odd literals print as an escaped repr."""
    if name and name.isascii() and name.isprintable() and name == name.strip():
        return name
    return ascii(name)


def doc_ids(text):
    matches = (HEADING.fullmatch(line) for line in text.splitlines())
    return {match.group(1) for match in matches if match}


def check(repo):
    """Return (info lines, finding lines) for one repo."""
    health, support = read_input(repo, HEALTH), read_input(repo, SUPPORT)
    if health is None or support is None:
        return [], [f"FAIL no-file {name}" for name, raw in
                    ((HEALTH, health), (SUPPORT, support)) if raw is None]
    try:
        tree = ast.parse(health)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return [], ["FAIL bad-python"]

    known, unresolved = code_ids(tree)
    documented = doc_ids(support.decode("utf-8", errors="replace"))
    info = [f"ids code {len(known)}", f"ids doc {len(documented)}"]
    findings = [f"FAIL undocumented {printable(name)}" for name in sorted(known - documented)]
    if not unresolved:  # with unresolved calls, absence cannot be established
        findings += [f"FAIL stale-doc {name}" for name in sorted(documented - known)]
    else:
        findings.append(f"FAIL unresolved-dynamic {unresolved}")
    return info, findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path,
                        help="repository root (read only)")
    args = parser.parse_args(argv)
    info, findings = check(args.repo)
    lines = info + findings
    lines.append(f"FAIL {TRAILER}" if findings else f"PASS {TRAILER}")
    sys.stdout.write("".join(line + "\n" for line in lines))
    sys.stdout.flush()
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
