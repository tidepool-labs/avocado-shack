#!/usr/bin/env python3
"""Find install entry-gate merge SHAs in a local Git checkout."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


class GateError(ValueError):
    """An error safe to print without echoing input or Git diagnostics."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GateError("malformed units JSON: duplicate key")
        result[key] = value
    return result


def load_units(source):
    try:
        units = json.loads(source.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except GateError:
        raise
    except (ValueError, RecursionError):
        raise GateError("malformed units JSON: expected valid UTF-8 JSON") from None
    except OSError:
        raise GateError("could not read units JSON") from None
    if not isinstance(units, dict) or not units:
        raise GateError("malformed units JSON: expected a nonempty unit object")
    for letter, spec in units.items():
        if (not re.fullmatch(r"[A-Za-z]", letter) or not isinstance(spec, dict)
                or spec.keys() != {"pr", "paths"}):
            raise GateError("malformed units JSON: expected unit letters with pr and paths")
        pr, paths = spec["pr"], spec["paths"]
        if pr is not None and (type(pr) is not int or pr <= 0):
            raise GateError("malformed units JSON: pr must be a positive integer or null")
        if not isinstance(paths, list):
            raise GateError("malformed units JSON: paths must be an array")
        if pr is not None and not paths:
            raise GateError("malformed units JSON: known pr requires at least one path")
        for path in paths:
            if (not isinstance(path, str) or "\0" in path
                    or any(part in {"", ".", ".."} for part in path.split("/"))):
                raise GateError("malformed units JSON: expected literal repository-relative paths")
            try:
                os.fsencode(path)
            except UnicodeError:
                raise GateError("malformed units JSON: unencodable path") from None
    return units


class LocalGit:
    def __init__(self, repo):
        self.command = ["git", "--no-replace-objects", "--literal-pathspecs", "-C", repo,
                        "--git-dir=.git", "-c", "core.commitGraph=false"]
        # Ignore inherited Git overrides, and deny transport even on old Git.
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(GIT_ALLOW_PROTOCOL="", GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0",
                        GIT_GRAFT_FILE=os.devnull, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        shallow = self.run("rev-parse", "--is-shallow-repository")
        if shallow.returncode:
            raise GateError("--repo must name a local Git checkout")
        if shallow.stdout != b"false\n":
            raise GateError("cannot verify merge uniqueness in a shallow checkout")
        if self.run("config", "--get-regexp",
                    r"^(extensions\.partialclone|remote\..*\.promisor)$").returncode != 1:
            raise GateError("cannot verify partial-clone configuration offline")

    def run(self, *args, data=None):
        return subprocess.run([*self.command, *args], input=data, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, env=self.env, check=False)

    def require_commit(self, target):
        if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", target, re.IGNORECASE):
            oid = target.lower().encode("ascii")
            result = self.run("cat-file", "--batch-check", data=oid + b"\n")
            if not result.returncode and result.stdout.split()[:2] == [oid, b"commit"]:
                return oid.decode("ascii")
        raise GateError("unknown target or target is not a commit (expected a full commit SHA)")

    def merge_matches(self, target, prs):
        by_number = {str(pr).encode("ascii"): pr for pr in prs}
        matches = {pr: [] for pr in prs}
        result = self.run("log", "--first-parent", "--merges", "--no-notes", "--no-show-signature",
                          "--encoding=UTF-8", "-z", "--format=%H%x00%s", target, "--")
        fields = result.stdout.split(b"\0")
        if result.returncode or fields[-1] != b"" or len(fields) % 2 == 0:
            raise GateError("could not read target merge history")
        for sha, subject in zip(fields[:-1:2], fields[1::2]):
            if not re.fullmatch(rb"[0-9a-f]{%d}" % len(target), sha):
                raise GateError("could not read target merge history")
            # The required space after the PR number rules out prefix collisions.
            match = re.match(rb"Merge pull request #([0-9]+) ", subject)
            if match and match[1] in by_number:
                matches[by_number[match[1]]].append(sha.decode("ascii"))
        return matches

    def present(self, target, path):
        result = self.run("ls-tree", "--full-tree", "--name-only", "-z", target, "--", path)
        if result.returncode:
            raise GateError("could not read target tree")
        return os.fsencode(path) in result.stdout.split(b"\0")


def report(git, target, units):
    matches = git.merge_matches(target, {spec["pr"] for spec in units.values() if spec["pr"] is not None})
    ok = True
    for unit, spec in units.items():
        pr = spec["pr"]
        merges = matches.get(pr, [])
        if pr is None:
            outcome = "FILL-IN open"
        elif not merges:
            outcome = "no merge found"
        elif len(merges) != 1:
            outcome = "duplicate merges found"
        else:
            outcome = f"{merges[0]}; ancestor: yes"
        present = [git.present(target, path) for path in spec["paths"]]
        fields = [f"{unit}: PR {'null' if pr is None else '#' + str(pr)}", outcome]
        fields.extend(f"path {index}: {'present' if found else 'missing'}"
                      for index, found in enumerate(present, 1))
        print("; ".join(fields))
        ok &= len(merges) == 1 and all(present)
    return 0 if ok else 1


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "error: invalid arguments; see --help\n")


def main(argv=None):
    parser = ArgumentParser(description=__doc__, epilog="Path statuses are numbered in units-file order.")
    parser.add_argument("--repo", required=True, help="local Git checkout root")
    parser.add_argument("--target", required=True, help="full target commit SHA")
    parser.add_argument("--units", required=True, type=Path,
                        help='JSON object: {"B": {"pr": 1, "paths": ["path/to/file"]}}')
    args = parser.parse_args(argv)
    try:
        units = load_units(args.units)
        git = LocalGit(args.repo)
        return report(git, git.require_commit(args.target), units)
    except GateError as error:
        print(f"error: {error}", file=sys.stderr)
    except OSError:
        print("error: could not run local Git checks", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
