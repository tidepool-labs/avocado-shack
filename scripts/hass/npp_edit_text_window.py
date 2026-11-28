#!/usr/bin/env python3
"""Replay two synthetic NPP edits against the request text window, offline."""

import argparse
import ast
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hass import npp
from hass.npp import job, reply
from hass.skills import openreq

LISTING = {
    "name": "Wildflower Honey", "category": "pantry", "kind": "food",
    "sellingPrice": "4.00", "priceUnit": "each", "maker": None,
    "makerKey": None, "newMaker": False, "town": "", "url": "", "facts": [],
    "photo": "ab" * 32, "personOrScreen": False, "size": None, "labelWords": [],
}


def request_turns(path):
    """Read the literal cap at Jobs.input's requests.put; don't guess a default."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    caps = []
    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef) or cls.name != "Jobs":
            continue
        for method in cls.body:
            if not isinstance(method, ast.FunctionDef) or method.name != "input":
                continue
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                put = node.func
                if not isinstance(put, ast.Attribute) or put.attr != "put":
                    continue
                receiver = put.value
                if ((isinstance(receiver, ast.Attribute) and receiver.attr == "requests")
                        or (isinstance(receiver, ast.Name) and receiver.id == "requests")):
                    caps.extend(kw.value for kw in node.keywords if kw.arg == "turns")
    if len(caps) == 1 and isinstance(caps[0], ast.Constant):
        value = caps[0].value
        if type(value) is int and value > 0:
            return value
    return None


def replay(stages, history, seen, turns):
    stored = openreq.bound_texts([*history, "call it Sage Honey"], turns=turns)
    work = job.Work(
        "abcd",
        {"texts": stored, "slots": {"intake": {
            "price": "4.00", "sold_by": "item", "price_span": [17, 19], "private": [],
        }}, "attachments": [LISTING["photo"]]},
        {"listing_json": json.dumps({**LISTING, reply.SEEN: seen})},
        None,
    )
    plan = stages.edit(work)
    if plan.questions:
        outcome = plan.questions[0][0]
        # Only a pinned question/reply ID belongs on stdout, never its sentence.
        if outcome not in stages.replies["questions"] and outcome not in stages.replies["edits"]:
            raise ValueError("unexpected question ID")
    elif plan.patch is not None or plan.listing is not None:
        outcome = "patch"
    else:
        raise ValueError("missing edit outcome")
    return outcome, plan.listing is not None and plan.listing.get("name") == "Sage Honey"


def finish(findings):
    for reason in dict.fromkeys(findings):
        print(f"FAIL {reason}")
    print("FAIL npp_edit_text_window" if findings else "PASS npp_edit_text_window")
    return int(bool(findings))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    parser.parse_args(args)
    if args:  # No options, not even an argument separator.
        parser.error("no arguments accepted")

    try:
        turns = request_turns(Path(job.__file__))
    except (OSError, ValueError, SyntaxError):
        turns = None
    if turns is None:
        return finish(["turns-unread"])
    print(f"window turns={turns} total={openreq.MAX_TOTAL_TEXT}")

    try:
        stages = reply.Stages(npp.assets(), start=lambda w: None, render=lambda w, l: None, mapper=None)
    except Exception:
        return finish(["check-error"])

    caption = "Wildflower honey $4 each"
    cases = (
        ("ninth", [caption] + ["call it Clover Honey %d" % i for i in range(1, 8)], 8, "ninth-text-lost"),
        ("after_long", [caption, "x" * 3990, "y" * 3990], 3, "long-text-shift"),
    )
    findings = []
    for label, history, seen, reason in cases:
        try:
            outcome, ok = replay(stages, history, seen, turns)
        except Exception:
            findings.append("check-error")
        else:
            print(f"edit {label}={outcome}")
            if not ok:
                findings.append(reason)
    return finish(findings)


if __name__ == "__main__":
    sys.exit(main())
