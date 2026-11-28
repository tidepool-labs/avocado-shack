#!/usr/bin/env python3
"""Exercise the private NPP artifact boundary with disposable files only."""

import argparse
import os
from pathlib import Path
import signal
import stat
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import media  # noqa: E402
from hass.npp import receipt  # noqa: E402


JOBS_OK = ("abcd", "0123456789ab")
JOBS_BAD = ("ABCD", "abc", "aaaaaaaaaaaaa", "../x", "abcd/e", "")
RECEIPT = b'{"a": 1}\n'


def refused(call, *args, expected: tuple[type[Exception], ...] = (ValueError,)):
    try:
        call(*args)
    except expected:
        return True
    return False


class FifoDeadline(Exception):
    """The read did not return promptly."""


def fifo_refused(path):
    def expire(_signum, _frame):
        raise FifoDeadline

    # Bound even a blocking open, without a writer changing the FIFO fixture.
    previous = signal.signal(signal.SIGALRM, expire)
    try:
        signal.setitimer(signal.ITIMER_REAL, 5)
        return refused(receipt.read_artifact, path)
    except FifoDeadline:
        return False
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def check(root, fail):
    artifacts = receipt.Artifacts(root)
    png = media.KINDS["png"] + b"x" * 10
    card = None
    for job in JOBS_OK:
        try:
            path, _ = artifacts.write_card(job, png)
        except Exception:
            fail(f"job-refused {job}")
        else:
            if job == "abcd":
                card = path
    for i, job in enumerate(JOBS_BAD):
        if not refused(artifacts.write_card, job, png):
            fail(f"job-accepted {i}")
    if card is None:
        # The abcd write already reported failure; there is no card to inspect.
        return

    npp = root / "npp"
    job_dir = npp / "abcd"
    modes = [stat.S_IMODE(path.lstat().st_mode) for path in (npp, job_dir, card)]
    permissions = (mode & 0o777 for mode in modes)
    print("modes root={:03o} job={:03o} card={:03o}".format(*permissions))
    for name, mode, expected in zip(("root", "job", "card"), modes, (0o700, 0o700, 0o600)):
        if mode != expected:
            fail(f"mode {name}")
    if receipt.read_artifact(card) != png:
        fail("round-trip card")

    link = job_dir / ("card-" + "cd" * 32 + ".png")
    link.symlink_to(card)
    # Also use the actual digest so the hash guard cannot mask a symlink regression.
    alias_dir = root / "alias"
    alias_dir.mkdir()
    alias = alias_dir / card.name
    alias.symlink_to(card)
    refusals = [refused(receipt.read_artifact, path, expected=(OSError, ValueError))
                for path in (link, alias)]
    if not all(refusals):
        fail("unsafe-read symlink")

    saved = job_dir / "receipt.json"
    os.mkfifo(saved)
    try:
        if not fifo_refused(saved):
            fail("unsafe-read fifo")
    finally:
        saved.unlink()
    artifacts.write_receipt("abcd", {"a": 1})
    if receipt.read_artifact(saved) != RECEIPT:
        fail("round-trip receipt")

    for kind, path, data in (
        ("bad-hash", job_dir / ("card-" + "ef" * 32 + ".png"), png),
        ("other-name", job_dir / "notes.txt", b"{}"),
    ):
        path.write_bytes(data)
        if not refused(receipt.read_artifact, path):
            fail(f"unsafe-read {kind}")

    before = saved.read_bytes()
    rejected = refused(artifacts.write_receipt, "abcd", {"x": "y" * 262144})
    if not rejected or not saved.is_file() or saved.read_bytes() != before:
        fail("unsafe-write big-receipt")
    if not refused(artifacts.write_card, "abcd", b"GIF89a"):
        fail("unsafe-write not-png")
    if not refused(artifacts.card, "abcd", "zz"):
        fail("unsafe-write bad-digest")
    with tempfile.TemporaryDirectory(dir=root) as target:
        (npp / "beef").symlink_to(target, target_is_directory=True)
        if not refused(artifacts.folder, "beef"):
            fail("unsafe-write symlink-dir")
        with tempfile.TemporaryDirectory(dir=root) as other_root:
            (Path(other_root) / "npp").symlink_to(target, target_is_directory=True)
            if not refused(receipt.Artifacts(other_root).write_card, "abcd", png):
                fail("unsafe-write symlink-root")
    if any(path.name.startswith(".receipt-") for path in npp.iterdir()):
        fail("temp-left")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    args = sys.argv[1:] if argv is None else argv
    parser.parse_args(args)
    if args:  # argparse otherwise accepts a bare '--'.
        parser.error("no arguments are accepted")

    failed = False

    def fail(reason):
        nonlocal failed
        failed = True
        print(f"FAIL {reason}")

    try:
        with tempfile.TemporaryDirectory() as root:
            check(Path(root).resolve(), fail)
    except Exception:
        fail("check-error")
    print(f"{'FAIL' if failed else 'PASS'} npp_artifact_path_safety")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
