#!/usr/bin/env python3
"""Check install-kit config and backup attributes without opening either file."""

import argparse
from pathlib import Path
import stat


class Refused(Exception):
    """Carries only a fixed refusal label, never a path or OS error."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "FAIL arguments\n")


def explicit_path(raw, label):
    # Reject ambiguous spelling before Path can discard separators or '.' segments.
    if not raw.startswith("/") or "\0" in raw or any(
        part in ("", ".", "..") for part in raw[1:].split("/")
    ):
        raise Refused(label)
    return Path(raw)


def metadata(path, label):
    try:
        return path.lstat()
    except OSError:
        raise Refused(label) from None


def check_parents(path, label):
    for parent in reversed(path.parents):
        if not stat.S_ISDIR(metadata(parent, label).st_mode):
            raise Refused(label)


def check(config_arg, backup_arg, service_uid, backup_dir_uid):
    config = explicit_path(config_arg, "config-path")
    backup = explicit_path(backup_arg, "backup-path")

    check_parents(config, "config-path")
    source = metadata(config, "config-file")
    if not stat.S_ISREG(source.st_mode):
        raise Refused("config-file")
    if source.st_uid != service_uid:
        raise Refused("config-owner")
    if stat.S_IMODE(source.st_mode) != 0o600:
        raise Refused("config-mode")

    directory = backup.parent
    check_parents(directory, "backup-path")
    dest_dir = metadata(directory, "backup-directory")
    if not stat.S_ISDIR(dest_dir.st_mode):
        raise Refused("backup-directory")
    if dest_dir.st_uid != backup_dir_uid:
        raise Refused("backup-directory-owner")
    if stat.S_IMODE(dest_dir.st_mode) != 0o700:
        raise Refused("backup-directory-mode")

    source_dir = metadata(config.parent, "config-path")
    if (source_dir.st_dev, source_dir.st_ino) == (dest_dir.st_dev, dest_dir.st_ino):
        raise Refused("backup-directory-same-as-config")

    # Only a missing leaf is success; lstat sees even a dangling link as occupied.
    try:
        backup.lstat()
    except FileNotFoundError:
        return
    except OSError:
        raise Refused("backup-entry-unchecked") from None
    raise Refused("backup-entry-exists")


def main(argv=None):
    parser = Parser(
        prog="install_config_attributes.py",
        description="Metadata snapshot only; cannot protect a later copy from concurrent changes.",
        allow_abbrev=False,
    )
    parser.add_argument("--config", required=True, help="absolute config filename; no . or .. segments")
    parser.add_argument("--backup", required=True, help="absolute new backup filename; no trailing slash")
    parser.add_argument("--service-uid", required=True, type=int)
    parser.add_argument("--backup-dir-uid", required=True, type=int)
    args = parser.parse_args(argv)
    if min(args.service_uid, args.backup_dir_uid) < 0:
        parser.error("negative UID")
    try:
        check(args.config, args.backup, args.service_uid, args.backup_dir_uid)
    except Refused as exc:
        print(f"FAIL {exc}")
        return 1
    print("PASS config-attributes; metadata snapshot only, not safe against concurrent changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
