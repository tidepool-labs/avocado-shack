#!/usr/bin/env python3
"""Report public catalog changes between two local writer commits."""

import argparse
import json
import os
import re
import subprocess


CATALOG = "hass/content/products.json"
# Fields hass/ops/history.py removes when it undoes an added product.
INVERSE_DROPPED = ("available", "available_on")


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's messages can echo arbitrary argument values, including paths.
        super().error("invalid arguments; see --help")


def git(repo, *args):
    # Never fetch missing objects from a partial clone or honor replace refs.
    env = dict(os.environ, GIT_ALLOW_PROTOCOL="", GIT_NO_LAZY_FETCH="1",
               GIT_NO_REPLACE_OBJECTS="1", GIT_OPTIONAL_LOCKS="0")
    return subprocess.run(["git", "-C", repo, *args], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, env=env)


def is_checkout(repo):
    try:
        result = git(repo, "rev-parse", "--is-inside-work-tree")
    except OSError:
        return False
    return result.returncode == 0 and result.stdout == b"true\n"


def is_commit(repo, sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        return False
    result = git(repo, "cat-file", "-t", sha)
    return result.returncode == 0 and result.stdout == b"commit\n"


def reject_constant(_token):
    raise ValueError("non-JSON number")


def reject_repeated_key(pairs):
    # json.loads would keep only the last value of a repeated key; the message names no content.
    keys = [name for name, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("repeated key")
    return dict(pairs)


def read_products(repo, sha):
    spec = f"{sha}:{CATALOG}"
    result = git(repo, "cat-file", "blob", spec)
    if result.returncode:
        exists = git(repo, "cat-file", "-t", spec).returncode == 0
        return None, "bad-content" if exists else "no-content"

    try:
        document = json.loads(result.stdout, parse_constant=reject_constant,
                              object_pairs_hook=reject_repeated_key)
        rows = document.get("products") if isinstance(document, dict) else None
        if not isinstance(rows, list):
            return None, "bad-content"
        products = {}
        for row in rows:
            key = row.get("id") if isinstance(row, dict) else None
            if not isinstance(key, str) or key in products:
                return None, "bad-content"
            # Compare JSON values, ignoring object order but not boolean/number type.
            products[key] = {name: json.dumps(value, sort_keys=True) for name, value in row.items()}
    except (ValueError, RecursionError):
        return None, "bad-content"
    return products, None


def label(value):
    # Even an unusual JSON key must not introduce a new report line.
    return "".join(char if char.isprintable() else ascii(char)[1:-1] for char in value)


def report(before, after):
    added = sorted(after.keys() - before.keys())
    for key in added:
        print(f"added {label(key)}")
    for key in sorted(before.keys() - after.keys()):
        print(f"removed {label(key)}")
    for key in sorted(before.keys() & after.keys()):
        old, new = before[key], after[key]
        fields = [label(name) for name in sorted(old.keys() | new.keys())
                  if old.get(name) != new.get(name)]
        if fields:
            print(f"changed {label(key)} {' '.join(fields)}")
    print(f"added-total {len(added)}")
    return len(added)


def failures(*reasons):
    for reason in reasons:
        print(f"FAIL {reason}")
    print("FAIL pilot_content_diff")
    return 1


def exact_product_errors(before, after, expectation):
    mode, key = expectation
    # Fields are compared in their canonical JSON form, as in the report.
    old, new = before.get(key), after.get(key)
    if mode == "forward":
        if old is not None or (new or {}).get("status") != '"active"':
            yield "expected-product-forward"
    else:
        # history.revert keeps a new product in the writer catalog as its current record with
        # status hidden and its stock word and day (available, available_on) removed.
        expected = None
        if old is not None and old.get("status") == '"active"':
            expected = {name: value for name, value in old.items() if name not in INVERSE_DROPPED}
            expected["status"] = '"hidden"'
        if new is None or new != expected:
            yield "expected-product-inverse"
    if any(before.get(pid) != after.get(pid) for pid in (before.keys() | after.keys()) - {key}):
        yield "other-products-changed"


def main(argv=None):
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--repo", required=True, help="local Git checkout")
    parser.add_argument("--from", dest="from_sha", required=True, metavar="SHA")
    parser.add_argument("--to", dest="to_sha", required=True, metavar="SHA")
    parser.add_argument("--expect-added", type=int, metavar="N", help="check additions count only")
    parser.add_argument("--expect-product", nargs=2, metavar=("MODE", "ID"),
                        help="forward: absent to active; inverse: active to hidden; no other product changes")
    args = parser.parse_args(argv)
    if args.expect_product is not None:
        mode, key = args.expect_product
        if mode not in ("forward", "inverse") or not key:
            parser.error("invalid product expectation")

    if not is_checkout(args.repo):
        return failures("not-git")
    endpoints = (("from", args.from_sha), ("to", args.to_sha))
    errors = [f"bad-commit {side}" for side, sha in endpoints if not is_commit(args.repo, sha)]
    if errors:
        return failures(*errors)
    if git(args.repo, "merge-base", "--is-ancestor", args.from_sha, args.to_sha).returncode:
        return failures("not-ancestor")

    catalogs = []
    for side, sha in endpoints:
        products, reason = read_products(args.repo, sha)
        catalogs.append(products)
        if reason:
            errors.append(f"{reason} {side}")
    if errors:
        return failures(*errors)

    before, after = catalogs
    added = report(before, after)
    if args.expect_added is not None and args.expect_added != added:
        errors.append(f"added-count {added}")
    if args.expect_product is not None:
        errors.extend(exact_product_errors(before, after, args.expect_product))
    if errors:
        return failures(*errors)
    print("PASS pilot_content_diff")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
