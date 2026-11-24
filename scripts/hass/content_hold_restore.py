#!/usr/bin/env python3
"""Report products restored from hold between two local catalog snapshots."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass import content_model


PRODUCTS_PATH = "hass/content/products.json"
REV_RE = re.compile(r"[0-9a-f]{7,40}")


def commit_arg(value):
    if not REV_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("expected 7–40 lowercase hexadecimal characters")
    return value


def git(repo, *args):
    # Do not fetch missing objects even if the input is a partial clone.
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="")
    return subprocess.run(["git", "-C", str(repo), *args], shell=False,
                          capture_output=True, env=env)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(_token):
    raise ValueError("non-JSON number")


def endpoint(repo, sha, label):
    target = f"{sha}:{PRODUCTS_PATH}"
    if git(repo, "cat-file", "-e", target).returncode:
        return None, f"products-absent {label}"
    result = git(repo, "show", target)
    if result.returncode:
        return None, "git-error"
    try:
        document = json.loads(result.stdout.decode("utf-8"),
                              object_pairs_hook=unique_object,
                              parse_constant=reject_constant)
    except (ValueError, RecursionError):
        return None, f"bad-json {label}"
    rows = document.get("products") if isinstance(document, dict) else None
    if not isinstance(rows, list):
        return None, f"bad-json {label}"
    return rows, None


def statuses(rows):
    by_id = {}
    malformed = invalid_id = 0
    for row in rows:
        product_id = row.get("id") if isinstance(row, dict) else None
        if not isinstance(product_id, str):
            malformed += 1
        elif not content_model.ID_RE.fullmatch(product_id):
            invalid_id += 1
        else:
            by_id[product_id] = row.get("status")
    return by_id, malformed, invalid_id


def compare(repo, from_rev, to_rev):
    if repo.is_symlink() or not repo.is_dir():
        return ["unsafe-repo"]
    if git(repo, "rev-parse", "--git-dir").returncode:
        return ["not-a-repo"]

    findings = []
    commits = {}
    for label, rev in (("from", from_rev), ("to", to_rev)):
        result = git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
        if result.returncode == 1:
            findings.append(f"bad-commit {label}")
        elif result.returncode:
            return findings + ["git-error"]
        else:
            commits[label] = result.stdout.strip().decode("ascii")
    if findings:
        return findings

    ancestor = git(repo, "merge-base", "--is-ancestor", commits["from"], commits["to"])
    if ancestor.returncode == 1:
        return ["not-ancestor"]
    if ancestor.returncode:
        return ["git-error"]

    snapshots = {}
    for label, sha in commits.items():
        rows, error = endpoint(repo, sha, label)
        if error == "git-error":
            return findings + [error]
        if error:
            findings.append(error)
        else:
            snapshots[label] = statuses(rows)
    if findings:
        return findings

    before, malformed_from, invalid_from = snapshots["from"]
    after, malformed_to, invalid_to = snapshots["to"]
    held_from = {pid for pid, status in before.items() if status == "held"}
    held_to = {pid for pid, status in after.items() if status == "held"}
    restored = sorted(pid for pid in held_from if after.get(pid) == "active")
    hidden = sorted(pid for pid in held_from if after.get(pid) == "hidden")

    print(f"held-from {len(held_from)}")
    print(f"held-to {len(held_to)}")
    for pid in restored:
        print(f"restored {pid} active")
    for pid in hidden:
        print(f"held-to-hidden {pid}")
    print(f"note hold-dropped {len(held_from - after.keys())}")
    print(f"note newly-held {len(held_to - held_from)}")
    print(f"note malformed {malformed_from + malformed_to}")
    print(f"note invalid-id {invalid_from + invalid_to}")
    return [f"restored-from-hold {len(restored)}"] if restored else []


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Compares the file as it is at FROM and TO (endpoint state only, not a "
               "footprint check). Changes reverted between the two commits are not reported.",
    )
    parser.add_argument("--repo", type=Path, required=True, metavar="CLONE")
    parser.add_argument("--from", type=commit_arg, required=True, metavar="REV", dest="from_rev")
    parser.add_argument("--to", type=commit_arg, required=True, metavar="REV", dest="to_rev")
    args = parser.parse_args(argv)
    try:
        findings = compare(args.repo, args.from_rev, args.to_rev)
    except (OSError, ValueError):
        findings = ["git-error"]
    for reason in findings:
        print(f"FAIL {reason}")
    print("FAIL content_hold_restore" if findings else "PASS content_hold_restore")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
