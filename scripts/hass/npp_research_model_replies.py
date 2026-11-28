#!/usr/bin/env python3
"""Check S4's extract and verify ports with canned model replies, offline."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hass.npp
from hass.npp import research_hermes


def _ok(text):
    return {"ok": True, "model": "m", "ms": 1, "text": text}


_SUPPORTS = _ok('{"verdict":"supports"}')
CASES = (
    ("verify", _SUPPORTS, 60),
    ("verify", _ok('{"verdict":"supports","x":1}'), 60),
    ("verify", _ok('{"verdict":"supports","verdict":"refutes"}'), 60),
    ("verify", _ok("x" * 16_385), 60),
    ("verify", _ok("not json"), 60),
    ("verify", {"ok": False}, 60),
    ("verify", None, 60),
    ("verify", {"ok": True, "text": 5}, 60),
    ("verify", "str", 60),
    ("verify", _SUPPORTS, 3),
    ("extract", _ok('{"facts": []}'), 60),
    ("extract", _ok('["x"]'), 60),
)
_EXPECTED = {0: "supports", 10: {"facts": []}}
_RECORD_KEYS = {"step", "ok", "model", "ms"}


def _check_case(index, port, reply, seconds):
    count = 0

    def fake(_request):
        nonlocal count
        count += 1
        return reply

    model = research_hermes.Models(hass.npp.assets(), runner=fake)
    result = None
    try:
        if port == "verify":
            result = model.verify("Miners", "nature", "farm", "q", seconds)
        else:
            result = model.extract("Miners", {"https://miners.example/": ["b"]}, seconds)
    except ValueError:
        kind = "valueerror"
    except Exception:
        kind = "other"
    else:
        kind = "none" if result is None else "value"

    # An unexpected exception has no informational outcome; report it below.
    if kind != "other":
        outcome = f"value={json.dumps(result)}" if kind == "value" else kind
        print(f"case {index} {port} {outcome} calls={count}")

    if port == "verify" and index != 0 and kind in {"value", "other"}:
        yield f"unexpected-{kind} {index}"
    if index in _EXPECTED and result != _EXPECTED[index]:
        yield f"ok-lost {index}"
    if index == 9 and count:
        yield "call-made 9"
    if any(not hasattr(record, "keys") or record.keys() != _RECORD_KEYS for record in model.calls):
        yield f"call-record-keys {index}"
    if kind == "other":
        yield "check-error"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.parse_args(argv)
    failed = False
    for index, (port, reply, seconds) in enumerate(CASES):
        try:
            for reason in _check_case(index, port, reply, seconds):
                print(f"FAIL {reason}")
                failed = True
        except Exception:
            # Setup or inspection failed; never print exceptions or skip silently.
            print("FAIL check-error")
            failed = True
    print(f"{'FAIL' if failed else 'PASS'} npp_research_model_replies")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
