#!/usr/bin/env python3
"""Check a candidate or installed JSON config against its pre-switch backup.

Read-only: does not replace files, verify service state, or authorize install.
Diagnostics use only fixed JSON Pointer paths, never operator-defined keys.
"""

import argparse
from decimal import Decimal, DecimalException
import json
from pathlib import Path
import sys


SWITCHES = ("npp", "houseRender", "photo_polish")


class Refusal(Exception):
    pass


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise Refusal("duplicate JSON key")
        obj[key] = value
    return obj


def _reject_constant(_token):
    raise Refusal("non-JSON number")


def _read(path):
    try:
        return json.loads(
            path.read_bytes().decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            # Avoid rounding away changes, including overflow/underflow in floats.
            parse_float=Decimal,
        )
    except OSError:
        raise Refusal("cannot read input") from None
    except (ValueError, DecimalException, RecursionError):
        raise Refusal("invalid JSON") from None


def _first_difference(expected, actual, path=()):
    if type(expected) is not type(actual):
        return path
    if isinstance(expected, dict):
        for key in sorted(expected.keys() | actual.keys()):
            child = (*path, key)
            if key not in expected or key not in actual:
                return child
            difference = _first_difference(expected[key], actual[key], child)
            if difference is not None:
                return difference
    elif isinstance(expected, list):
        for index, (left, right) in enumerate(zip(expected, actual)):
            difference = _first_difference(left, right, (*path, str(index)))
            if difference is not None:
                return difference
        if len(expected) != len(actual):
            return (*path, str(min(len(expected), len(actual))))
    elif expected != actual:
        return path
    return None


def _pointer(path):
    pointer = "".join("/" + part.replace("~", "~0").replace("/", "~1") for part in path)
    return json.dumps(pointer, ensure_ascii=True)


def _fail(side, reason, path=()):
    print(f"FAIL {side}: {reason} at {_pointer(path)}", file=sys.stderr)
    return 1


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default errors can echo arbitrary argv text.
        self.exit(2, "Usage: install_switch_readback.py --before BACKUP --after CONFIG\n")


def main(argv=None):
    parser = _Parser(description="Verify only the three NPP switches were set to true.", allow_abbrev=False)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        expected = _read(args.before)
    except Refusal as error:
        return _fail("before", error)
    if not isinstance(expected, dict):
        return _fail("before", "expected a JSON object")
    settings = expected.get("settings")
    if not isinstance(settings, dict):
        return _fail("before", "expected a settings object", ("settings",))
    if settings.get("npp", False) is not False:
        return _fail("before", "baseline switch is not off", ("settings", "npp"))
    settings.update(dict.fromkeys(SWITCHES, True))

    try:
        actual = _read(args.after)
    except Refusal as error:
        return _fail("after", error)
    try:
        difference = _first_difference(expected, actual)
    except RecursionError:
        return _fail("after", "config is too deeply nested to compare")
    if difference is not None:
        for key in SWITCHES:
            switch_path = ("settings", key)
            if difference == switch_path:
                return _fail("after", "config differs from the expected edit", switch_path)
        print("FAIL after: unrelated config change", file=sys.stderr)
        return 1
    print("PASS " + " ".join(_pointer(("settings", key)) for key in SWITCHES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
