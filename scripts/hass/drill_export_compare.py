#!/usr/bin/env python3
"""Compare two transcript JSONL exports without displaying their contents."""

import argparse
import hashlib
import json
from pathlib import Path


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default message can echo unrecognized arguments verbatim.
        super().error("invalid arguments; use --help for usage")


def reject_constant(_token):
    raise ValueError("not a JSON constant")


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def read_export(path, label):
    lines = []
    bad_line = None
    try:
        if not path.is_file():
            return lines, f"no-file {label}"
        with path.open("rb") as source:
            for number, raw in enumerate(source, 1):
                if not raw.strip():
                    continue
                try:
                    obj = json.loads(raw.decode("utf-8"), parse_constant=reject_constant,
                                     object_pairs_hook=unique_object)
                    if not isinstance(obj, dict):
                        raise ValueError("not a JSON object")
                    lines.append(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                            ensure_ascii=True))
                except (ValueError, RecursionError):
                    if bad_line is None:
                        bad_line = number
    except (OSError, ValueError):
        # Never include a filename or exception text in diagnostics.
        return [], f"no-file {label}"
    return lines, f"bad-line {label} {bad_line}" if bad_line is not None else None


def main(argv=None):
    parser = PrivateArgumentParser(prog="drill_export_compare.py", description=__doc__)
    parser.add_argument("--backup-export", required=True, type=Path, metavar="FILE")
    parser.add_argument("--restored-export", required=True, type=Path, metavar="FILE")
    args = parser.parse_args(argv)

    backup, backup_error = read_export(args.backup_export, "backup")
    restored, restored_error = read_export(args.restored_export, "restored")
    print(f"count backup {len(backup)}")
    print(f"count restored {len(restored)}")
    findings = [reason for reason in (backup_error, restored_error) if reason]
    # An incomplete or invalid export cannot support an equality comparison.
    if not findings:
        if not backup and not restored:
            findings.append("empty")
        elif len(backup) != len(restored):
            findings.append("count-mismatch")
        else:
            for number, (left, right) in enumerate(zip(backup, restored), 1):
                if left != right:
                    findings.append(f"first-diff {number}")
                    break

    if findings:
        for reason in findings:
            print(f"FAIL {reason}")
        print("FAIL drill_export_compare")
        return 1
    digest = hashlib.sha256("\n".join(backup).encode("ascii")).hexdigest()
    print(f"digest {digest[:12]}")
    print("PASS drill_export_compare")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
