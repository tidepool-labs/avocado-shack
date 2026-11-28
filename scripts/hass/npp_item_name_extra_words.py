#!/usr/bin/env python3
"""Report extra words and punctuation kept in S3 item names, offline."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp
from hass.npp import job, missing


TEXTS = (
    "It's honey",
    "It's honey.",
    "It's honey!",
    "it's a jar of honey",
    "It's honey from Miners",
    "The item is wildflower honey",
    "it is apple butter",
)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    if list(argv) == ["--"]:  # Reject a bare marker consistently across Python versions.
        parser.error("no arguments accepted")
    parser.parse_args(argv)

    failed = False

    def finding(reason):
        nonlocal failed
        failed = True
        print(f"FAIL {reason}")

    try:
        mi = missing.MissingInfo(hass.npp.assets())
        for i, text in enumerate(TEXTS):
            item = mi.decide({}, owner_item=job.owner_item(text)).item
            print(f"case {i} item={item}")
            if not item:
                finding(f"no-item {i}")
                continue
            words = item.casefold().split()
            if item.endswith((".", "!", "?")):
                finding(f"trailing-punctuation {i}")
            if words and words[0] in {"a", "an", "the"}:
                finding(f"article-kept {i}")
            if "from" in words:
                finding(f"from-kept {i}")
    except Exception:
        finding("check-error")

    print("FAIL npp_item_name_extra_words" if failed else "PASS npp_item_name_extra_words")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
