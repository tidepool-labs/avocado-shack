#!/usr/bin/env python3
"""Compare installed Hass service and timer files with a selected Git commit."""

import argparse
from io import BytesIO
from itertools import zip_longest
import os
from pathlib import Path
import re
import subprocess


TEMPLATE_DIR = "deploy/hass/"
UNIT_SUFFIXES = (".service", ".timer")


class UnitParser(argparse.ArgumentParser):
    def error(self, message):
        # Unknown arguments can include private paths or other values.
        if message.startswith("unrecognized arguments:"):
            message = "unrecognized arguments"
        super().error(message)


def git(repo, *args):
    # Inspect the named objects, not replacements; never fetch missing objects.
    env = dict(os.environ, GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1",
               GIT_ALLOW_PROTOCOL="", GIT_OPTIONAL_LOCKS="0")
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def finish(reason=None, *, failed=False):
    if reason is not None:
        print(f"FAIL {reason}")
    failed = failed or reason is not None
    print("FAIL units_template_parity" if failed else "PASS units_template_parity")
    return int(failed)


def compare(templates, installed, installed_entries):
    failed = False
    for name, expected in templates.items():
        path = installed / name
        try:
            if path.is_symlink():
                print(f"note symlink {name}")
            actual = path.read_bytes() if path.is_file() else None
        except OSError:
            actual = None
        if actual is None:
            print(f"FAIL missing-unit {name}")
        elif expected == actual:
            print(f"same {name}")
            continue
        else:
            # Binary iteration retains LF endings and does not decode content.
            for number, (left, right) in enumerate(
                zip_longest(BytesIO(expected), BytesIO(actual)), 1
            ):
                if left != right:
                    print(f"FAIL differs {name} {number}")
                    break
        failed = True

    for path in installed_entries:
        name = path.name
        if (name.startswith("hass-") and name.endswith(UNIT_SUFFIXES)
                and name not in templates):
            try:
                if path.is_file():
                    print(f"note extra {name}")
            except OSError:
                continue
    return finish(failed=failed)


def main(argv=None):
    parser = UnitParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--repo", required=True, type=Path, help="Git checkout")
    parser.add_argument("--commit", required=True, metavar="SHA", help="full lowercase commit SHA")
    parser.add_argument("--installed", required=True, type=Path, help="installed unit directory")
    args = parser.parse_args(argv)

    if git(args.repo, "rev-parse", "--is-inside-work-tree") != b"true\n":
        return finish("not-git")
    if (not re.fullmatch(r"[0-9a-f]{40}", args.commit)
            or git(args.repo, "cat-file", "-t", args.commit) != b"commit\n"):
        return finish("bad-commit")
    try:
        installed_entries = sorted(args.installed.iterdir())
    except OSError:
        return finish("no-installed")

    paths = git(args.repo, "ls-tree", "--name-only", "-rz", "--full-tree",
                args.commit, TEMPLATE_DIR)
    if paths is None:
        return finish("bad-commit")
    templates = {}
    for entry in paths.split(b"\0"):
        name = os.fsdecode(entry).removeprefix(TEMPLATE_DIR)
        if "/" in name or not name.endswith(UNIT_SUFFIXES):
            continue
        blob = git(args.repo, "cat-file", "blob", f"{args.commit}:{TEMPLATE_DIR}{name}")
        if blob is None:
            return finish("bad-commit")
        templates[name] = blob
    if not templates:
        return finish("bad-commit")
    return compare(templates, args.installed, installed_entries)


if __name__ == "__main__":
    raise SystemExit(main())
