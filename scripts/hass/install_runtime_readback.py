#!/usr/bin/env python3
"""Check the consistency of one saved, post-release Hass capture (JSON on stdin).

Usage: install_runtime_readback.py --target FULL_SHA --runtime ABSOLUTE_ROOT
       [--expected-old FULL_SHA] < capture.json

Save one JSON object from the same attended run. Required fields:
  release: {exit_code, output}  Command exit status and complete combined transcript.
  receipt: {phase, target, runtime, old (when bound)}  From the final release receipt.
  checkout: {root, head, status: {exit_code, stdout}}  Observed top-level and HEAD,
    plus unmodified porcelain status including untracked files.
  running_pin: full SHA from a separate post-release observation; do not copy
    it from the selection, receipt or checkout. Do not include private config.
  units: map keyed by hass-receiver.service, hass-worker.service, hass-health.timer.
    Each value has {exit_code, state} from the active-state check. Both services
    also need restarts: {exit_code, count} from the restart-counter read.
  health: {exit_code, summary}  From the post-release live self-test (not a
    synthetic-only run); summary is its final HASS-SELFTEST line.

Supply the expected SHA and canonical runtime path from the install selection,
not from the capture. To bind both ends of a move, supply --expected-old from
the independently recorded pre-move pin. Without it, receipt.old is not checked.
Keep the capture private. This checks saved observations, not their authenticity,
freshness, or what a process actually loaded.
"""

import argparse
import json
from pathlib import PurePosixPath
import re
import sys


MAX_CAPTURE = 65_536
UNITS = ("hass-receiver.service", "hass-worker.service", "hass-health.timer")
HEALTH_SUMMARY = re.compile(r"HASS-SELFTEST \S+ pass=[1-9][0-9]* warn=[0-9]+ fail=0 skip=[0-9]+")


class ReadbackParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "REFUSED: expected --target and --runtime; see --help\n")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def object_at(parent, key):
    value = parent.get(key)
    return value if isinstance(value, dict) else {}


def is_zero(value):
    return type(value) is int and value == 0


def refusal(capture, target, runtime, expected_old=None):
    """Return a fixed refusal reason, or None; never echo capture values."""
    release = object_at(capture, "release")
    if not is_zero(release.get("exit_code")):
        return "release exit status must be zero"
    output = release.get("output")
    # The producer emits only these phase lines on a successful apply. Do not
    # let a later success-looking line mask a refusal/rollback or another run.
    lines = []
    if isinstance(output, str):
        lines = output.replace("\r\n", "\n").removesuffix("\n").split("\n")
    if lines not in (
        ["RELEASE released"],
        ["RELEASE prepared", "RELEASE switching", "RELEASE released"],
    ):
        return "release transcript does not end in an uncontradicted RELEASE released"

    receipt = object_at(capture, "receipt")
    if receipt.get("phase") != "released":
        return "receipt phase is not released"
    if receipt.get("target") != target or receipt.get("runtime") != runtime:
        return "receipt target or runtime does not match selection"
    if expected_old is not None:
        if expected_old == target:
            return "old and target pins are identical; not a move"
        if receipt.get("old") != expected_old:
            return "receipt old pin missing or does not match pre-move selection"

    checkout = object_at(capture, "checkout")
    if checkout.get("root") != runtime:
        return "checkout root does not match selection"
    if checkout.get("head") != target:
        return "checkout HEAD does not match selection"
    status = object_at(checkout, "status")
    if not is_zero(status.get("exit_code")) or status.get("stdout") != "":
        return "checkout status missing, failed, or dirty"
    if capture.get("running_pin") != target:
        return "independent running pin missing or does not match selection"

    units = object_at(capture, "units")
    for name in UNITS:
        unit = object_at(units, name)
        if not is_zero(unit.get("exit_code")) or unit.get("state") != "active":
            return "missing or non-active unit observation: " + name
        if name.endswith(".service"):
            restarts = object_at(unit, "restarts")
            if not is_zero(restarts.get("exit_code")) or not is_zero(restarts.get("count")):
                return "missing, failed, or nonzero restart count: " + name
    health = object_at(capture, "health")
    summary = health.get("summary")
    if (not is_zero(health.get("exit_code")) or not isinstance(summary, str)
            or not HEALTH_SUMMARY.fullmatch(summary)):
        return "missing or failing health observation"
    return None


def main(argv=None):
    parser = ReadbackParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                            allow_abbrev=False)
    parser.add_argument("--target", required=True, help="selected full lowercase 40-hex commit")
    parser.add_argument("--runtime", required=True, help="expected canonical absolute checkout root")
    parser.add_argument("--expected-old", help="independent pre-move full lowercase 40-hex commit")
    args = parser.parse_args(argv)
    root = PurePosixPath(args.runtime)
    if not re.fullmatch(r"[0-9a-f]{40}", args.target) or not (
        root.root == "/" and str(root) == args.runtime and ".." not in root.parts
    ):
        parser.error("invalid selection")
    if args.expected_old is not None and not re.fullmatch(r"[0-9a-f]{40}", args.expected_old):
        parser.exit(2, "REFUSED: --expected-old must be a full lowercase 40-hex commit\n")

    try:
        text = sys.stdin.read(MAX_CAPTURE + 1)
        capture = json.loads(text, object_pairs_hook=unique_object) if len(text) <= MAX_CAPTURE else None
    except (ValueError, OSError, RecursionError):
        capture = None
    reason = (refusal(capture, args.target, args.runtime, args.expected_old)
              if isinstance(capture, dict) else "invalid capture JSON")
    if reason is not None:
        print("REFUSED: " + reason, file=sys.stderr)
        return 1
    binding = "; receipt old pin matches pre-move selection" if args.expected_old is not None else ""
    print(f"PASS: saved release, checkout, pin and service observations agree{binding} (not process attestation)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
