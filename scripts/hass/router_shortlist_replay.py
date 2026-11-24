#!/usr/bin/env python3
"""Replay fixture messages through the offline Hass skill shortlist."""

import argparse
import errno
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import hass.skills
from hass.skills import router

DEFAULT_CASES = ROOT / "hass/tests/fixtures/skills-acceptance/messages.jsonl"
MAX_BYTES = 1024 * 1024
MAX_LINES = 2000
SAFE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


class InputError(ValueError):
    """A fixed finding code safe to print."""


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's diagnostic can include unrecognized arguments verbatim.
        super().error("invalid arguments")


def read_lines(path):
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            raise InputError("unsafe-input")
        # Refuse leaf symlinks and avoid blocking if a FIFO replaces the input.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise InputError("unsafe-input")
            if info.st_size > MAX_BYTES:
                raise InputError("too-large")
            raw = source.read(MAX_BYTES + 1)
    except InputError:
        raise
    except OSError as exc:
        reason = "unsafe-input" if exc.errno == errno.ELOOP else "unreadable-input"
        raise InputError(reason) from None
    except ValueError:
        raise InputError("unreadable-input") from None

    if len(raw) > MAX_BYTES:
        raise InputError("too-large")
    try:
        lines = raw.decode("utf-8").removesuffix("\n").split("\n") if raw else []
    except UnicodeDecodeError:
        raise InputError("unreadable-input") from None
    if len(lines) > MAX_LINES:
        raise InputError("too-many-lines")
    return lines


def reject_constant(_value):
    raise ValueError("non-JSON constant")


def parse_case(line):
    try:
        case = json.loads(line, parse_constant=reject_constant)
    except (ValueError, RecursionError):
        return None
    if not isinstance(case, dict):
        return None
    texts = case.get("texts")
    photos = case.get("photos", [])
    if (not isinstance(case.get("id"), str) or not isinstance(case.get("skill"), str)
            or not isinstance(texts, list) or not texts or not all(isinstance(t, str) for t in texts)
            or not isinstance(photos, list)):
        return None
    return case["id"], case["skill"], texts[0], bool(photos)


def finish(failed):
    print(f"{'FAIL' if failed else 'PASS'} router_shortlist_replay")
    return int(failed)


def main(argv=None):
    parser = PrivateArgumentParser(prog="router_shortlist_replay.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, metavar="FILE")
    args = parser.parse_args(argv)

    try:
        lines = read_lines(args.cases)
    except InputError as exc:
        print(f"FAIL {exc}")
        return finish(True)

    cases = []
    failed = False
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        case = parse_case(line)
        if case is None:
            print(f"FAIL case-invalid {number}")
            failed = True
        else:
            cases.append(case)

    try:
        skills = hass.skills.load_skills()
    except Exception:
        print("FAIL skills-invalid")
        return finish(True)

    counts = dict.fromkeys(("rank1", "top3", "absent", "expect-none"), 0)
    for case_id, skill, first_text, attachment in cases:
        try:
            names = [name for name, _ in router.candidates(first_text, attachment=attachment, skills=skills)]
        except Exception:
            print("FAIL check-error")
            failed = True
            continue
        if skill == "none":
            counts["expect-none"] += 1
        elif names and names[0] == skill:
            counts["rank1"] += 1
        elif skill in names:
            counts["top3"] += 1
        else:
            counts["absent"] += 1
            print(f"FAIL absent {case_id}" if SAFE_ID.fullmatch(case_id) else "FAIL absent-id-invalid")
            failed = True

    print(f"cases {len(cases)}")
    for label, count in counts.items():
        print(label, count)
    return finish(failed)


if __name__ == "__main__":
    sys.exit(main())
