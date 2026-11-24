#!/usr/bin/env python3
"""Verify a completed editor-config backup offline without modifying either file."""

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys


class DuplicateKey(ValueError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKey
        result[key] = value
    return result


def reject_constant(_token):
    raise ValueError


def read_regular(path, findings, owner_uid, *, backup=False):
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            findings.add("symlink")
            return None
        if not stat.S_ISREG(mode):
            findings.add("not-regular")
            return None
        # Do not follow a replaced symlink or block if a FIFO replaces the file.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode):
                findings.add("not-regular")
                return None
            if backup and stat.S_IMODE(info.st_mode) != 0o600:
                findings.add("backup-mode")
            if info.st_uid != owner_uid:
                findings.add("owner")
            return source.read(), (info.st_dev, info.st_ino)
    except OSError as error:
        findings.add("symlink" if error.errno == errno.ELOOP else "not-regular")
    except ValueError:
        findings.add("not-regular")
    return None


def check_json(raw, findings):
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                              parse_constant=reject_constant)
        if not isinstance(document, dict):
            raise ValueError
        settings = document.get("settings", {})
        if not isinstance(settings, dict):
            raise ValueError
        if settings.get("npp", False) is not False:
            findings.add("npp-not-off")
    except DuplicateKey:
        findings.add("duplicate-key")
    except (ValueError, RecursionError):
        findings.add("bad-json")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--owner-uid", type=int, required=True)
    args = parser.parse_args(argv)

    findings = set()
    try:
        parent_mode = args.backup.parent.stat().st_mode
    except (OSError, ValueError):
        findings.add("backup-dir-mode")
    else:
        if not stat.S_ISDIR(parent_mode) or stat.S_IMODE(parent_mode) != 0o700:
            findings.add("backup-dir-mode")

    config = read_regular(args.config, findings, args.owner_uid)
    backup = read_regular(args.backup, findings, args.owner_uid, backup=True)
    if backup is not None:
        backup_bytes, backup_identity = backup
        if config is not None:
            config_bytes, config_identity = config
            if config_identity == backup_identity:
                findings.add("backup-aliases-config")
            if config_bytes != backup_bytes:
                findings.add("bytes-differ")
        check_json(backup_bytes, findings)

        if not findings:
            print(f"backup_sha256 {hashlib.sha256(backup_bytes).hexdigest()}")
            print("PASS install_backup_receipt")
            return 0
    for reason in sorted(findings):
        print(f"FAIL {reason}")
    print("FAIL install_backup_receipt")
    return 1


if __name__ == "__main__":
    sys.exit(main())
