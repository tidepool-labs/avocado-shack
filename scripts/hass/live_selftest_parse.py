#!/usr/bin/env python3
"""HASS-LIVE-AUDIT-1: validate the JSON that scripts/hass/live_selftest.sh gets from hass/health.py and hass/inbox.py.

    python3 -B scripts/hass/live_selftest_parse.py health|inbox < OUTPUT

health: the last non-empty line must be one JSON object with a boolean `ok`, a `problems` list of objects that each
carry a string `check`, and ok == (no problems). Prints the sorted, unique check ids on one line (empty line if none).
inbox: one JSON object with integer `pending` and `done` >= 0 and `oldest_pending_minutes` a finite number or null. Prints
`pending oldest done` (oldest as `null` when there is none).
Both modes reject duplicate keys anywhere in the final JSON object.
Exit 0 valid, 3 missing or invalid report (prints the reason only: never the report itself), 2 bad usage.
Counts and check ids only: problem details, messages and paths are never printed.
"""

import json, math, re, sys  # noqa: E401

CHECK_ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def _last_object(text):
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("no report")
    try:
        obj = json.loads(lines[-1], object_pairs_hook=_unique_object)
    except (ValueError, RecursionError):
        raise ValueError("report is not JSON") from None
    if not isinstance(obj, dict):
        raise ValueError("report is not a JSON object")
    return obj


def _count(obj, name):
    v = obj.get(name)
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise ValueError(f"{name} missing or not a count")
    return v


def health(text):
    obj = _last_object(text)
    ok, problems = obj.get("ok"), obj.get("problems")
    if not isinstance(ok, bool):
        raise ValueError("ok missing or not a boolean")
    if not isinstance(problems, list):
        raise ValueError("problems missing or not a list")
    ids = set()
    for p in problems:
        check = p.get("check") if isinstance(p, dict) else None
        if not isinstance(check, str) or not CHECK_ID.fullmatch(check):
            raise ValueError("a problem has no valid check id")
        ids.add(check)
    if ok == bool(problems):
        raise ValueError("ok disagrees with problems")
    return " ".join(sorted(ids))


def inbox(text):
    obj = _last_object(text)
    pending, done = _count(obj, "pending"), _count(obj, "done")
    oldest = obj.get("oldest_pending_minutes")
    if oldest is not None and (
        isinstance(oldest, bool)
        or not isinstance(oldest, (int, float))
        or (isinstance(oldest, float) and not math.isfinite(oldest))
        or oldest < 0
    ):
        raise ValueError("oldest_pending_minutes not a number or null")
    return f"{pending} {'null' if oldest is None else int(oldest)} {done}"


def main(argv):
    if len(argv) != 1 or argv[0] not in ("health", "inbox"):
        print("usage: live_selftest_parse.py health|inbox < OUTPUT", file=sys.stderr)
        return 2
    try:
        print((health if argv[0] == "health" else inbox)(sys.stdin.read()))
    except ValueError as e:
        print(f"invalid {argv[0]} report: {e}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
