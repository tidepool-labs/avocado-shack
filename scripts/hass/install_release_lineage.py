#!/usr/bin/env python3
"""Check release ancestry and tree paths using only a local Git checkout."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


class CheckError(Exception):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CheckError("manifest contains a duplicate JSON key")
        result[key] = value
    return result


def load_manifest(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (OSError, ValueError, RecursionError):
        raise CheckError("cannot read a valid JSON manifest") from None
    if not isinstance(data, dict) or set(data) != {"gates", "paths"}:
        raise CheckError("manifest must contain exactly 'gates' and 'paths'")
    gates, paths = data["gates"], data["paths"]
    if not isinstance(gates, dict) or not gates or any(not label.strip() for label in gates):
        raise CheckError("manifest 'gates' must be a nonempty object of labels to commit SHAs")
    if not isinstance(paths, list) or not paths:
        raise CheckError("manifest 'paths' must be a nonempty array of repository-relative paths")
    for path in paths:
        if (not isinstance(path, str) or "\0" in path
                or any(part in {"", ".", ".."} for part in path.split("/"))):
            raise CheckError("manifest paths must be literal, repository-relative Git tree paths")
        try:
            os.fsencode(path)
        except UnicodeError:
            raise CheckError("manifest contains an unencodable tree path") from None
    return gates, paths


class LocalGit:
    def __init__(self, repo):
        self.command = ["git", "--no-replace-objects", "--literal-pathspecs",
                        "-C", str(repo.resolve()), "--git-dir=.git", "-c", "core.commitGraph=false"]
        # Inherited Git overrides must not redirect the checkout, substitute ancestry,
        # or enable tracing. No transport is allowed, even on older Git versions.
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(GIT_ALLOW_PROTOCOL="", GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0",
                        GIT_GRAFT_FILE=os.devnull, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        if self.run("rev-parse", "--is-inside-git-dir").returncode:
            raise CheckError("--repo must name a local Git checkout")
        promisor = self.run("config", "--name-only", "--get-regexp",
                            r"^(extensions\.partialclone|remote\..*\.promisor)$")
        # Older Git can start a lazy fetch subprocess even when transport is denied.
        if promisor.returncode != 1:
            raise CheckError("cannot verify a checkout with partial-clone configuration offline")
        storage = self.run("rev-parse", "--show-object-format")
        self.sha_length = {b"sha1\n": 40, b"sha256\n": 64}.get(storage.stdout)
        if storage.returncode or self.sha_length is None:
            raise CheckError("cannot determine the checkout's Git object format")

    def run(self, *args, data=None):
        return subprocess.run([*self.command, *args], input=data, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, env=self.env, check=False)

    def object_type(self, sha):
        lookup = self.run("cat-file", "--batch-check", data=sha.encode("ascii") + b"\n")
        fields = lookup.stdout.split()
        if lookup.returncode or len(fields) < 2:
            raise CheckError("Git could not read an object type")
        oid, kind = fields[:2]
        # A hex-named ref is not evidence that the requested object ID exists.
        return kind if oid == sha.lower().encode("ascii") and kind != b"missing" else None


def check_release(git, target, gates, paths):
    sha_pattern = rf"[0-9a-fA-F]{{{git.sha_length}}}"
    if not re.fullmatch(sha_pattern, target):
        raise CheckError(f"--target must be a full {git.sha_length}-digit hexadecimal commit SHA")
    for label, sha in gates.items():
        if not isinstance(sha, str) or not re.fullmatch(sha_pattern, sha):
            raise CheckError(f"gate {ascii(label)} must have a full {git.sha_length}-digit hexadecimal commit SHA")
    if git.object_type(target) != b"commit":
        raise CheckError("target is not a commit available in this checkout")

    ok = True
    print(f"Target: {target}")
    for label, sha in gates.items():
        kind = git.object_type(sha)
        ancestor = False
        status = "no"
        if kind == b"commit":
            result = git.run("merge-base", "--is-ancestor", sha, target).returncode
            ancestor = result == 0
            status = {0: "yes", 1: "no"}.get(result, "unknown (Git error)")
        elif kind is not None:
            status = "no (not a commit)"
        print(f"Gate {ascii(label)} {sha}: object present={'yes' if kind is not None else 'no'}; "
              f"ancestor={status}")
        ok &= ancestor
    for path in paths:
        result = git.run("ls-tree", "--full-tree", "-z", target, "--", path)
        status = "unknown (Git error)"
        if not result.returncode and (not result.stdout or result.stdout.endswith(b"\0")):
            status = "no"
            encoded_path = os.fsencode(path)
            for record in result.stdout.split(b"\0"):
                metadata, _, name = record.partition(b"\t")
                if name == encoded_path:
                    fields = metadata.split(b" ")  # mode, type, object ID
                    if len(fields) != 3:
                        status = "unknown (Git error)"
                    elif fields[0] in {b"100644", b"100755"} and fields[1] == b"blob":
                        status = "yes"
                    else:
                        status = "no (not a regular file blob)"
                    break
        print(f"Path {ascii(path)}: present={status}")
        ok &= status == "yes"
    return 0 if ok else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'Manifest format: {"gates": {"LABEL": "FULL_COMMIT_SHA"}, '
        '"paths": ["relative/tree/file"]}. Exit 1 for failed checks, 2 for invalid inputs.'))
    parser.add_argument("--repo", type=Path, required=True, help="local Git checkout root")
    parser.add_argument("--target", required=True, help="full commit SHA to check")
    parser.add_argument("--manifest", type=Path, required=True, help="JSON gate and path list")
    args = parser.parse_args()
    print("Local ancestry and regular file presence only; this does not check CI or review approval, "
          "or whether a present file still has its reviewed contents.", flush=True)
    try:
        gates, paths = load_manifest(args.manifest)
        return check_release(LocalGit(args.repo), args.target, gates, paths)
    except CheckError as exc:
        print(f"Error: {exc}", file=sys.stderr)
    except OSError:
        print("Error: could not run local Git checks", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
