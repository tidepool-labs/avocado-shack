#!/usr/bin/env python3
"""Compare operator-resolved skill files with a selected local Git commit.

--roster is a UTF-8 JSON file mapping each profile label to both fleet skill
names, each with a resolved absolute path to the directory containing its SKILL.md:
{"builder-a": {"hass-npp-maintain": "/example/maintain",
               "hass-npp-review": "/example/review"}}

Use path-free labels (ASCII letters, digits, underscore, hyphen). The operator
owns roster coverage and effective skill resolution; nothing is discovered.
"""

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess

SKILLS = ("hass-npp-maintain", "hass-npp-review")


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "FAIL: invalid arguments (see --help)\n")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def git(repo, *args):
    # Neither inherited Git overrides nor replacement refs may redirect reads.
    # Missing promisor objects must fail locally, not trigger a fetch.
    env = {
        "PATH": os.environ.get("PATH", os.defpath),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_ALLOW_PROTOCOL": "",
    }
    return subprocess.run(
        ["git", "--git-dir=.git", *args], cwd=repo, env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=True,
    ).stdout


def compare_install(root, expected):
    if not isinstance(root, str) or not root.startswith("/"):
        return "invalid root"
    parts = [] if root == "/" else root[1:].split("/")
    if any(part in ("", ".", "..") for part in parts) or "\0" in root:
        return "invalid root"
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        # Open one component at a time: O_NOFOLLOW only checks the last one.
        directory = os.open("/", directory_flags)
        try:
            for part in parts:
                directory, parent = os.open(part, directory_flags, dir_fd=directory), directory
                os.close(parent)
            leaf = "SKILL.md"
            if not stat.S_ISREG(os.stat(leaf, dir_fd=directory, follow_symlinks=False).st_mode):
                return "not a regular file"
            # Recheck the opened inode; a replacement FIFO must not hang us.
            fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, "rb") as installed:
                if not stat.S_ISREG(os.fstat(installed.fileno()).st_mode):
                    return "not a regular file"
                return None if installed.read(len(expected) + 1) == expected else "bytes differ"
        finally:
            os.close(directory)
    except FileNotFoundError:
        return "missing root or file"
    except (OSError, ValueError):
        return "cannot read a regular file"


def main(argv=None):
    parser = Parser(prog="install_skill_parity.py", description=__doc__,
                    formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    parser.add_argument("--repo", required=True, help="local Git checkout")
    parser.add_argument("--commit", required=True, help="full commit SHA")
    parser.add_argument("--roster", required=True, help="path to the JSON roster")
    args = parser.parse_args(argv)

    try:
        roster = json.loads(Path(args.roster).read_text(encoding="utf-8"),
                            object_pairs_hook=unique_object)
        if not isinstance(roster, dict) or not roster or not all(
            re.fullmatch(r"[A-Za-z0-9_-]+", label) and isinstance(roots, dict)
            and roots.keys() <= set(SKILLS) for label, roots in roster.items()
        ):
            raise ValueError("invalid roster")
    except (OSError, ValueError, RecursionError):
        print("FAIL: invalid, empty or unreadable roster")
        return 1

    try:
        commit = args.commit.lower()
        if (not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit)
                or git(args.repo, "rev-parse", "--verify", f"{commit}^{{commit}}").strip()
                != commit.encode("ascii")):
            raise ValueError("not an exact commit ID")
    except (OSError, ValueError, subprocess.CalledProcessError):
        print("FAIL: cannot resolve the exact release commit locally")
        return 1

    failed = False
    for skill in SKILLS:
        try:
            expected = git(args.repo, "cat-file", "blob", f"{commit}:docs/hass/skills/{skill}/SKILL.md")
        except (OSError, subprocess.CalledProcessError):
            expected = None
        for label, roots in sorted(roster.items()):
            if skill not in roots:
                reason = "missing roster entry"
            elif expected is None:
                reason = "release blob unavailable"
            else:
                reason = compare_install(roots[skill], expected)
            if reason is None:
                print(f"PASS {label} {skill}")
            else:
                print(f"FAIL {label} {skill}: {reason}")
                failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
