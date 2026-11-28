#!/usr/bin/env python3
"""Check how S3 and S10 read synthetic maker-and-town captions offline."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import claims, npp
from hass.npp import edits, missing, private_numbers, stages


CAPTIONS = (
    "made by Etto Farm, based in Arroyo Grande",
    "made by Etto Farm; based in Arroyo Grande",
    "made by Etto Farm based in Arroyo Grande",
    "made by Etto Farm in Arroyo Grande",
    "made by Etto Farm from Arroyo Grande",
    "made by Etto Farm. They're based in Arroyo Grande",
    "made by Etto Farm, town: Arroyo Grande",
    "made by Etto Farm\nbased in Arroyo Grande",
    "made by Etto Farm, Arroyo Grande",
    "made by Etto Farm of Arroyo Grande",
)
MAKER = "Etto Farm"
TOWN = "Arroyo Grande"


def _match(value, expected):
    return "exact" if claims.fold(value) == claims.fold(expected) else "other"


def _check(grammar, caption):
    words = private_numbers.finance(caption).public_words
    maker = missing._owner_maker([words], "Honey")
    s3_maker = "none" if maker is None else _match(maker, MAKER)
    s3_town = maker is not None and stages._site_words(maker, [words])[0] == TOWN

    patch = dict(edits.read(grammar, words, {}).patch)
    s10_maker = _match(patch["maker"], MAKER) if "maker" in patch else "ask"
    s10_town = _match(patch["makerTown"], TOWN) if "makerTown" in patch else "none"
    return s3_maker, "yes" if s3_town else "no", s10_maker, s10_town


def main(argv=None):
    argparse.ArgumentParser(add_help=False).parse_args(argv)
    failed = False
    try:
        grammar = edits.Grammar(npp.assets()[1])
    except Exception:
        print("FAIL check-error")
        failed = True
    else:
        for number, caption in enumerate(CAPTIONS, 1):
            try:
                s3_maker, s3_town, s10_maker, s10_town = _check(grammar, caption)
            except Exception:
                # A failed caption cannot be classified; don't expose exception text.
                print("FAIL check-error")
                failed = True
                continue
            print(f"caption {number:02d} s3-maker={s3_maker} s3-town={s3_town} "
                  f"s10-maker={s10_maker} s10-town={s10_town}")
            for field, finding in (
                ("s3-maker", s3_maker != "exact"),
                ("s10-maker", s10_maker == "other"),
                ("s10-town", s10_town == "other"),
            ):
                if finding:
                    print(f"FAIL {field} {number:02d}")
                    failed = True
    print(f"{'FAIL' if failed else 'PASS'} npp_maker_town_caption")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
