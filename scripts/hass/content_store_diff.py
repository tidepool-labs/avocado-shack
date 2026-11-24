#!/usr/bin/env python3
"""Compare store.json at FROM and TO. This is a state comparison, not a
footprint check: a value changed and changed back is not reported.
"""

import argparse
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

STORE_PATH = "hass/content/store.json"
FACT_FIELDS = ("name", "streetAddress", "town", "hours", "phone")
MISSING = object()


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse's usual diagnostics can echo paths and other input values.
        super().error("invalid arguments (see --help)")


def revision(value):
    if not re.fullmatch(r"[0-9a-f]{7,40}", value):
        raise argparse.ArgumentTypeError("expected 7 to 40 lowercase hex digits")
    return value


def git(repo, *args):
    # Do not fetch missing objects even if the input is a partial clone.
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="",
               GIT_OPTIONAL_LOCKS="0")
    return subprocess.run(["git", "-C", str(repo), *args], shell=False,
                          capture_output=True, env=env)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def reject_constant(_token):
    raise ValueError("not a JSON number")


def read_store(repo, sha, side):
    spec = f"{sha}:{STORE_PATH}"
    if git(repo, "cat-file", "-e", spec).returncode:
        return None, f"store-absent {side}"
    result = git(repo, "show", spec)
    if result.returncode:
        return None, "git-error"
    try:
        store = json.loads(result.stdout.decode("utf-8"), object_pairs_hook=unique_object,
                           parse_constant=reject_constant, parse_float=Decimal, parse_int=Decimal)
        if isinstance(store, dict):
            return store, None
    except (ValueError, RecursionError, InvalidOperation):
        pass
    return None, f"bad-json {side}"


def differs(left, right):
    # Python's ordinary container equality conflates JSON true/false with 1/0.
    pending = [(left, right)]
    while pending:
        left, right = pending.pop()
        if type(left) is not type(right):
            return True
        if isinstance(left, dict):
            if left.keys() != right.keys():
                return True
            pending.extend((left[key], right[key]) for key in left)
        elif isinstance(left, list):
            if len(left) != len(right):
                return True
            pending.extend(zip(left, right))
        elif left != right:
            return True
    return False


def findings(args):
    repo = args.repo
    try:
        if repo.is_symlink() or not repo.is_dir():
            return ["unsafe-repo"]
    except OSError:
        return ["unsafe-repo"]
    if git(repo, "rev-parse", "--git-dir").returncode:
        return ["not-a-repo"]

    shas = []
    problems = []
    for side, rev in (("from", args.from_rev), ("to", args.to)):
        result = git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
        if result.returncode == 1:
            problems.append(f"bad-commit {side}")
        elif result.returncode:
            problems.append("git-error")
        else:
            shas.append(result.stdout.decode("ascii").strip())
    if problems:
        return problems

    status = git(repo, "merge-base", "--is-ancestor", *shas).returncode
    if status:
        return ["not-ancestor" if status == 1 else "git-error"]

    stores = []
    for side, sha in zip(("from", "to"), shas):
        store, problem = read_store(repo, sha, side)
        if problem:
            problems.append(problem)
        else:
            stores.append(store)
    if problems:
        return problems

    before, after = stores
    unexpected = 0
    for field in FACT_FIELDS:
        if differs(before.get(field, MISSING), after.get(field, MISSING)):
            if field in args.allow:
                print(f"allowed {field}")
            else:
                print(f"fact-changed {field}")
                unexpected += 1
    for key in sorted((before.keys() | after.keys()) - set(FACT_FIELDS)):
        if differs(before.get(key, MISSING), after.get(key, MISSING)):
            print(f"changed {key}")
    return [f"store-fact-changed {unexpected}"] if unexpected else []


def main(argv=None):
    parser = PrivateArgumentParser(prog="content_store_diff.py", description=__doc__,
                                   allow_abbrev=False)
    parser.add_argument("--repo", required=True, type=Path, metavar="CLONE")
    parser.add_argument("--from", required=True, type=revision, dest="from_rev", metavar="REV")
    parser.add_argument("--to", required=True, type=revision, metavar="REV")
    parser.add_argument("--allow", action="append", choices=FACT_FIELDS, default=[])
    args = parser.parse_args(argv)
    try:
        problems = findings(args)
    except (OSError, UnicodeError):
        problems = ["git-error"]
    for problem in problems:
        print(f"FAIL {problem}")
    print("FAIL content_store_diff" if problems else "PASS content_store_diff")
    return int(bool(problems))


if __name__ == "__main__":
    sys.exit(main())
