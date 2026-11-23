#!/usr/bin/env python3
"""Report interpreter prompt size and omissions from an offline content copy."""

import argparse
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import interpreter_prompt  # noqa: E402
from hass.content_model import load_and_validate  # noqa: E402
from hass.ops import load_registry  # noqa: E402


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse can echo unrecognized arguments and rejected values verbatim.
        super().error("invalid arguments; see --help")


def _nonnegative_int(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("expected a non-negative integer")
    return number


def _fail(reason):
    print(f"FAIL {reason}")
    print("FAIL prompt_size_report")
    return 1


def main(argv=None):
    parser = _Parser(description=__doc__, prog="prompt_size_report.py", allow_abbrev=False)
    parser.add_argument("--content", required=True, type=Path, metavar="DIR",
                        help="directory containing a copy of the content JSON files")
    parser.add_argument("--max-omitted", type=_nonnegative_int, metavar="N",
                        help="fail if more than N prompt fields are omitted")
    args = parser.parse_args(argv)

    try:
        if not stat.S_ISDIR(args.content.lstat().st_mode):
            return _fail("unsafe-input")
    except (OSError, ValueError):
        return _fail("unsafe-input")

    try:
        content = load_and_validate(args.content, None)
    except (OSError, ValueError, RecursionError):  # includes ContentError and decoding errors
        return _fail("content-invalid")

    try:
        prompt = interpreter_prompt.build(load_registry(), content)
        size = len(prompt.encode("utf-8"))
        lines = prompt.splitlines()
    except Exception:
        return _fail("build-error")

    maximum = interpreter_prompt.PROMPT_MAX_BYTES
    omitted = sum(field.strip() == interpreter_prompt.OMITTED
                  for line in lines if " | " in line for field in line.split(" | "))
    print(f"bytes {size}")
    print(f"max {maximum}")
    print(f"headroom {maximum - size}")
    print(f"lines {len(lines)}")
    print(f"products {len(content.products)}")
    print(f"makers {len(content.makers)}")
    print(f"omitted {omitted}")

    failed = False
    if size > maximum:
        print(f"FAIL over-max {size}")
        failed = True
    if args.max_omitted is not None and omitted > args.max_omitted:
        print(f"FAIL omitted-over {omitted}")
        failed = True
    print("FAIL prompt_size_report" if failed else "PASS prompt_size_report")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
