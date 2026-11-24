#!/usr/bin/env python3
"""Check a saved Hass acceptance receipt without running acceptance.

Usage: python3 -B scripts/hass/install_acceptance_receipt.py --stdout FILE
       --metadata FILE --expected-runtime-sha SHA [--require-full-roster]

Metadata is a UTF-8 JSON object with stdout_sha256 (64 hex characters over
unmodified stdout bytes), runtime_sha (full 40-hex Git commit), and exit_status
(integer). Supply the expected commit independently of that file. By default,
selected runs can pass the consistency check if every ID is one the producer
can emit. With --require-full-roster, the
rows must match the producer's complete ID roster, including not-covered rows.
Neither mode authenticates the capture or proves how it was produced or what is
deployed. Keep the original capture private.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import TypeGuard


class ReceiptError(ValueError):
    """An invalid receipt; messages must not contain captured values."""


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def _invalid_constant(_value):
    raise ValueError("non-JSON constant")


def _object(data, label):
    try:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        obj = json.loads(data, object_pairs_hook=_unique_object,
                         parse_constant=_invalid_constant)
    except (ValueError, RecursionError):
        raise ReceiptError(f"invalid JSON in {label}") from None
    if not isinstance(obj, dict):
        raise ReceiptError(f"expected a JSON object in {label}")
    return obj


def _hex(value: object, length: int) -> TypeGuard[str]:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{%d}" % length, value) is not None


def validate(stdout: bytes, metadata: bytes, expected_runtime_sha: str, *,
             require_full_roster: bool = False) -> dict:
    """Return counts and uncovered IDs, or raise a redacted ReceiptError."""
    if not _hex(expected_runtime_sha, 40):
        raise ReceiptError("expected runtime SHA must be a full 40-hex Git commit")
    capture = _object(metadata, "metadata")
    runtime_sha = capture.get("runtime_sha")
    if not _hex(runtime_sha, 40) or runtime_sha.lower() != expected_runtime_sha.lower():
        raise ReceiptError("capture runtime SHA does not match the expected full SHA")
    digest = capture.get("stdout_sha256")
    if not _hex(digest, 64) or digest.lower() != hashlib.sha256(stdout).hexdigest():
        raise ReceiptError("capture stdout SHA-256 does not match the saved bytes")
    exit_status = capture.get("exit_status")
    if type(exit_status) is not int or exit_status != 0:
        raise ReceiptError("capture exit_status must be integer zero")

    try:
        # Only LF delimits records; splitlines() also recognizes non-JSON separators.
        lines = stdout.decode("utf-8").removesuffix("\n").split("\n")
    except UnicodeDecodeError:
        raise ReceiptError("saved stdout is not UTF-8") from None
    final = _object(lines[-1], "final stdout line")
    summary = final.get("summary")
    counts = {"ids": 0, "pass": 0, "fail": 0, "not covered": 0}
    if (set(final) != {"summary"} or not isinstance(summary, dict)
            or summary.keys() != counts.keys()
            or any(type(n) is not int or n < 0 for n in summary.values())):
        raise ReceiptError("final stdout line must contain the integer summary counts")
    if summary["fail"] != 0:
        raise ReceiptError("final summary.fail must be integer zero")

    seen, not_covered = set(), []
    for number, line in enumerate(lines[:-1], 1):
        label = f"stdout row {number}"
        row = _object(line, label)
        ident, result = row.get("id"), row.get("result")
        tests, failures = row.get("tests"), row.get("failures")
        if ("summary" in row or not isinstance(ident, str)
                or not re.fullmatch(r"H[0-9]{2}", ident) or ident in seen):
            raise ReceiptError(f"missing, invalid, or duplicate H ID in {label}")
        if (result not in ("pass", "not covered") or type(failures) is not int
                or failures != 0 or type(tests) is not int
                or (tests <= 0 if result == "pass" else tests != 0)):
            raise ReceiptError(f"invalid or failing result in {label}")
        seen.add(ident)
        counts["ids"] += 1
        counts[result] += 1
        if result == "not covered":
            not_covered.append(ident)
    if not seen or counts != summary:
        raise ReceiptError("summary counts do not match a nonempty set of stdout rows")
    result = {"summary": counts, "not_covered_ids": not_covered}
    from hass.acceptance import ALL_IDS

    if require_full_roster:
        if seen != set(ALL_IDS):
            raise ReceiptError("saved rows do not match the full producer H ID roster")
        result["full_roster"] = True
    elif not seen <= set(ALL_IDS):
        raise ReceiptError("saved rows cite an H ID outside the producer roster")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check a saved Hass acceptance receipt.",
                                     epilog="Does not authenticate the capture or prove how it was produced.")
    parser.add_argument("--stdout", required=True, type=Path, help="saved acceptance stdout")
    parser.add_argument("--metadata", required=True, type=Path,
                        help="JSON with stdout_sha256, runtime_sha, and exit_status")
    parser.add_argument("--expected-runtime-sha", required=True,
                        help="independently obtained full runtime commit SHA")
    parser.add_argument("--require-full-roster", action="store_true",
                        help="require exactly the producer's full set of H IDs, including not-covered rows")
    args = parser.parse_args(argv)
    try:
        result = validate(args.stdout.read_bytes(), args.metadata.read_bytes(),
                          args.expected_runtime_sha, require_full_roster=args.require_full_roster)
    except (OSError, ValueError) as exc:
        reason = str(exc) if isinstance(exc, ReceiptError) else "cannot read capture inputs"
        print(f"Receipt refused: {reason}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "consistent (capture not authenticated)", **result}))
    return 0


if __name__ == "__main__":
    # Direct file invocation starts with scripts/hass, not the checkout root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.exit(main())
