#!/usr/bin/env python3
"""Check an adjacent config stage without changing either file."""

import argparse
import hashlib
import json
import os
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


def inspect_file(path, owner_uid, findings, *, stage=False, expect_stage_sha256=None):
    try:
        info = os.lstat(path)
    except (OSError, ValueError):
        findings.append("not-regular")
        return
    if stat.S_ISLNK(info.st_mode):
        findings.append("symlink")
        return
    if not stat.S_ISREG(info.st_mode):
        findings.append("not-regular")
        return
    if stage and info.st_nlink != 1:
        findings.append("hardlinked")
    if stat.S_IMODE(info.st_mode) != 0o600:
        findings.append("mode")
    if info.st_uid != owner_uid:
        findings.append("owner")

    try:
        # Do not follow a substituted leaf or block if it was replaced by a FIFO.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source:
            opened = os.fstat(source.fileno())
            if not os.path.samestat(info, opened):
                findings.append("not-regular")
            elif stage:
                raw = source.read()
                document = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                                      parse_constant=reject_constant)
                if not isinstance(document, dict):
                    findings.append("bad-json")
                elif (expect_stage_sha256 is not None
                      and hashlib.sha256(raw).hexdigest() != expect_stage_sha256.lower()):
                    findings.append("stage-sha256-mismatch")
    except DuplicateKey:
        findings.append("duplicate-key")
    except (OSError, ValueError, RecursionError):
        # There is no separate reason for unreadable inputs.
        findings.append("bad-json" if stage else "not-regular")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        "This is a preflight check, not a lock or an authorization to replace the config."
    ))
    parser.add_argument("--config", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--owner-uid", required=True, type=int)
    parser.add_argument("--expect-stage-sha256", metavar="HEX",
                        help="require the SHA-256 of the already selected candidate bytes")
    args = parser.parse_args(argv)

    findings = []
    inspect_file(args.config, args.owner_uid, findings)
    inspect_file(args.stage, args.owner_uid, findings, stage=True,
                 expect_stage_sha256=args.expect_stage_sha256)

    config_parent, config_name = os.path.split(args.config)
    stage_parent, stage_name = os.path.split(args.stage)
    if config_name and config_name == stage_name:
        findings.append("same-name")
    try:
        if not os.path.samestat(os.stat(config_parent or "."), os.stat(stage_parent or ".")):
            findings.append("other-directory")
    except (OSError, ValueError):
        # The corresponding file inspection already reports the inaccessible path.
        if "not-regular" not in findings:
            findings.append("not-regular")

    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} install_stage_file")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
