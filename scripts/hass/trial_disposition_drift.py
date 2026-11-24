#!/usr/bin/env python3
"""List literal conversation dispositions that the trial summary counts as other."""

import argparse
import ast
from collections import Counter
import errno
from io import BytesIO
import os
from pathlib import Path
import re
import stat
import sys
import tokenize


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hass.trial_summary import _bucket  # noqa: E402


MAX_SOURCE_BYTES = 2 * 1024 * 1024
VALUE_PATTERN = re.compile(r"[a-z][a-z0-9-]*(?::[a-z0-9-]+)?")


class InputError(ValueError):
    """Carries only a fixed finding label, never path or source text."""


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's default error text can echo arbitrary positional arguments.
        super().error("invalid arguments")


def read_source(path):
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            raise InputError("unsafe-input")
        # Refuse a symlink swap, and don't block if the path becomes a FIFO.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise InputError("unsafe-input")
            if info.st_size > MAX_SOURCE_BYTES:
                raise InputError("too-large")
            raw = source.read(MAX_SOURCE_BYTES + 1)
    except OSError as exc:
        reason = "unsafe-input" if exc.errno == errno.ELOOP else "unreadable-input"
        raise InputError(reason) from None
    if len(raw) > MAX_SOURCE_BYTES:
        raise InputError("too-large")
    try:
        encoding, _ = tokenize.detect_encoding(BytesIO(raw).readline)
        return raw.decode(encoding)
    except (SyntaxError, UnicodeError, LookupError):
        raise InputError("unreadable-input") from None


def is_disposition_name(node):
    return isinstance(node, ast.Name) and node.id == "disposition"


def disposition_expressions(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(map(is_disposition_name, node.targets)):
            yield node.value
        elif isinstance(node, ast.AnnAssign) and is_disposition_name(node.target):
            if node.value is not None:
                yield node.value
        elif isinstance(node, ast.keyword) and node.arg == "disposition":
            yield node.value
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "disposition":
                    yield value


def value_leaves(expression):
    """Yield literal strings, and one None for each unresolved branch."""
    pending = [expression]
    while pending:
        node = pending.pop()
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value
        elif isinstance(node, ast.IfExp):
            pending.extend((node.body, node.orelse))
        elif isinstance(node, (ast.BoolOp, ast.Dict)):
            pending.extend(node.values)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr == "get" and len(node.args) == 2 and not node.keywords
              and not any(isinstance(arg, ast.Starred) for arg in node.args)):
            pending.extend((node.func.value, node.args[1]))
        else:
            yield None


def main(argv=None):
    parser = PrivateArgumentParser(prog="trial_disposition_drift.py", description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "hass/conversation.py",
                        help="Python source file (default: hass/conversation.py)")
    args = parser.parse_args(argv)
    try:
        source = read_source(args.source)
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError, RecursionError):
            raise InputError("source-unparsable") from None
    except InputError as exc:
        print(f"FAIL {exc}")
        print("FAIL trial_disposition_drift")
        return 1

    values = set()
    dynamic = nonconforming = 0
    for expression in disposition_expressions(tree):
        for value in value_leaves(expression):
            if value is None:
                dynamic += 1
            elif VALUE_PATTERN.fullmatch(value):
                values.add(value)
            else:
                nonconforming += 1

    buckets = Counter()
    uncounted = []
    for value in sorted(values):
        bucket = _bucket(value)
        buckets[bucket] += 1
        if bucket == "other" and value != "other":
            uncounted.append(value)
    print(f"values {len(values)}")
    print(f"dynamic {dynamic}")
    print(f"nonconforming {nonconforming}")
    for bucket, count in sorted(buckets.items()):
        print(f"bucket {bucket} {count}")
    for value in uncounted:
        print(f"FAIL uncounted {value}")
    print("FAIL trial_disposition_drift" if uncounted else "PASS trial_disposition_drift")
    return int(bool(uncounted))


if __name__ == "__main__":
    sys.exit(main())
