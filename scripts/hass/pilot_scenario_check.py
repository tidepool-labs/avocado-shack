#!/usr/bin/env python3
"""Check the listing-specific expectations in one offline pilot receipt."""

from datetime import datetime
import json
from pathlib import Path
import re
import sys


PRICE_QUESTIONS = ("ask_price", "ask_price_unit")
# Keys from hass/npp/assets/hass-npp-reply/reply-templates.json.
QUESTION_IDS = (*PRICE_QUESTIONS, "ask_identity", "ask_unit", "ask_near_maker",
                "ask_edit_source", "ask_edit_unclear")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def reject_constant(_token):
    raise ValueError


def matches(value, spec):
    """Validate the wire shape separately from the scenario rules."""
    if isinstance(spec, dict):
        return (isinstance(value, dict) and value.keys() == spec.keys()
                and all(matches(value[key], rule) for key, rule in spec.items()))
    if isinstance(spec, list):
        return isinstance(value, list) and all(matches(item, spec[0]) for item in value)
    if isinstance(spec, tuple):
        return value in spec
    if spec is None:
        return value is None
    if isinstance(spec, type):
        return type(value) is spec
    return spec(value)


def nullable(spec):
    return lambda value: value is None or matches(value, spec)


def hex_digest(length):
    pattern = re.compile(rf"[0-9a-fA-F]{{{length}}}")
    return lambda value: isinstance(value, str) and pattern.fullmatch(value) is not None


def timestamp(value, *, offset=False):
    if not isinstance(value, str) or len(value) < 12:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return not offset or parsed.utcoffset() is not None


SHA256 = hex_digest(64)
DRAFT = {"version": int, "draft_hash": SHA256, "change_id": str, "base": str}
REPLY = {
    "outbox_id": int,
    "kind": ("question", "card", "guard", "posted", "other"),
    "question_id": nullable(QUESTION_IDS),
    "version": nullable(int),
    "card_png_sha256": nullable(SHA256),
    "delivery": {
        "state": ("confirmed", "pending", "unconfirmed", "failed", "untracked"),
        "png_sha256": nullable(SHA256),
        "confirmed_at": nullable(timestamp),
    },
}
RECEIPT = {
    "schema": ("hass-pilot-receipt/1",),
    "listing": lambda value: type(value) is int and value in (1, 2, 3),
    "segments": [{"inbound_id": str, "received_at": lambda value: timestamp(value, offset=True),
                  "replies": [REPLY]}],
    "versions": [{**DRAFT, "photo_sha256": SHA256, "card_png_sha256": SHA256}],
    "approval": nullable({**DRAFT, "inbound_id": str, "accepted_at": timestamp}),
    "publish": nullable({"change_id": str, "commit": hex_digest(40), "live_verified": bool}),
    "privacy": dict.fromkeys(("text", "dom", "picture"), ("pass", "fail")),
    "provenance": ("sourced", "omitted", "unsourced"),
    "stops": [str],
    "elapsed_seconds": int,
}


def scenario_failures(receipt):
    segments = [segment["replies"] for segment in receipt["segments"]]
    first = segments[0] if segments else []
    replies = [reply for segment in segments for reply in segment]
    versions = receipt["versions"]
    listing = receipt["listing"]

    if listing == 1:
        if any(reply["kind"] == "question" for reply in replies):
            yield "listing-1-question"
        if len(versions) != 1:
            yield "listing-1-version-count"
    elif listing == 2:
        asked = {reply["question_id"] for reply in first
                 if reply["kind"] == "question" and reply["question_id"] in PRICE_QUESTIONS}
        if len(first) != 1 or not asked:
            yield "listing-2-initial-price-question"
        if not any(sum(reply["kind"] == "card" for reply in segment) == 1
                   for segment in segments[1:]):
            yield "listing-2-later-card"
        if any(reply["question_id"] in asked for segment in segments[1:] for reply in segment):
            yield "listing-2-repeated-price-question"
    else:
        if any(reply["kind"] == "question" for reply in first):
            yield "listing-3-initial-question"
        version_numbers = {version["version"] for version in versions}
        # Bind delivery to the version and card bytes, without checking timing or ordering.
        confirmed_cards = set()
        for reply in replies:
            delivery = reply["delivery"]
            card_digest = reply["card_png_sha256"]
            sent_digest = delivery["png_sha256"]
            if (reply["kind"] == "card" and delivery["state"] == "confirmed"
                    and card_digest is not None and sent_digest is not None
                    and card_digest.lower() == sent_digest.lower()):
                confirmed_cards.add((reply["version"], card_digest.lower()))
        delivered = {version["version"] for version in versions
                     if (version["version"], version["card_png_sha256"].lower()) in confirmed_cards}
        for number in (1, 2):
            if number not in delivered:
                yield f"listing-3-v{number}-delivered-card"
        if {1, 2} <= version_numbers:
            photos = {version["photo_sha256"].lower() for version in versions
                      if version["version"] in (1, 2)}
            if len(photos) != 1:
                yield "listing-3-photo-changed"
        publish = receipt["publish"]
        if publish is not None and any(version["version"] == 1
                                       and version["change_id"] == publish["change_id"]
                                       for version in versions):
            yield "listing-3-v1-published"
        approval = receipt["approval"]
        if approval is None or approval["version"] != 2:
            yield "listing-3-v2-approval"


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args in (["--help"], ["-h"]):
        print("usage: pilot_scenario_check.py RECEIPT.json")
        return 0
    if len(args) != 1:
        print("FAIL usage")
        return 2
    try:
        with Path(args[0]).open(encoding="utf-8") as source:
            receipt = json.load(source, object_pairs_hook=unique_object,
                                parse_constant=reject_constant)
        if not matches(receipt, RECEIPT):
            raise ValueError
    except (OSError, ValueError, RecursionError):
        print("FAIL malformed-receipt")
        return 2
    reasons = list(scenario_failures(receipt))
    for reason in reasons:
        print(f"FAIL {reason}")
    if reasons:
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
