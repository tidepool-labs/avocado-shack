#!/usr/bin/env python3
"""Shard unittest discovery without changing its pattern, recursion or load_tests hooks.

Each worker discovers the same suite and runs its round-robin subset of top-level
suites. Reports are buffered and printed whole so mergegate's FAIL/ERROR header
parsing sees the original unittest output, never interleaved shard output.
Each shard gets its own empty TMPDIR (like hosted ci_shards.py workers), so a
test that lists the temp directory before and after never sees a sibling
shard's scratch. This runner is also the attended release's staging step.

Usage: python3 hass/tests/run_parallel.py [--jobs N] [--list]
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parents[1]


def suites():
    """Keep discovery's actual suites, including package/module load_tests results."""
    return list(unittest.TestLoader().discover(str(TESTS), top_level_dir=str(ROOT)))


def shard(items, n):
    """Round-robin whole suites to preserve module/class fixture boundaries."""
    out = [[] for _ in range(n)]
    for i, item in enumerate(items):
        out[i % n].append(item)
    return [group for group in out if group]


def test_ids(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from test_ids(test)
        else:
            yield test.id()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=int(os.environ.get("HASS_TEST_JOBS") or 0))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--shard", type=int, help=argparse.SUPPRESS)
    a = ap.parse_args()
    discovered = suites()
    if a.list:
        print("\n".join(test_ids(discovered)))
        return 0
    if not discovered:
        print("no hass/tests test*.py suites found", file=sys.stderr)
        return 1
    jobs = a.jobs or min(6, os.cpu_count() or 1)
    jobs = max(1, min(jobs, len(discovered)))
    groups = shard(discovered, jobs)
    if a.shard is not None:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(groups[a.shard]))
        return 0 if result.wasSuccessful() else 1
    print(f"hass tests: {len(discovered)} suites in {len(groups)} parallel shards", flush=True)
    t0 = time.time()
    procs = []
    # Short names (as hosted ci_shards.py uses): a shard's TMPDIR is only
    # "/hpXXXXXXXX/N" longer than the inherited one. Tests that bind Unix sockets
    # under TMPDIR bind a relative name, so they do not depend on its length.
    with tempfile.TemporaryDirectory(prefix="hp") as tmp:
        for i, group in enumerate(groups):
            log = os.path.join(tmp, f"shard{i}.log")
            shard_tmp = os.path.join(tmp, str(i))
            os.mkdir(shard_tmp, 0o700)
            with open(log, "wb") as f:
                # Keep stdout/stderr in real order for mergegate's header adjacency.
                p = subprocess.Popen(
                    [sys.executable, "-u", str(Path(__file__).resolve()),
                     "--jobs", str(jobs), "--shard", str(i)],
                    cwd=str(ROOT), stdout=f, stderr=subprocess.STDOUT,
                    env=dict(os.environ, TMPDIR=shard_tmp),
                )
            procs.append((i, group, p, log))
        rc = 0
        for i, group, p, log in procs:
            p.wait()
            if p.returncode != 0:
                rc = 1
        for i, group, p, log in procs:
            print(f"\n===== shard {i}: {len(group)} suites, exit {p.returncode} =====", flush=True)
            with open(log, "rb") as fh:
                sys.stdout.buffer.write(fh.read())
            sys.stdout.buffer.flush()
    print(f"\nhass tests: {len(groups)} shards finished in {time.time()-t0:.0f}s, exit {rc}", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
