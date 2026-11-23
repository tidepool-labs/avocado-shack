#!/usr/bin/env python3
"""Compare NPP assets and pins between two local commits without a checkout."""

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.hass.npp_limits import asset_hashes

ASSETS = "hass/npp/assets"
PINS = "hass/npp/pins.json"
PREFIX = ASSETS + "/"


class GitReadError(Exception):
    """A local Git read failed; the command and its diagnostics stay private."""


def git(repo, *args):
    result = subprocess.run(
        ["git", "-C", repo, *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_ALLOW_PROTOCOL": "",
             "GIT_NO_LAZY_FETCH": "1"},
    )
    if result.returncode:
        raise GitReadError
    return result.stdout


def paths(raw):
    return [os.fsdecode(path) for path in raw.split(b"\0") if path]


class GitAssets:
    """Minimal path interface for asset_hashes, backed solely by commit entries."""

    def __init__(self, repo, commit):
        self.repo = repo
        self.commit = commit

    def rglob(self, pattern):
        assert pattern == "*"
        listing = git(self.repo, "ls-tree", "-r", "--name-only", "-z", self.commit, "--", ASSETS)
        return [GitAsset(self, path) for path in paths(listing) if path.startswith(PREFIX)]


class GitAsset:
    def __init__(self, root, path):
        self.root = root
        self.path = path

    def __lt__(self, other):
        return self.path < other.path

    def is_file(self):
        # Recursive ls-tree lists leaf entries, not directories.
        return True

    def relative_to(self, root):
        return PurePosixPath(self.path).relative_to(ASSETS)

    def read_bytes(self):
        return git(self.root.repo, "show", f"{self.root.commit}:{self.path}")


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse's diagnostics can echo an unknown argument verbatim.
        super().error("invalid arguments; see --help")


def reject_constant(_token):
    raise ValueError("not a JSON number")


def read_pins(repo, commit):
    try:
        data = json.loads(git(repo, "show", f"{commit}:{PINS}"), parse_constant=reject_constant)
    except (GitReadError, ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


def object_fields(value):
    return value if isinstance(value, dict) else {}


def step_changes(before, after):
    old = object_fields(before.get("steps"))
    new = object_fields(after.get("steps"))
    for step in sorted(old.keys() | new.keys()):
        a, b = object_fields(old.get(step)), object_fields(new.get(step))
        for field in sorted(a.keys() | b.keys()):
            # Compare parsed JSON, ignoring object order but distinguishing true from 1.
            if field not in a or field not in b or (
                json.dumps(a[field], sort_keys=True) != json.dumps(b[field], sort_keys=True)
            ):
                yield step, field


def label(name):
    # Keep even control characters in Git paths and JSON keys on one output line.
    return "".join(c if c.isprintable() else ascii(c)[1:-1] for c in name)


def failure(reason):
    print(f"FAIL {reason}")
    print("FAIL npp_pin_diff")
    return 1


def main(argv=None):
    parser = Parser(prog="npp_pin_diff.py", description=__doc__)
    parser.add_argument("--repo", required=True, metavar="DIR")
    parser.add_argument("--base", required=True, metavar="REV")
    parser.add_argument("--head", required=True, metavar="REV")
    args = parser.parse_args(argv)
    repo = args.repo
    try:
        git(repo, "rev-parse", "--git-dir")
    except (GitReadError, OSError):
        return failure("not-a-repo")

    commits = []
    for side, rev in (("base", args.base), ("head", args.head)):
        try:
            commits.append(git(repo, "rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}")
                           .strip().decode("ascii"))
        except GitReadError:
            return failure(f"bad-rev {side}")
    base, head = commits

    try:
        # npp_limits infers Path from its default; the helper uses only the adapter methods above.
        actual = asset_hashes(GitAssets(repo, head))  # pyright: ignore[reportArgumentType]
        changed = paths(git(repo, "diff", "--name-only", "-z", "--no-renames", "--no-ext-diff",
                            "--no-textconv", base, head, "--", ASSETS, PINS))
    except GitReadError:
        # An incomplete object store cannot establish pin integrity.
        print("FAIL npp_pin_diff")
        return 1
    asset_changes = sorted(path[len(PREFIX):] for path in changed if path.startswith(PREFIX))
    pins_changed = PINS in changed
    print(f"assets {len(actual)}")
    print(f"assets-changed {len(asset_changes)}")
    for name in asset_changes:
        print(f"asset-changed {label(name)}")
    print("pins-changed " + ("yes" if pins_changed else "no"))

    head_pins = read_pins(repo, head)
    pinned = head_pins.get("assets")
    if pins_changed:
        for step, field in step_changes(read_pins(repo, base), head_pins):
            print(f"step-changed {label(step)} {label(field)}")
    if not isinstance(pinned, dict):
        return failure("pins-unreadable")

    findings = [f"pin-stale {label(k)}" for k in sorted(pinned.keys() & actual.keys()) if pinned[k] != actual[k]]
    findings += [f"pin-missing {label(k)}" for k in sorted(actual.keys() - pinned.keys())]
    findings += [f"pin-orphan {label(k)}" for k in sorted(pinned.keys() - actual.keys())]
    for reason in findings:
        print(f"FAIL {reason}")
    print(("FAIL" if findings else "PASS") + " npp_pin_diff")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
