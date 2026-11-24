#!/usr/bin/env python3
"""Compare S2 and S5 claim decisions offline, reporting counts only."""

import argparse
from collections import Counter
from pathlib import Path
import re
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model, label_reader, product_claims

WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
MAX_BYTES = 32 * 1024
MAX_LINES = 1000
BUCKETS = {
    (True, True): "both",
    (True, False): "s2-only",
    (False, True): "s5-only",
    (False, False): "neither",
}


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's detail can include arbitrary argument values (e.g. paths).
        super().error("invalid arguments; use --help for usage")


class InputError(Exception):
    """Carries only a fixed finding reason, never input data."""


def file_words(path):
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            raise InputError("unsafe-input")
    except (FileNotFoundError, NotADirectoryError, ValueError):
        raise InputError("unsafe-input") from None
    except OSError:
        raise InputError("unreadable-input") from None

    try:
        with path.open("rb") as source:
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise InputError("too-large")
        lines = raw.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        raise InputError("unreadable-input") from None
    if len(lines) > MAX_LINES:
        raise InputError("too-many-lines")
    return [word for line in lines if (word := line.strip())]


def content_words(path):
    try:
        if not stat.S_ISDIR(path.lstat().st_mode):
            raise InputError("unsafe-input")
    except (OSError, ValueError):
        raise InputError("unsafe-input") from None
    try:
        content = content_model.load_content(path)
        return sorted({word for product in content.active_products()
                       for word in WORD.findall(product["name"])})
    except Exception:
        raise InputError("content-invalid") from None


def fail(reason):
    print(f"FAIL {reason}")
    print("FAIL claim_word_stage_check")
    return 1


def main(argv=None):
    parser = PrivateArgumentParser(prog="claim_word_stage_check.py", description=__doc__,
                                   allow_abbrev=False)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--words", type=Path, metavar="FILE", help="read a UTF-8 word list")
    source.add_argument("--content", type=Path, metavar="DIR", default=content_model.CONTENT_DIR,
                        help="read active names (the standard directory is hass/content)")
    args = parser.parse_args(argv)

    try:
        words = file_words(args.words) if args.words is not None else content_words(args.content)
    except InputError as error:
        return fail(error)

    counts = Counter()
    try:
        for word in words:
            s2 = bool(label_reader.is_claim(word))
            s5 = product_claims.drop_copy_claims(word, "")[0] != word
            counts[s2, s5] += 1
    except Exception:
        return fail("check-error")

    print(f"words {len(words)}")
    for pair, name in BUCKETS.items():
        print(f"{name} {counts[pair]}")
    disagree = counts[True, False] + counts[False, True]
    if disagree:
        return fail(f"stage-disagree {disagree}")
    print("PASS claim_word_stage_check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
