#!/usr/bin/env python3
"""Check how operation argument names read in a Hass follow-up question."""

import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import field_words, ops, voice  # noqa: E402


PRINTABLE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,40}")
REPORT = "field_words_voice_check"


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        registry = ops.load_registry()
    except Exception:
        print("FAIL registry-error")
        print(f"FAIL {REPORT}")
        return 1

    required = {}
    for op in registry.values():
        for name, arg in op.args.items():
            required[name] = required.get(name, False) or arg.required

    worded = len(required.keys() & field_words.FIELD_WORDS.keys())
    odd_names = {name for name in required if not PRINTABLE_NAME.fullmatch(name)}
    print(f"args {len(required)}")
    print(f"worded {worded}")
    print(f"unworded {len(required) - worded}")
    for key in sorted(field_words.FIELD_WORDS.keys() - required.keys()):
        printable_key = key if PRINTABLE_NAME.fullmatch(key) else "[redacted]"
        print(f"note unused-entry {printable_key}")
    print(f"note odd-name {len(odd_names)}")

    failed = False
    for name in sorted(required):
        q = f"Please provide {field_words.field_list([name])}."
        if voice.check(q):
            failed = True
            if name in odd_names:
                print("FAIL voice-name-invalid")
            else:
                kind = "required" if required[name] else "optional"
                print(f"FAIL voice {name} {kind}")

    print(f"{'FAIL' if failed else 'PASS'} {REPORT}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
