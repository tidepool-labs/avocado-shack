#!/usr/bin/env python3
"""Check the pinned NPP reply template caps without running the pipeline."""

import argparse
from pathlib import Path
import re
from string import Formatter
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import npp
from hass.npp import reply

FILL = 'x' * 20
GROUPS = ("questions", "prompts", "guards", "confirm", "edits")


def fill_args(text):
    return {field: FILL for _, field, _, _ in Formatter().parse(text) if field is not None}


def sentence_count(text):
    # Informational count: mirror the body regex in reply.one_line, not its boolean decision.
    body = re.sub(r"\s*\([^()]*\)$", "", text)
    return len(re.findall(r"[.!?](?:\s|$)", body))


def check_lines(replies, question_cap):
    for group in GROUPS:
        for key, text in replies[group].items():
            served_guard = group == "guards" and key != "guard_note"
            if served_guard:
                text = reply.guard(replies, key)
            one = reply.one_line(text)
            print(f"line {group}.{key} chars={len(text)} sentences={sentence_count(text)} "
                  f"one_line={'yes' if one else 'no'}")
            if group == "questions" and len(text.format(**fill_args(text))) > question_cap:
                yield f"question-too-long {key}"
            if (served_guard or group == "edits") and not one:
                yield f"guard-not-one-line {key}"


def check_parts(replies, bracket_cap):
    brackets = replies["brackets"]
    parts = brackets["parts"]
    ordered = dict.fromkeys(brackets["compose"]["drop_order"])
    for key in dict.fromkeys((*parts, *ordered)):
        has_part = key in parts
        unordered = not has_part or key not in ordered
        args = fill_args(parts[key]) if has_part else {}
        # Count the full text even when compose will drop it.
        text = parts[key].format(**args) if has_part else ""
        too_long = has_part and len(text) + 2 > bracket_cap
        if has_part:
            print(f"part {key} chars={len(text)}")
        if too_long:
            yield f"part-too-long {key}"

        try:
            composed = reply.compose(replies, {key: args})
        except (KeyError, ValueError):
            if not unordered:
                raise
        else:
            if not unordered and composed != ("" if too_long else text):
                raise ValueError("unexpected singleton bracket")
        if unordered:
            yield f"part-unordered {key}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)
    failed = False
    try:
        _, _, replies = npp.assets()
        caps = replies["caps"]
        question_cap, bracket_cap = caps["question_max_chars"], caps["bracket_max_chars"]
        if any(type(cap) is not int or cap < 0 for cap in (question_cap, bracket_cap)):
            raise ValueError("invalid reply cap")
        for check, cap in ((check_lines, question_cap), (check_parts, bracket_cap)):
            for reason in check(replies, cap):
                print(f"FAIL {reason}")
                failed = True
    except Exception:
        # An asset or check error must fail closed and never print exception details.
        print("FAIL check-error")
        failed = True
    print(f"{'FAIL' if failed else 'PASS'} npp_reply_template_caps")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
