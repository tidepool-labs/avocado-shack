#!/usr/bin/env python3
"""Report pending Hass release metadata offline. Never attempt recovery."""

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess


NAME = "release_pending_recovery"
SHA = re.compile(r"[0-9a-f]{40}")


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's unrecognized-arguments diagnostic can echo private paths.
        super().error("invalid arguments; see --help")


def read_regular(path):
    """Do not follow a final symlink or block on a FIFO swapped in after lstat."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, encoding="utf-8", newline="") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("not a regular file")
        return source.read()


def single_line(value):
    # Keep names and phases on one output line, with no terminal controls.
    return "".join(char if char.isprintable() else ascii(char)[1:-1] for char in value)


def reject_constant(_value):
    raise ValueError("not a JSON constant")


def report_receipt(path, runtime, fail):
    try:
        mode = os.lstat(path).st_mode
    except OSError:
        mode = 0
    if not stat.S_ISREG(mode):
        fail("receipt-missing")
        return
    try:
        receipt = json.loads(read_regular(path), parse_constant=reject_constant)
    except (OSError, ValueError, RecursionError):
        receipt = None
    if not isinstance(receipt, dict):
        fail("receipt-malformed")
        return
    # The writer records the canonical checkout path, not its Git dir.
    if receipt.get("runtime") != str(runtime):
        fail("receipt-runtime-mismatch")
        return

    phase = receipt.get("phase")
    fields = {"phase": single_line(phase) if isinstance(phase, str) else None}
    for name in ("old", "target"):
        value = receipt.get(name)
        fields[name] = value[:12] if isinstance(value, str) and SHA.fullmatch(value) else None
    if None in fields.values():
        fail("receipt-malformed")
    for name, value in fields.items():
        if value is not None:
            print(f"{name} {value}")


def report_host_before(path, fail):
    try:
        mode = os.lstat(path).st_mode
    except OSError:
        fail("host-before-missing")
        return
    if not stat.S_ISREG(mode) or stat.S_IMODE(mode) != 0o600:
        fail("host-before-mode")
    else:
        print("host-before 0600")


def report_pending(runtime, receipts, fail):
    try:
        if not runtime.is_dir():
            fail("not-git")
            return
        runtime = runtime.resolve()
        git = subprocess.run(
            ["git", "-C", str(runtime), "rev-parse", "--absolute-git-dir"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True,
        )
    except (OSError, RuntimeError, subprocess.CalledProcessError):
        fail("not-git")
        return

    marker = Path(os.fsdecode(git.stdout.removesuffix(b"\n"))) / "runtime-release.pending"
    try:
        mode = os.lstat(marker).st_mode
    except FileNotFoundError:
        print("ok no-pending")
        return
    except OSError:
        fail("marker-unreadable")
        return
    fail("pending-marker")
    try:
        raw = read_regular(marker) if stat.S_ISREG(mode) else ""
        path, newline, rest = raw.partition("\n")
        if not path or not newline or rest or "\r" in path or "\0" in path:
            raise ValueError("not a single path line")
    except (OSError, ValueError):
        fail("marker-unreadable")
        return

    run = Path(path)
    try:
        root = receipts.resolve()
        inside = (run.is_absolute() and run.name.startswith("run-")
                  and run.parent.resolve() == root and run.resolve().parent == root)
    except (OSError, RuntimeError):
        inside = False
    if not inside:
        fail("run-outside-receipts")
        return
    print(f"run {single_line(run.name)}")
    try:
        directory = run.is_dir()
    except OSError:
        directory = False
    if not directory:
        fail("run-missing")
        return
    report_receipt(run / "receipt.json", runtime, fail)
    report_host_before(run / "host.before", fail)


def main(argv=None):
    parser = PrivateArgumentParser(prog=NAME, description=__doc__, allow_abbrev=False)
    parser.add_argument("--runtime", required=True, type=Path, metavar="DIR")
    parser.add_argument("--receipts", required=True, type=Path, metavar="DIR")
    args = parser.parse_args(argv)
    failed = False

    def fail(reason):
        nonlocal failed
        failed = True
        print(f"FAIL {reason}")

    report_pending(args.runtime, args.receipts, fail)
    print(f"{'FAIL' if failed else 'PASS'} {NAME}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
