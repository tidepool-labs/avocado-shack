#!/usr/bin/env python3
"""Replay the acceptance corpus through takes_turn, not the conversation command gate."""

import argparse
import json
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import npp
from hass.npp.reply import Stages

MESSAGES = ROOT / "hass/tests/fixtures/skills-acceptance/messages.jsonl"
MAX_BYTES = 1_048_576
SAFE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


class InputError(ValueError):
    """A fixed diagnostic that does not expose corpus data."""


def reject_constant(_token):
    raise ValueError("non-JSON constant")


def read_messages():
    try:
        info = MESSAGES.lstat()
    except OSError:
        raise InputError("input-unreadable") from None
    if not stat.S_ISREG(info.st_mode):
        raise InputError("input-unsafe")
    if info.st_size > MAX_BYTES:
        raise InputError("input-too-large")

    rows = []
    try:
        for number, line in enumerate(MESSAGES.read_text(encoding="utf-8").split("\n"), 1):
            if not line.strip():
                continue
            row = json.loads(line, parse_constant=reject_constant)
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise ValueError("invalid record")
            texts = row.get("texts")
            if not isinstance(texts, list) or not all(isinstance(text, str) for text in texts):
                raise ValueError("invalid texts")
            ident = row["id"]
            rows.append((ident if SAFE_ID.fullmatch(ident) else f"line{number}", texts))
    except (OSError, ValueError, RecursionError):
        raise InputError("input-unreadable") from None
    return rows


def finish(findings):
    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} npp_turn_routing_replay")
    return int(bool(findings))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    argv = sys.argv[1:] if argv is None else argv
    parser.parse_args(argv)
    if argv:  # Reject a bare end-of-options marker even if argparse consumes it.
        parser.error(f"unrecognized arguments: {' '.join(argv)}")

    try:
        pinned = npp.assets()
    except Exception:
        return finish(["assets-unreadable"])
    stages = Stages(pinned, start=None, render=None)
    try:
        rows = read_messages()
    except InputError as error:
        return finish([str(error)])

    total = asking = 0
    findings = []
    for ident, texts in rows:
        for i, text in enumerate(texts):
            total += 1
            asking += bool(stages.takes_turn(text, "asking"))
            if stages.takes_turn(text, "card_out"):
                findings.append(f"edit-taken {ident}-{i}")
    print(f"turns total={total} asking={asking} card_out={len(findings)}")
    return finish(findings)


if __name__ == "__main__":
    sys.exit(main())
