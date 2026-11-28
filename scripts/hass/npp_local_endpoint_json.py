#!/usr/bin/env python3
"""Check the local interpreter's URL and JSON rules with offline fixtures."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import interpreter_local  # noqa: E402


CASES = [
    ("url", "http://127.0.0.1:11434"),
    ("url", "http://localhost:11434/"),
    ("url", "http://[::1]:8080"),
    ("url", "https://127.0.0.1:11434"),
    ("url", "http://example.com:11434"),
    ("url", "http://user@127.0.0.1:11434"),
    ("url", "http://127.0.0.1:0"),
    ("url", "http://127.0.0.1:11434/v1"),
    ("url", "http://127.0.0.1:11434?x=1"),
    ("json", '{"op": "product.add", "n": 2}'),
    ("json", '{"n": 1e999}'),
    ("json", '{"n": NaN}'),
    ("json", '{"a": 1, "a": 2}'),
    ("json", '{"s": "\\ud800"}'),
]
MUST_REFUSE = (3, 4, 5, 6, 7, 8, 10, 11, 12, 13)
EXPECTED = (
    "case 0 url=ok:'http://127.0.0.1:11434'",
    "case 1 url=ok:'http://localhost:11434'",
    "case 2 url=ok:'http://[::1]:8080'",
    "case 3 url=refused",
    "case 4 url=refused",
    "case 5 url=refused",
    "case 6 url=refused",
    "case 7 url=refused",
    "case 8 url=refused",
    "case 9 json=ok:{'op': 'product.add', 'n': 2}",
    "case 10 json=refused",
    "case 11 json=refused",
    "case 12 json=refused",
    "case 13 json=refused",
)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False
    for i, (kind, value) in enumerate(CASES):
        check = interpreter_local.check_url if kind == "url" else interpreter_local._strict
        refused = False
        try:
            result = check(value)
        except ValueError:
            refused = True
            detail = "refused"
        except Exception:
            print("FAIL check-error")
            failed = True
            break
        else:
            detail = f"ok:{result!r}"

        line = f"case {i} {kind}={detail}"
        print(line)
        if i in MUST_REFUSE and not refused:
            print(f"FAIL unsafe-endpoint-or-json {i}")
            failed = True
        if line != EXPECTED[i]:
            print(f"FAIL endpoint-changed {i}")
            failed = True

    if failed:
        print("FAIL npp_local_endpoint_json")
        return 1
    print("PASS npp_local_endpoint_json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
