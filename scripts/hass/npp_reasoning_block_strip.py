#!/usr/bin/env python3
"""Check the local interpreter drops a reasoning block only when it wholly precedes the answer.

HASS-INTERP-OPENAI-1: `interpreter_local.strip_reasoning` drops the text up to the last `</think>` and refuses
(`_Failed`) any other tag shape, so stray reasoning is never read as a listing operation. Offline and read-only:
it calls only that pure function on the fixed replies in CASES.
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import interpreter_local


CASES = [
    '<think>plan</think>{"op": "product.add"}',
    'plan</think>{"op": "product.add"}',
    '<think>a</think><think>b</think>{"op": "x"}',
    '{"op": "x"}<think>late</think>',
    '<think>unclosed {"op": "x"}',
    '<think>a</think>between<think>b</think>{"op": "x"}',
    '{"op": "x"}',
    '<think><think>a</think>{"op": "x"}',
    'a</think>b</think>{"op": "x"}',
    '{"op": "x"}</think>',
    '{"op": "x"} </think> <think>',
]
MUST_REFUSE = (3, 4, 5, 7, 8, 10)
# The informational lines measured at c8cdcc95 (case 9 gives the empty string).
EXPECTED = [
    """case 0 answer=ok:'{"op": "product.add"}'""",
    """case 1 answer=ok:'{"op": "product.add"}'""",
    """case 2 answer=ok:'{"op": "x"}'""",
    "case 3 answer=refused",
    "case 4 answer=refused",
    "case 5 answer=refused",
    """case 6 answer=ok:'{"op": "x"}'""",
    "case 7 answer=refused",
    "case 8 answer=refused",
    "case 9 answer=ok:''",
    "case 10 answer=refused",
]
NAME = "npp_reasoning_block_strip"


def fail(reason):
    print(f"FAIL {reason}")


def main(argv=None):
    # No options at all (not even -h): any argument is argparse's own exit 2, with nothing on stdout.
    argparse.ArgumentParser(description=__doc__, allow_abbrev=False, add_help=False).parse_args(argv)
    findings = 0
    try:
        for index, text in enumerate(CASES):
            try:
                line = f"case {index} answer=ok:{interpreter_local.strip_reasoning(text)!r}"
            except interpreter_local._Failed:
                line = f"case {index} answer=refused"
            print(line)
            if index in MUST_REFUSE and line != f"case {index} answer=refused":
                fail(f"reasoning-left-in-answer {index}")
                findings += 1
            if line != EXPECTED[index]:
                fail(f"answer-changed {index}")
                findings += 1
    except Exception:  # noqa: BLE001 - a check that cannot complete is a named FAIL, never a traceback
        fail("check-error")
        findings += 1
    if findings:
        print(f"FAIL {NAME}")
        return 1
    print(f"PASS {NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
