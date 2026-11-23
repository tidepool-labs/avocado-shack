#!/usr/bin/env python3
"""Check one pilot publish commit against an operator's path patterns, offline."""

import argparse
from collections import Counter
from fnmatch import fnmatchcase
import json
import os
from pathlib import Path
import re
import subprocess
import unicodedata


TOOL = "npp_publish_footprint"
OID = re.compile(rb"[0-9a-f]{40}(?:[0-9a-f]{24})?")


class Finding(ValueError):
    """A fixed diagnostic safe to print without Git or input data."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse may include the caller's raw arguments in its error text.
        super().error("invalid arguments; see --help")


def git(repo, *args):
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=False,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_REPLACE_OBJECTS": "1",
                 "GIT_NO_LAZY_FETCH": "1"},
        )
    except (OSError, subprocess.TimeoutExpired):
        raise Finding("git-error") from None


def resolve(repo, revision, which):
    result = git(repo, "rev-parse", "--verify", "--quiet", revision + "^{commit}")
    if result.returncode:
        raise Finding(f"bad-rev {which}")
    oid = result.stdout.removesuffix(b"\n")
    if not OID.fullmatch(oid):
        raise Finding("git-error")
    return oid.decode("ascii")


def parents(raw, oid_length):
    header, separator, _ = raw.partition(b"\n\n")
    lines = iter(header.split(b"\n"))
    key, _, tree = next(lines).partition(b" ")
    if not separator or key != b"tree" or len(tree) != oid_length or not OID.fullmatch(tree):
        raise Finding("git-error")
    found = []
    line = next(lines, b"")
    while line.startswith(b"parent "):
        oid = line[len(b"parent "):]
        if len(oid) != oid_length or not OID.fullmatch(oid):
            raise Finding("git-error")
        found.append(oid.decode("ascii"))
        line = next(lines, b"")
    if not line.startswith(b"author ") or not line[7:] or b"\0" in line:
        raise Finding("git-error")
    line = next(lines, b"")
    if not line.startswith(b"committer ") or not line[10:] or b"\0" in line:
        raise Finding("git-error")
    # Optional headers (e.g. gpgsig) may have space-prefixed continuation
    # lines. A parent outside the leading parent block is malformed.
    continuation = False
    for line in lines:
        if b"\0" in line:
            raise Finding("git-error")
        if continuation and line.startswith(b" "):
            continue
        key, space, _ = line.partition(b" ")
        if (not space or not re.fullmatch(rb"[!-~]+", key)
                or key in {b"tree", b"parent", b"author", b"committer"}):
            raise Finding("git-error")
        continuation = True
    return found


def allow_patterns(path):
    try:
        if path.is_symlink() or not path.is_file():
            raise Finding("bad-allow")
        lines = path.read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeError):
        raise Finding("bad-allow") from None
    patterns = [line for line in lines if line.strip() and not line.startswith("#")]
    if not patterns or any(p.startswith("/") or ".." in p or "\0" in p for p in patterns):
        raise Finding("bad-allow")
    return patterns


def footprint(args):
    try:
        is_directory = not args.repo.is_symlink() and args.repo.is_dir()
    except OSError:
        is_directory = False
    if not is_directory:
        raise Finding("not-a-repo")
    for which, revision in (("from", args.before), ("to", args.to)):
        if revision.startswith("-") or any(c.isspace() or unicodedata.category(c) == "Cc" for c in revision):
            raise Finding(f"bad-rev {which}")
    if git(args.repo, "rev-parse", "--git-dir").returncode:
        raise Finding("not-a-repo")
    before = resolve(args.repo, args.before, "from")
    after = resolve(args.repo, args.to, "to")
    ancestry = git(args.repo, "merge-base", "--is-ancestor", before, after)
    if ancestry.returncode == 1:
        raise Finding("not-ancestor")
    if ancestry.returncode:
        raise Finding("git-error")
    commit = git(args.repo, "cat-file", "commit", after)
    if commit.returncode:
        raise Finding("git-error")
    if parents(commit.stdout, len(after)) != [before]:
        raise Finding("not-single-publish")
    patterns = allow_patterns(args.allow)
    result = git(args.repo, "diff", "--name-status", "-z", "--no-renames", "--no-ext-diff",
                 "--ignore-submodules=none", before, after, "--")
    if result.returncode:
        raise Finding("git-error")
    fields = result.stdout.split(b"\0")
    if fields.pop() or len(fields) % 2 or any(not field for field in fields):
        raise Finding("git-error")
    counts = Counter()
    unexpected = []
    for status, name in zip(fields[::2], fields[1::2]):
        letter = chr(status[0])
        path = name.decode("utf-8", errors="surrogateescape")
        counts[letter] += 1
        if not any(fnmatchcase(path, pattern) for pattern in patterns):
            unexpected.append((letter, path))
    changed = sum(counts.values())
    print(f"changed {changed}")
    for letter, count in sorted(counts.items()):
        print(f"status {letter} {count}")
    print(f"allowed {changed - len(unexpected)}")
    for letter, path in unexpected:
        print(f"unexpected {letter} {json.dumps(path)}")
    if not changed:
        raise Finding("no-change")
    if unexpected:
        raise Finding(f"unexpected {len(unexpected)}")


def main(argv=None):
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--repo", required=True, type=Path, help="local site repository")
    parser.add_argument("--from", required=True, dest="before", help="the publish commit's sole parent")
    parser.add_argument("--to", required=True, help="the single publish commit")
    parser.add_argument("--allow", required=True, type=Path, help="UTF-8 file with one path pattern per line")
    args = parser.parse_args(argv)
    try:
        footprint(args)
    except Finding as finding:
        print(f"FAIL {finding}")
        print(f"FAIL {TOOL}")
        return 1
    print(f"PASS {TOOL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
