#!/usr/bin/env python3
"""Weekly model-drift report over private NPP receipts (design section 4d).

Read-only. For every step seen in valid receipt evidence, print the number of
calls, the calls that returned a model id other than the step's pin in the
given checkout's hass/npp/pins.json, and the returned ids seen. A call that
returned no id is counted but is not drift (as in hass.npp.evidence).

Lines: `step <name> calls=<n> drifted=<n> pinned=<id|-> returned=<ids|->`,
`NOTE bad-receipt <job>`, `NOTE no-evidence <job>`, `NOTE bad-evidence <job>`,
`FAIL unpinned <step>`, then one last line: `PASS npp_drift` (exit 0) or
`FAIL npp_drift <steps>` (exit 1) naming every drifted or unpinned step.
Unusable inputs print `FAIL bad-pins` or `FAIL bad-receipts-dir` (exit 2).
"""

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import re
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.npp import evidence
from hass.npp.receipt import JOB_RE, read_artifact


PINS_MAX = 256 << 10


def _since(value):
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from None


def load_pins(checkout):
    """Return {step: pinned model id} from the checkout; raise ValueError if unusable."""
    with (Path(checkout) / "hass/npp/pins.json").open("rb") as source:
        data = source.read(PINS_MAX + 1)
    if len(data) > PINS_MAX:
        raise ValueError("pins too large")
    steps = json.loads(data).get("steps")
    if not isinstance(steps, dict):
        raise ValueError("pins without steps")
    # A step without a string model id is not pinned.
    return {step: entry["model"] for step, entry in steps.items()
            if isinstance(entry, dict) and isinstance(entry.get("model"), str)}


def read_receipt(path, since):
    """Return (job, evidence doc or None), or None when the receipt is outside --since; raise if bad."""
    job = path.parent.name
    if not re.fullmatch(JOB_RE, job) or path.parent.is_symlink():
        raise ValueError
    row = json.loads(read_artifact(path))
    if row.get("job_id") != job:
        raise ValueError
    if since is not None:
        created = row.get("created_at")
        if type(created) is not str:
            raise ValueError
        moment = datetime.fromisoformat(created)
        if moment.utcoffset() is None:
            raise ValueError
        if moment.date() < since:
            return None
    return job, row.get("evidence")


def report(receipts, pins, since):
    """Return (output lines, failing steps in name order) for the sorted receipt paths."""
    lines, steps = [], {}
    for path in receipts:
        try:
            found = read_receipt(path, since)
        except (OSError, ValueError, TypeError, AttributeError, RecursionError):
            job = path.parent.name
            lines.append("NOTE bad-receipt " + (job if re.fullmatch(JOB_RE, job) else "<invalid-job>"))
            continue
        if found is None:
            continue
        job, doc = found
        if doc is None:  # Receipts written before HRM-11 carry no evidence.
            lines.append("NOTE no-evidence " + job)
            continue
        try:
            problems = evidence.validate(doc)
        except (TypeError, ValueError, AttributeError, RecursionError):
            problems = ["evidence: unreadable"]
        if problems:
            lines.append("NOTE bad-evidence " + job)
            continue
        for model in doc["models"]:
            seen = steps.setdefault(model["step"], dict(calls=0, drifted=0, returned=set()))
            seen["calls"] += 1
            returned = model["returned"]
            if returned is not None:
                seen["returned"].add(returned)
                pinned = pins.get(model["step"])
                if pinned is not None and returned != pinned:
                    seen["drifted"] += 1
    failing = []
    for step in sorted(steps):
        seen = steps[step]
        lines.append(f"step {step} calls={seen['calls']} drifted={seen['drifted']} "
                     f"pinned={pins.get(step, '-')} returned={','.join(sorted(seen['returned'])) or '-'}")
        if step not in pins:
            lines.append("FAIL unpinned " + step)
            failing.append(step)
        elif seen["drifted"]:
            failing.append(step)
    return lines, failing


def main(argv=None):
    parser = argparse.ArgumentParser(description="Weekly model-drift report over private NPP receipts.")
    parser.add_argument("--receipts", required=True, type=Path, help="NPP root containing <job>/receipt.json")
    parser.add_argument("--repo", required=True, type=Path, help="checkout whose hass/npp/pins.json holds the pins")
    parser.add_argument("--since", type=_since, help="inclusive receipt creation day (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    try:
        pins = load_pins(args.repo)
    except (OSError, ValueError, AttributeError, RecursionError):
        print("FAIL bad-pins")
        return 2
    try:
        root = args.receipts.resolve(strict=True)
        if not root.is_dir():
            raise NotADirectoryError
        receipts = sorted(root.glob("*/receipt.json"))
    except OSError:
        print("FAIL bad-receipts-dir")
        return 2
    lines, failing = report(receipts, pins, args.since)
    for line in lines:
        print(line)
    if failing:
        print("FAIL npp_drift " + " ".join(failing))
        return 1
    print("PASS npp_drift")
    return 0


if __name__ == "__main__":
    sys.exit(main())
