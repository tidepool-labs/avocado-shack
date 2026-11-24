#!/usr/bin/env python3
"""Check the reviewed tools checkout offline (origin is a local config check)."""

import argparse
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess


NAME = "install_tools_checkout"


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's normal diagnostic may echo a mistyped private value.
        super().error("invalid arguments")


def git(repo, *args):
    try:
        return subprocess.run(
            ["git", "--no-optional-locks", "--no-replace-objects", "-c", "core.fsmonitor=false", *args],
            cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": ""},
            check=True,
        ).stdout
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None


def normalize_url(url):
    return url.removesuffix(b"/").removesuffix(b".git")


def remote_finding(repo, expected):
    raw = git(repo, "config", "--null", "--get-all", "remote.origin.url")
    if raw in (None, b"", b"\0"):
        return "no-remote"
    # One exact value, not a substring, remote rewrite, or choice among URLs.
    actual = raw.removesuffix(b"\0")
    if (not raw.endswith(b"\0") or not actual.decode("utf-8", "replace").isprintable()
            or not expected.isprintable() or not normalize_url(actual)
            or normalize_url(actual) != normalize_url(os.fsencode(expected))):
        return "wrong-remote"
    return None


def file_digest(directory, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError
        with os.fdopen(fd, "rb", closefd=False) as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    finally:
        os.close(fd)


def install_digests(repo, sha):
    tree = git(repo, "ls-tree", "-z", f"{sha}:scripts/hass")
    if not tree or not tree.endswith(b"\0"):
        raise ValueError
    helpers = {}
    for entry in tree.split(b"\0")[:-1]:
        header, name = entry.split(b"\t", 1)
        if not (name.startswith(b"install_") and name.endswith(b".py")):
            continue
        mode, kind, oid = header.split()
        if (mode not in (b"100644", b"100755") or kind != b"blob"
                or name in helpers or b"/" in name or not name.decode("utf-8").isprintable()):
            raise ValueError
        helpers[name] = oid.decode("ascii")
    if not helpers:
        raise ValueError

    rows = []
    # Do not follow checkout links at any component below the supplied root.
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as stack:
        scripts = os.open(repo / "scripts", flags)
        stack.callback(os.close, scripts)
        hass = os.open("hass", flags, dir_fd=scripts)
        stack.callback(os.close, hass)
        for name, oid in sorted(helpers.items()):
            if git(repo, "cat-file", "-t", oid) != b"blob\n":
                raise ValueError
            blob = git(repo, "cat-file", "blob", oid)
            if blob is None:
                raise ValueError
            digest = file_digest(hass, name)
            if digest != hashlib.sha256(blob).hexdigest():
                raise ValueError
            rows.append(f"install_tool scripts/hass/{name.decode('utf-8')} {digest[:12]}")
    return rows


def main(argv=None):
    parser = Parser(prog=NAME, description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="checkout root")
    parser.add_argument("--sha", required=True, help="reviewed 40-character commit SHA")
    parser.add_argument("--remote-url", required=True, help="expected origin URL")
    args = parser.parse_args(argv)

    findings = []
    valid_sha = re.fullmatch(r"[0-9a-f]{40}", args.sha)
    if not valid_sha:
        findings.append("bad-sha")
    rows = []
    if git(args.repo, "rev-parse", "--is-inside-work-tree", "--show-prefix") != b"true\n\n":
        findings.append("not-git")
    else:
        if valid_sha and git(args.repo, "rev-parse", "--verify", "HEAD^{commit}") != (
            args.sha.encode("ascii") + b"\n"
        ):
            findings.append("head-mismatch")
        if git(args.repo, "status", "--porcelain", "--untracked-files=all") != b"":
            findings.append("dirty")
        remote = remote_finding(args.repo, args.remote_url)
        if remote:
            findings.append(remote)
        if not findings:
            try:
                rows = install_digests(args.repo, args.sha)
            except (OSError, ValueError):
                findings.append("dirty")

    if findings:
        for reason in findings:
            print(f"FAIL {reason}")
        print(f"FAIL {NAME}")
        return 1
    for row in rows:
        print(row)
    print(f"PASS {NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
