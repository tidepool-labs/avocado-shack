#!/usr/bin/env python3
"""Check rollback config bytes without changing files or service state."""

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat
import sys


LIMIT = "Byte check only; does not prove off-state or service health."


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse can echo a mistyped value; never include user input in errors.
        self.print_usage(sys.stderr)
        self.exit(2, f"Invalid arguments; see --help.\n{LIMIT}\n")


def sha256_and_identity(path):
    # Open each component relative to its already-open parent. No component
    # may be a symlink, even if it points to a file with the expected bytes.
    parts = path.parts
    if not parts or parts == (path.anchor,):
        raise ValueError
    directories = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent = os.open(path.anchor or ".", directories)
    try:
        for part in parts[bool(path.anchor):-1]:
            child = os.open(part, directories, dir_fd=parent)
            os.close(parent)
            parent = child
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        with os.fdopen(os.open(parts[-1], flags, dir_fd=parent), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise ValueError
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
            return digest.hexdigest(), (opened.st_dev, opened.st_ino)
    finally:
        os.close(parent)


def main():
    parser = Parser(description=__doc__, epilog=LIMIT)
    commands = parser.add_subparsers(dest="command", required=True)
    pre = commands.add_parser("pre", help="check for drift before restore", epilog=LIMIT)
    pre.add_argument("--current", required=True, type=Path)
    pre.add_argument("--candidate-sha", required=True, metavar="HEX64")
    post = commands.add_parser("post", help="check the backup and restored bytes", epilog=LIMIT)
    post.add_argument("--restored", required=True, type=Path)
    post.add_argument("--backup", required=True, type=Path)
    post.add_argument("--original-sha", required=True, metavar="HEX64")
    args = parser.parse_args()

    if args.command == "pre":
        expected = args.candidate_sha
        inputs = [("current", args.current)]
        success = "current bytes match the recorded candidate digest"
    else:
        expected = args.original_sha
        inputs = [("backup", args.backup), ("restored", args.restored)]
        success = "backup and restored bytes both match the recorded original digest"

    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        print(f"FAIL {args.command}: expected a 64-digit hexadecimal SHA-256 digest.\n{LIMIT}",
              file=sys.stderr)
        return 2
    backup_identity = None
    for role, path in inputs:
        try:
            actual, identity = sha256_and_identity(path)
        except (OSError, ValueError):
            print(f"FAIL {args.command}: cannot read {role} as a regular file without symlinks.\n{LIMIT}",
                  file=sys.stderr)
            return 1
        if actual != expected.lower():
            print(f"FAIL {args.command}: {role} digest mismatch.\n{LIMIT}", file=sys.stderr)
            return 1
        if role == "backup":
            backup_identity = identity
        elif role == "restored" and identity == backup_identity:
            print(f"FAIL post: backup and restored must be distinct files.\n{LIMIT}", file=sys.stderr)
            return 1
    print(f"PASS {args.command}: {success}.\n{LIMIT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
