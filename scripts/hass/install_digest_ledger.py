#!/usr/bin/env python3
"""Record or check a config digest in an offline, owner-only ledger."""

import argparse
from datetime import datetime
import errno
import fcntl
import hashlib
import json
import os
import re
import stat


LABEL = re.compile(r"[a-z0-9-]{1,32}")
SHA256 = re.compile(r"[0-9a-f]{64}")
UTC_TIME = re.compile(r"[0-9W-]+T[0-9]{2}(?::?[0-9]{2}){0,2}(?:[.,][0-9]+)?Z")
KEYS = {"label", "sha256", "size", "at"}
READ_FLAGS = os.O_RDONLY | os.O_NONBLOCK


class Refusal(Exception):
    """Carries only a fixed, public finding code."""


def matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def valid_time(value):
    if not matches(UTC_TIME, value):
        return False
    try:
        datetime.fromisoformat(value[:-1])
    except ValueError:
        return False
    return True


def fingerprint(path):
    digest = hashlib.sha256()
    size = 0
    try:
        if not stat.S_ISREG(os.stat(path).st_mode):
            raise Refusal("not-regular")
        with os.fdopen(os.open(path, READ_FLAGS), "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise Refusal("not-regular")
            while chunk := source.read(65536):
                digest.update(chunk)
                size += len(chunk)
    except (OSError, ValueError):
        raise Refusal("not-regular") from None
    return digest.hexdigest(), size


def unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate key")
    return result


def lookup(ledger, label):
    last = None
    terminated = True
    for line in ledger:
        try:
            entry = json.loads(line.decode("utf-8"), object_pairs_hook=unique_object)
        except (ValueError, RecursionError):
            raise Refusal("bad-ledger") from None
        if not (isinstance(entry, dict) and entry.keys() == KEYS
                and matches(LABEL, entry["label"]) and matches(SHA256, entry["sha256"])
                and type(entry["size"]) is int and entry["size"] >= 0
                and valid_time(entry["at"])):
            raise Refusal("bad-ledger")
        if entry["label"] == label:
            last = (entry["sha256"], entry["size"])
        terminated = line.endswith(b"\n")
    return last, terminated


def verify_ledger_mode(mode):
    if stat.S_ISLNK(mode):
        raise Refusal("ledger-symlink")
    if not stat.S_ISREG(mode):
        raise Refusal("bad-ledger")
    if stat.S_IMODE(mode) != 0o600:
        raise Refusal("ledger-mode")


def open_ledger(parent_fd, name, record):
    flags = os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_RDWR | os.O_APPEND if record else os.O_RDONLY)
    try:
        mode = os.stat(name, dir_fd=parent_fd, follow_symlinks=False).st_mode
    except FileNotFoundError:
        if not record:
            raise Refusal("no-entry") from None
        try:
            return os.open(name, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent_fd), True
        except FileExistsError:
            mode = os.stat(name, dir_fd=parent_fd, follow_symlinks=False).st_mode
    verify_ledger_mode(mode)
    try:
        return os.open(name, flags, dir_fd=parent_fd), False
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise Refusal("ledger-symlink") from None
        raise


def use_ledger(args, digest, size):
    parent, name = os.path.split(args.ledger)
    record = args.command == "record"
    try:
        parent_fd = os.open(parent or ".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except (OSError, ValueError):
        raise Refusal("ledger-dir-mode") from None
    try:
        if stat.S_IMODE(os.fstat(parent_fd).st_mode) != 0o700:
            raise Refusal("ledger-dir-mode")
        if not name:
            raise Refusal("bad-ledger")
        fd, created = open_ledger(parent_fd, name, record)
        with os.fdopen(fd, "r+b" if record else "rb") as ledger:
            if created:
                os.fchmod(fd, 0o600)  # Also exact under a restrictive umask.
            verify_ledger_mode(os.fstat(fd).st_mode)
            # Keep validation and append together for cooperating invocations.
            fcntl.flock(fd, fcntl.LOCK_EX if record else fcntl.LOCK_SH)
            last, terminated = lookup(ledger, args.label)
            if record:
                entry = {"label": args.label, "sha256": digest, "size": size, "at": args.at}
                prefix = "" if terminated else "\n"
                ledger.write((prefix + json.dumps(entry) + "\n").encode("utf-8"))
            elif last is None:
                raise Refusal("no-entry")
            elif last != (digest, size):
                raise Refusal("drift")
    finally:
        os.close(parent_fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("record", "check"):
        sub = commands.add_parser(command)
        sub.add_argument("--ledger", required=True, metavar="FILE")
        sub.add_argument("--label", required=True, metavar="NAME")
        sub.add_argument("--file", required=True, metavar="PATH")
        if command == "record":
            sub.add_argument("--at", required=True, metavar="ISO", help="UTC timestamp ending in Z")
    args = parser.parse_args(argv)

    findings = []
    if not matches(LABEL, args.label):
        findings.append("bad-label")
    if args.command == "record" and not valid_time(args.at):
        findings.append("bad-time")
    if not findings:
        try:
            digest, size = fingerprint(args.file)
            use_ledger(args, digest, size)
        except Refusal as error:
            findings.append(str(error))
        except (OSError, ValueError):
            findings.append("bad-ledger")
        else:
            if args.command == "check":
                print(f"MATCH {args.label} {digest[:12]}")
            print("PASS install_digest_ledger")
            return 0
    for reason in findings:
        print(f"FAIL {reason}")
    print("FAIL install_digest_ledger")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
