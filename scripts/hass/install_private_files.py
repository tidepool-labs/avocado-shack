#!/usr/bin/env python3
"""Check private install paths without opening receipts or changing permissions."""

import argparse
import os
from pathlib import Path
import stat


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's default diagnostic can echo an argument value.
        super().error("invalid arguments")


def git_finding(directory):
    for ancestor in (directory, *directory.parents):
        try:
            os.lstat(ancestor / ".git")
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            return "missing"  # Could not establish that the marker is absent.
        return "inside-git"
    return None


def findings(raw, kind, owner_uid):
    if not os.path.isabs(raw):
        return ["not-absolute"]

    parts = raw[1:].split("/")
    # Allow one trailing slash for directories only; the file type check
    # below still refuses it for files. Preserve any other empty component.
    if raw.endswith("/"):
        parts.pop()

    # Inspect the components in order before rejecting ambiguous spellings:
    # a symlink hidden by '..' is still a symlink finding. Metadata only.
    current = "/"
    try:
        info = os.lstat(current)
        for part in parts:
            if not part:
                continue
            if not stat.S_ISDIR(info.st_mode):
                return ["not-dir"]
            current = os.path.join(current, part)
            info = os.lstat(current)
            if stat.S_ISLNK(info.st_mode):
                return ["symlink"]
    except (OSError, ValueError):
        return ["missing"]

    if any(part in ("", ".", "..") for part in parts):
        return ["non-canonical"]

    result = []
    directory = stat.S_ISDIR(info.st_mode)
    if kind == "file" and (not stat.S_ISREG(info.st_mode) or raw.endswith("/")):
        result.append("not-regular")
    elif kind == "dir" and not directory:
        result.append("not-dir")
    else:
        if kind == "file" and info.st_nlink != 1:
            result.append("hardlinked")
        if stat.S_IMODE(info.st_mode) != (0o600 if kind == "file" else 0o700):
            result.append("mode")
        if info.st_uid != owner_uid:
            result.append("owner")

    path = Path(current)
    git = git_finding(path if directory else path.parent)
    if git is not None:
        result.append(git)
    return result


def main(argv=None):
    parser = PrivateArgumentParser(prog="install_private_files.py", description=__doc__)
    parser.add_argument("--owner-uid", type=int, required=True)
    parser.add_argument("--file", action="append", default=[], metavar="PATH")
    parser.add_argument("--dir", action="append", default=[], metavar="PATH")
    args = parser.parse_args(argv)

    failed = not (args.file or args.dir)
    if failed:
        print("FAIL no-paths")
    for kind, paths in (("file", args.file), ("dir", args.dir)):
        for index, path in enumerate(paths):
            reasons = findings(path, kind, args.owner_uid)
            if reasons:
                failed = True
                for reason in reasons:
                    print(f"FAIL {reason}")
            else:
                print(f"{kind}[{index}] ok")
    print("FAIL install_private_files" if failed else "PASS install_private_files")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
