#!/usr/bin/env python3
"""Check S5's serialized selector request with synthetic listings and no network."""

import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp
from hass.npp import copy


NAME = "npp_selector_body_privacy"
NEEDLES = ("quillberry", "zorbel", "vexmoor", "plonkwise", "913.47", "8642",
           "17 oz", "1987", "glimmerwick")
OPTIONS_KEYS = {"kind", "category", "templates", "phrase_ids", "fact_ids"}


def cases():
    owner_words = ("add quillberry jam made by Zorbel Farm in Vexmoor, "
                   "17 oz jar, 913.47 each, I have 8642 plonkwise")
    private = frozenset({Decimal("913.47"), Decimal("8642")})
    jam = ("food", "pantry", "raw", "Quillberry Jam", owner_words)
    label = "ZORBEL FARM QUILLBERRY JAM 17 oz"
    facts = (
        copy.Fact("official-makes", "makes", "jam", "https://zorbel.example/",
                  "Zorbel Farm makes jam.", "supports"),
        copy.Fact("official-founded", "founded", "1987", "https://zorbel.example/",
                  "Zorbel Farm was founded in 1987.", "supports"),
    )
    return (
        ("A", copy.Context(*jam, maker_name="Zorbel Farm", town="Vexmoor",
                           size_text="17 oz", source_read=label, facts=facts, private=private)),
        ("B", copy.Context(*jam, brand="Zorbel Farm", size_text="17 oz",
                           source_read=label, private=private)),
        ("C", copy.Context("non-food", "general", "house", "Glimmerwick Candle",
                           "new glimmerwick candle 913.47 each plonkwise", private=private)),
    )


def unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate JSON key")
    return result


def reject_constant(_token):
    raise ValueError("non-JSON constant")


def valid_options(body):
    if not isinstance(body, bytes):
        return False
    try:
        request = json.loads(body.decode("utf-8"), object_pairs_hook=unique_object,
                             parse_constant=reject_constant)
        content = request["messages"][0]["content"]
        if not isinstance(content, str):
            return False
        _, marker, payload = content.rpartition("\nEligible IDs: ")
        if not marker:
            return False
        options = json.loads(payload, object_pairs_hook=unique_object,
                             parse_constant=reject_constant)
    except (ValueError, KeyError, IndexError, TypeError, RecursionError):
        return False
    return (isinstance(options, dict) and options.keys() == OPTIONS_KEYS
            and isinstance(options["fact_ids"], dict)
            and all(isinstance(ref, str) and re.fullmatch(r"official-[a-z]+", ref)
                    for ref in options["fact_ids"].values()))


def check():
    try:
        writer = copy.Writer(hass.npp.assets())
    except Exception:
        return ["check-error"]

    findings = []
    for case, ctx in cases():
        bodies = []

        def fake(url, body, headers, timeout):
            bodies.append(body)
            return 500, b""

        try:
            select = copy.codex_selector(transport=fake)
            writer.write(ctx, select)
        except Exception:
            if "check-error" not in findings:
                findings.append("check-error")

        print(f"case {case} requests={len(bodies)}")
        if not bodies:
            findings.append(f"no-request {case}")
            continue
        texts = [body.decode("utf-8", errors="replace").casefold()
                 for body in bodies if isinstance(body, bytes)]
        for index, needle in enumerate(NEEDLES):
            if any(needle in text for text in texts):
                findings.append(f"value-in-body {case} {index}")
        if not all(valid_options(body) for body in bodies):
            findings.append(f"options-shape {case}")
    return findings


def main(argv=None):
    # Even --help is an argument and must be refused for this fixed check.
    parser = argparse.ArgumentParser(prog=NAME, description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    parser.parse_args(args)
    if args:  # argparse can accept a lone end-of-options marker.
        parser.error("no arguments accepted")
    findings = check()
    for finding in findings:
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} {NAME}")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
