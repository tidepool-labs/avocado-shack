#!/usr/bin/env python3
"""Compare literal stage() names in Hass and Mac source with stagelog.ORDER."""

import argparse
import ast
from pathlib import Path
import re
import stat
import sys
import warnings

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from hass.stagelog import ORDER  # noqa: E402

MAX_BYTES = 1024 * 1024
STAGE_NAME = re.compile(r"[a-z][a-z0-9-]{0,39}")


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unrecognized tokens, which can be private paths.
        super().error("invalid arguments; see --help")


def source_files(root, findings):
    """Discover sources without traversing links or the excluded test tree."""
    excluded = root / "hass" / "tests"
    pending = [root / "mac", root / "hass"]
    files = []
    skipped = 0
    while pending:
        path = pending.pop()
        if path == excluded:
            continue
        try:
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                skipped += 1
            elif stat.S_ISDIR(info.st_mode):
                pending.extend(sorted(path.iterdir(), reverse=True))
            elif path.name.endswith(".py"):
                files.append((path, info))
            elif path.parent == root:
                findings.append("source-unreadable")
        except OSError:
            findings.append("source-unreadable")
    return sorted(files, key=lambda item: item[0].as_posix()), skipped


def recorded_names(path, info, findings):
    if not stat.S_ISREG(info.st_mode):
        findings.append("source-unreadable")
        return
    if info.st_size > MAX_BYTES:
        findings.append("source-too-large")
        return
    try:
        with path.open("rb") as source:
            data = source.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            findings.append("source-too-large")
            return
        # Parsing can warn about source text (e.g. invalid escape sequences).
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(data)
    except (OSError, SyntaxError, ValueError, RecursionError):
        findings.append("source-unreadable")
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func, first = node.func, node.args[0]
        is_stage = (isinstance(func, ast.Name) and func.id == "stage"
                    or isinstance(func, ast.Attribute) and func.attr == "stage")
        if is_stage and isinstance(first, ast.Constant) and isinstance(first.value, str):
            yield first.value


def main(argv=None):
    parser = ArgumentParser(prog="stage_name_drift.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="source root (default: checkout)")
    root = parser.parse_args(argv).root
    try:
        safe_root = stat.S_ISDIR(root.lstat().st_mode)
    except OSError:
        safe_root = False
    if not safe_root:
        print("FAIL unsafe-input")
        print("FAIL stage_name_drift")
        return 1

    findings = []
    files, skipped = source_files(root, findings)
    recorded = {name for path, info in files for name in recorded_names(path, info, findings)}
    known = set(ORDER)
    for name in sorted(recorded):
        if not STAGE_NAME.fullmatch(name):
            findings.append("stage-name-invalid")
        elif name not in known:
            findings.append(f"stage-not-in-order {name}")

    print(f"files {len(files)}")
    print(f"skipped {skipped}")
    print(f"stages-recorded {len(recorded)}")
    print(f"order {len(ORDER)}")
    for name in ORDER:
        if name not in recorded and STAGE_NAME.fullmatch(name):
            print(f"note order-not-recorded {name}")
    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} stage_name_drift")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
