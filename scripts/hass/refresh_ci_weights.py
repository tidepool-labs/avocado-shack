"""Regenerate Hass shard weights from downloaded successful full-tier CI records.

From the repo root, run `python3 scripts/hass/refresh_ci_weights.py RUN_ID_DIR ...
--output NEW_FILE`. Each input directory must be named for the numeric workflow
run ID and contain its four extracted hass-record-N artifact directories. Use
only runs whose aggregate check passed, and review the new file before replacing
hass/tests/ci_weights.json. No network calls or in-place updates are made.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
from statistics import median
import sys
import unittest

# Running the file directly starts with scripts/hass, not the repository root.
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.tests import ci_shards


def read_run(run_dir):
    """Read uniquely attributable per-module times from one four-shard run."""
    owners, observations = {}, defaultdict(list)
    for i in range(ci_shards.DEFAULT_SHARDS):
        path = run_dir / f"hass-record-{i}" / f"{i}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError(f"{path}: expected a shard object")
        if (record.get("shard") != str(i) or record.get("tier") != "full"
                or record.get("ok") is not True
                or type(record.get("tests_run")) is not int or record["tests_run"] <= 0
                or any(type(record.get(k)) is not int or record[k] != 0
                       for k in ("failures", "errors", "unexpected_successes"))):
            raise ValueError(f"{path}: not a successful full shard")
        modules, timings = record.get("modules"), record.get("module_seconds")
        if not isinstance(modules, list) or not modules or not isinstance(timings, dict) or not timings:
            raise ValueError(f"{path}: missing modules or timings")
        for name in modules:
            if not isinstance(name, str) or not name or name in owners:
                raise ValueError(f"{path}: invalid or repeated shard module {name!r}")
            owners[name] = i
        for name, seconds in timings.items():
            if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
                raise ValueError(f"{path}: invalid timing for {name!r}")
            observations[name].append((i, seconds))
    # The runner keys by the test class's defining module, not the module listed
    # in the plan. A re-export can attach a key to another shard or to both.
    # Discard that observation for this run; other runs can still measure it.
    return {name: entries[0][1] for name, entries in observations.items()
            if len(entries) == 1 and owners.get(name) == entries[0][0]}


def reexported_keys(modules):
    """Defining-module keys that some other listed module also executes.

    The runner's TimedResult files every test under its class's defining module,
    so a module that re-exports another module's TestCase class runs it a second
    time under the defining module's key. When both modules sit on one shard that
    key still looks unique to its owner, yet it holds the doubled time.
    """
    def tests_of(item):
        for test in item:
            if isinstance(test, unittest.TestSuite):
                yield from tests_of(test)
            else:
                yield test

    keys = set()
    for name in modules:
        suite = unittest.defaultTestLoader.loadTestsFromName(ci_shards.PREFIX + name)
        for test in tests_of(suite):
            defining = type(test).__module__
            defining = defining[len(ci_shards.PREFIX):] if defining.startswith(ci_shards.PREFIX) else defining
            if defining != name:
                keys.add(defining)
    return keys


def render_weights(run_dirs, modules, ambiguous):
    """`ambiguous` is reexported_keys(modules); those keys are never weighted."""
    ordered = sorted(run_dirs, key=lambda p: p.name)
    ids = [p.name for p in ordered]
    if (not ids or len(ids) != len(set(ids))
            or any(not name.isascii() or not name.isdecimal() for name in ids)):
        raise ValueError("provide unique numeric GitHub workflow run IDs as directory names")
    active = set(modules) - set(ambiguous)
    samples = defaultdict(list)
    for run_dir in ordered:
        for name, seconds in read_run(run_dir).items():
            if name in active:
                samples[name].append(seconds)
    if not samples:
        raise ValueError("no attributable timings for current test modules")
    seconds = {name: max(1, math.ceil(median(samples[name]))) for name in sorted(samples)}
    measured = (f"GitHub Actions full-tier runs {', '.join(ids)}: median uniquely attributable "
                "module_seconds rounded up (minimum 1); unmeasured modules use the default weight. "
                "Weights balance shards only and never remove coverage.")
    return json.dumps({"version": 1, "measured": measured, "seconds": seconds}, indent=0) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path, metavar="RUN_ID_DIR")
    parser.add_argument("--output", type=Path, required=True, help="new file to create for review")
    args = parser.parse_args()
    try:
        modules = ci_shards.all_modules()
        output = render_weights(args.runs, modules, reexported_keys(modules))
        with args.output.open("x", encoding="utf-8") as file:
            file.write(output)
    except (OSError, ValueError, OverflowError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
