#!/usr/bin/env python3
"""Check the deterministic photo-caption finance path without showing values.

caption_answers returns a public remainder and answers. This report uses
`price` (selling price), `sold_by` (item/pound), `cost`, and `qty`. A missing
price or unresolved finance in the remainder means ask. Card means only that
caption finance did not block it; no photo, identity, or live checks run here.
"""

import argparse
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.skills import item_intake


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse can echo unexpected arguments, including an input path.
        super().error("invalid arguments; see --help")


def read_captions(path):
    # Refuse symlinks at open; nonblocking also avoids waiting on a named pipe.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, encoding="utf-8") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise OSError("expected a regular file")
        captions = []
        for line in source:
            # Keep at most one extra caption, but check UTF-8 to the end.
            if len(captions) <= 20 and line.strip():
                captions.append(line.rstrip("\n"))
        return captions


def report(index, caption):
    parsed = True
    try:
        public, answers = item_intake.caption_answers(
            caption.replace("\ufffc", ""), {"photo_fields": None}
        )
    except ValueError:
        # A numeric conversion can refuse malformed finance (e.g. a huge count).
        public, answers = caption, {}
        parsed = False
    price = "price" in answers
    unit = {"item": "each", "pound": "per-lb"}.get(answers.get("sold_by", ""), "none")
    ask = not price or item_intake.unresolved_finance(public)
    prefix = f"caption {index}"
    print(f"{prefix} price {'yes' if price else 'no'}")
    print(f"{prefix} unit {unit}")
    print(f"{prefix} cost {'yes' if 'cost' in answers else 'no'}")
    print(f"{prefix} quantity {'yes' if 'qty' in answers else 'no'}")
    print(f"{prefix} path {'ask' if ask else 'card'}")
    # A failed parse doesn't establish that the selling price was omitted.
    return ask, price if parsed else None


def main(argv=None):
    parser = PrivateArgumentParser(
        prog="pilot_caption_precheck", description="Check photo-caption finance offline.", allow_abbrev=False
    )
    parser.add_argument("--captions", required=True, metavar="FILE", help="UTF-8 file, one caption per line")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--expect-card", action="store_true", help="fail for any caption that would ask")
    mode.add_argument("--expect-pilot-sequence", action="store_true",
                      help="require three initial captions: card, ask with no selling price, card")
    args = parser.parse_args(argv)
    try:
        captions = read_captions(args.captions)
    except (OSError, ValueError):
        captions = []

    if args.expect_pilot_sequence:
        print("scope caption finance only")
    failed = True
    if not captions:
        print("FAIL unreadable")
    elif len(captions) > 20:
        print("FAIL too-many")
    elif args.expect_pilot_sequence and len(captions) != 3:
        print("FAIL pilot-caption-count")
    else:
        failed = False
        for index, caption in enumerate(captions, 1):
            ask, price = report(index, caption)
            if args.expect_card and ask:
                print(f"FAIL would-ask {index}")
                failed = True
            if args.expect_pilot_sequence:
                matches = ask and price is False if index == 2 else not ask
                if not matches:
                    print(f"FAIL pilot-sequence {index}")
                    failed = True
    print("FAIL pilot_caption_precheck" if failed else "PASS pilot_caption_precheck")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
