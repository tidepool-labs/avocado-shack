#!/usr/bin/env python3
"""Measure and validate NPP artifacts on an offline media copy without deleting anything."""

import argparse
from contextlib import closing
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.npp.receipt import CARD_RE, JOB_RE, read_artifact  # noqa: E402


STORE = "conversation.sqlite3"


class UsageParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse otherwise echoes unrecognized arguments, including paths.
        super().error("invalid arguments; see --help")


def _temp_candidates():
    return tuple(dict.fromkeys(filter(None, (
        os.environ.get("TMPDIR"), os.environ.get("TEMP"), os.environ.get("TMP"),
        "/tmp", "/var/tmp", "/usr/tmp", os.getcwd(),
    ))))


def _temp_parent(inputs):
    roots = [os.path.realpath(root) for root in inputs]
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)
                and all(os.path.commonpath((parent, root)) != root for root in roots)):
            return parent
    return None


def _snapshot_jobs(state, media):
    """Return (job ids, finding); SQLite only opens the disposable copy."""
    store = state / STORE
    invalid = f"not-sqlite {STORE}"
    try:
        if not stat.S_ISREG(store.lstat().st_mode):
            return None, invalid
        sources = [store]
        for suffix in ("-wal", "-journal"):
            sidecar = store.with_name(STORE + suffix)
            try:
                mode = sidecar.lstat().st_mode
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(mode):
                return None, invalid
            sources.append(sidecar)
    except OSError:
        return None, invalid

    parent = _temp_parent((media, state))
    if parent is None:
        return None, "temp-unavailable"
    try:
        snapshot = tempfile.TemporaryDirectory(dir=parent)
    except OSError:
        return None, "temp-unavailable"
    try:
        with snapshot as directory:
            for source in sources:
                shutil.copyfile(source, Path(directory) / source.name)
            with closing(sqlite3.connect(Path(directory) / STORE)) as connection:
                connection.execute("PRAGMA query_only=ON")
                jobs = {row[0] for row in connection.execute("SELECT job_id FROM npp_jobs")}
    except (OSError, sqlite3.Error):
        return None, invalid
    return jobs, None


def _scan_media(media):
    """Count artifact names and regular-file bytes regardless of validity."""
    npp = media / "npp"
    try:
        for directory in (media, npp):
            if not stat.S_ISDIR(directory.lstat().st_mode):
                return None, "unsafe-npp-dir"
    except FileNotFoundError:
        return None, "no-npp-dir"
    except OSError:
        return None, "unsafe-npp-dir"

    jobs = set()
    receipts = cards = size = no_receipt = other = bad = 0
    try:
        with os.scandir(npp) as folders:
            for job in folders:
                if not re.fullmatch(JOB_RE, job.name):
                    other += 1
                    continue
                if not job.is_dir(follow_symlinks=False):
                    continue
                jobs.add(job.name)
                has_receipt = False
                with os.scandir(job.path) as artifacts:
                    for artifact in artifacts:
                        receipt = artifact.name == "receipt.json"
                        if not receipt and not re.fullmatch(CARD_RE, artifact.name):
                            other += 1
                            continue
                        has_receipt |= receipt
                        receipts += receipt
                        cards += not receipt
                        try:
                            info = artifact.stat(follow_symlinks=False)
                            if stat.S_ISREG(info.st_mode):
                                size += info.st_size
                            read_artifact(Path(artifact.path))
                        except (OSError, ValueError, RecursionError):
                            bad += 1
                no_receipt += not has_receipt
    except OSError:
        return None, "unsafe-npp-dir"

    print(f"jobs {len(jobs)}")
    print(f"receipts {receipts}")
    print(f"cards {cards}")
    print(f"bytes {size}")
    print(f"note no-receipt {no_receipt}")
    print(f"note other-names {other}")
    return jobs, f"bad-artifact {bad}" if bad else None


def main(argv=None):
    parser = UsageParser(prog="npp_media_usage.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--media", required=True, type=Path, metavar="DIR")
    parser.add_argument("--state", type=Path, metavar="DIR")
    args = parser.parse_args(argv)

    folders, finding = _scan_media(args.media)
    failed = finding is not None
    if finding:
        print(f"FAIL {finding}")
    if args.state is not None:
        jobs, finding = _snapshot_jobs(args.state, args.media)
        if finding:
            print(f"FAIL {finding}")
            failed = True
        elif folders is not None and jobs is not None:
            print(f"note folder-without-job {len(folders - jobs)}")
            print(f"note job-without-folder {len(jobs - folders)}")
    print("deletes 0")
    print("FAIL npp_media_usage" if failed else "PASS npp_media_usage")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
