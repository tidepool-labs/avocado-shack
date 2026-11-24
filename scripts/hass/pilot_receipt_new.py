#!/usr/bin/env python3
"""Create a blank pilot receipt in a private directory."""

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import sys


class ReceiptError(ValueError):
    """A refusal whose message is safe to print."""


class ReceiptParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error can repeat private arguments.
        raise ReceiptError("expected --listing N and --out PATH")


def refuse_git_marker(fd):
    # Don't follow or read the marker: a linked worktree keeps it as a file.
    try:
        os.stat(".git", dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise ReceiptError("output must be outside Git worktrees")


def open_parent(path):
    directory = Path(path)
    if ".." in directory.parts:
        raise ReceiptError("output parent must not contain '..'")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        # Walk from the root even for a relative output, so worktree markers
        # above the invocation cwd aren't skipped.
        if not directory.is_absolute():
            directory = Path.cwd() / directory
        fd = os.open(directory.anchor, flags)
        try:
            for part in directory.parts[1:]:
                refuse_git_marker(fd)
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            refuse_git_marker(fd)
            if os.fstat(fd).st_mode & 0o077:
                raise ReceiptError("output parent allows group or other access")
        except (OSError, ValueError):
            os.close(fd)
            raise
    except OSError as error:
        if error.errno in (errno.ENOENT, errno.ENOTDIR, errno.ELOOP):
            raise ReceiptError("output parent must be an existing symlink-free directory") from None
        raise ReceiptError("could not inspect output parent") from None
    return fd


def write_receipt(path, payload):
    parent, name = os.path.split(path)
    if not name or name in (".", "..") or not name.isprintable():
        raise ReceiptError("output path must name a new file with a printable basename")

    # Check permissions and create relative to the same open directory.
    parent_fd = open_parent(parent)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        try:
            fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
        except FileExistsError:
            raise ReceiptError("output already exists (including symlinks)") from None
        except OSError:
            raise ReceiptError("could not create receipt") from None

        try:
            try:
                os.fchmod(fd, 0o600)  # Keep the exact mode even under a restrictive umask.
                remaining = memoryview(payload)
                while remaining:
                    written = os.write(fd, remaining)
                    if not written:
                        raise OSError("short write")
                    remaining = remaining[written:]
            finally:
                os.close(fd)
        except OSError:
            os.unlink(name, dir_fd=parent_fd)
            raise ReceiptError("could not write receipt") from None
    finally:
        os.close(parent_fd)
    return name


def main(argv=None):
    parser = ReceiptParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--listing", required=True, metavar="N", help="listing number (1, 2 or 3)")
    parser.add_argument("--out", required=True, metavar="PATH", help="new private JSON file")
    try:
        args = parser.parse_args(argv)
        if args.listing not in ("1", "2", "3"):
            raise ReceiptError("listing must be 1, 2 or 3")
        receipt = {
            "schema": "hass-pilot-receipt/1",
            "listing": int(args.listing),
            "segments": [],
            "versions": [],
            "approval": None,
            "publish": None,
            "privacy": {"text": None, "dom": None, "picture": None},
            "provenance": None,
            "stops": [],
            "elapsed_seconds": None,
        }
        payload = (json.dumps(receipt, indent=2) + "\n").encode("utf-8")
        name = write_receipt(args.out, payload)
    except ReceiptError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print("error: receipt filesystem operation failed", file=sys.stderr)
        return 1
    print(name, hashlib.sha256(payload).hexdigest()[:12])
    return 0


if __name__ == "__main__":
    sys.exit(main())
