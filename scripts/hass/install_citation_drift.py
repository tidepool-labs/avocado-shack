#!/usr/bin/env python3
"""Check install-kit citation spans against a local commit, not the checkout files."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import NoReturn


SCOPE = "Only file and range existence were checked; semantic equivalence was not checked."


def _git(repo: Path, *args: str) -> bytes:
    # Bind lookups to --repo rather than an inherited index, Git dir or object store.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    # Older Git versions may ignore NO_LAZY_FETCH. Deny every transport as a backstop.
    env.update(GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="")
    return subprocess.run(
        ["git", "--no-replace-objects", "-C", str(repo), *args],
        env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    ).stdout


def _citation(value: str) -> tuple[str, int]:
    path, _, span = value.rpartition(":")
    match = re.fullmatch(r"([0-9]+)[-–]([0-9]+)", span)
    if not match or not path.isprintable() or any(
        part in ("", ".", "..") for part in path.split("/")
    ):
        raise ValueError
    start, end = map(int, match.groups())
    if not 1 <= start <= end:
        raise ValueError
    return path, end


def _check(repo: Path, commit: str, path: str, end: int) -> str | None:
    entries = _git(repo, "--literal-pathspecs", "ls-tree", "-z", "--full-tree", commit, "--", path)
    for entry in entries.split(b"\0"):
        header, _, name = entry.partition(b"\t")
        if name != os.fsencode(path):
            continue
        mode, kind, oid = header.split()
        if mode not in (b"100644", b"100755") or kind != b"blob":
            return "not a regular file"
        blob = _git(repo, "cat-file", "blob", oid.decode("ascii"))
        # Git source lines are LF-delimited. A final, unterminated line still counts.
        lines = blob.count(b"\n") + bool(blob and not blob.endswith(b"\n"))
        return f"too short ({lines} lines; needs line {end})" if end > lines else None
    return "missing from the selected commit"


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse messages can echo a pasted operand (unrecognized arguments, ignored
        # explicit argument, ambiguous option). Never print them; use fixed text only.
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: invalid command-line arguments; "
                     "operands are not echoed. Put citation references after `--`.\n")

    def fail(self, message: str) -> NoReturn:
        # For this script's own fixed messages, which never contain user input.
        super().error(message)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__, epilog=SCOPE)
    parser.add_argument("--repo", required=True, type=Path, help="local Git checkout")
    parser.add_argument("--commit", required=True, help="full commit object ID")
    parser.add_argument("references", nargs="+", metavar="path:start-end",
                        help="inclusive line range; hyphen or en dash")
    args = parser.parse_args(argv)

    try:
        oid_lengths = {b"sha1": 40, b"sha256": 64}
        length = oid_lengths.get(_git(args.repo, "rev-parse", "--show-object-format").strip())
    except (OSError, subprocess.CalledProcessError):
        parser.fail("cannot open the local Git checkout")
    if length is None or not re.fullmatch(r"[0-9a-fA-F]+", args.commit) or len(args.commit) != length:
        parser.fail("--commit must be a full commit object ID")
    commit = args.commit.lower()
    try:
        is_commit = _git(args.repo, "cat-file", "-t", commit).strip() == b"commit"
    except (OSError, subprocess.CalledProcessError):
        is_commit = False
    if not is_commit:
        parser.fail("--commit is not an available local commit object")

    print(f"Selected commit: {commit[:12]}")
    failed = False
    for ordinal, reference in enumerate(args.references, start=1):
        try:
            path, end = _citation(reference)
        except ValueError:
            print(f"FAIL citation #{ordinal}: invalid citation; "
                  "expected repo-relative path:start-end with positive, ordered lines")
            failed = True
            continue
        try:
            problem = _check(args.repo, commit, path, end)
        except (OSError, subprocess.CalledProcessError):
            problem = "could not read the local Git object"
        if problem is None:
            print(f"OK {reference!r}")
        else:
            print(f"FAIL {reference!r}: {problem}")
            failed = True
    print(SCOPE)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
