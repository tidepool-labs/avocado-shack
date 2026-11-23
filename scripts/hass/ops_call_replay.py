#!/usr/bin/env python3
"""Replay recorded Hass calls through argument checks without applying them."""

import argparse
import io
import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.content_model import ContentError, load_and_validate  # noqa: E402
from hass.ops import check_args, load_registry  # noqa: E402

MAX_BYTES = 1_000_000
MAX_LINES = 2_000
CONTENT_FILES = ("products.json", "makers.json", "community.json", "store.json")


class ReplayParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse can include supplied values (e.g. in unrecognized arguments).
        super().error("expected --calls FILE and --content DIR")


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL ops_call_replay")
    return 1


def reject_constant(_token):
    raise ValueError("not a JSON number")


def replay_line(line, registry, makers):
    try:
        call = json.loads(line, parse_constant=reject_constant)
    except (ValueError, RecursionError):
        return "malformed"
    if not isinstance(call, dict) or not isinstance(call.get("op"), str):
        return "malformed"
    op = registry.get(call["op"])
    if op is None:
        return "unknown-op"
    problems, missing = check_args(op, call.get("args"), makers, None)
    return f"problems {len(problems)} missing {len(missing)}" if problems or missing else "ok"


def main(argv=None):
    parser = ReplayParser(prog="ops_call_replay", description=__doc__, allow_abbrev=False)
    parser.add_argument("--calls", required=True, type=Path, metavar="FILE")
    parser.add_argument("--content", required=True, type=Path, metavar="DIR")
    args = parser.parse_args(argv)

    try:
        if not stat.S_ISREG(args.calls.lstat().st_mode) or not stat.S_ISDIR(args.content.lstat().st_mode):
            return fail("unsafe-input")
        # Recheck the opened descriptor; never follow a replacement symlink or wait on a FIFO.
        with os.fdopen(os.open(args.calls, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode):
                return fail("unsafe-input")
            if info.st_size > MAX_BYTES:
                return fail("too-large")
            raw = source.read(MAX_BYTES + 1)
    except (OSError, ValueError):
        return fail("unsafe-input")
    if len(raw) > MAX_BYTES:
        return fail("too-large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return fail("not-utf8")
    lines = [(k, line) for k, line in enumerate(io.StringIO(text, newline=None), 1) if line.strip()]
    if len(lines) > MAX_LINES:
        return fail("too-many-lines")

    try:
        # Inspect metadata only; the content model owns ingestion and validation.
        for name in CONTENT_FILES:
            info = (args.content / name).lstat()
            if not stat.S_ISREG(info.st_mode):
                return fail("unsafe-input")
            if info.st_size > MAX_BYTES:
                return fail("too-large")
        content = load_and_validate(args.content, None)
    except (ContentError, ValueError, OSError):
        return fail("content-invalid")

    registry = load_registry()
    results = [(k, replay_line(line, registry, content.makers)) for k, line in lines]
    for k, result in results:
        print(f"line {k} {result}")
    ok = sum(result == "ok" for _, result in results)
    refused = len(results) - ok
    print(f"calls {len(results)}")
    print(f"ok {ok}")
    print(f"refused {refused}")
    if refused:
        return fail(f"refused {refused}")
    print("PASS ops_call_replay")
    return 0


if __name__ == "__main__":
    sys.exit(main())
