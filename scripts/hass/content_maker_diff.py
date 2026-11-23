#!/usr/bin/env python3
"""Report maker additions, removals and changed fields without showing values."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.content_model import MAKER_FIELDS


MAKERS_PATH = "hass/content/makers.json"
FIELDS = MAKER_FIELDS + ("hidden",)
MISSING = object()


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default diagnostics can echo a supplied path or value.
        super().error("invalid arguments; see --help")


def commit_id(value):
    if not re.fullmatch(r"[0-9a-f]{7,40}", value):
        raise argparse.ArgumentTypeError("expected 7–40 lowercase hexadecimal digits")
    return value


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], shell=False, capture_output=True,
        # Do not fetch missing objects if pointed at a partial clone.
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": ""},
    )


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def reject_constant(_value):
    raise ValueError("non-JSON number")


def read_makers(repo, sha, side, findings):
    source = f"{sha}:{MAKERS_PATH}"
    if git(repo, "cat-file", "-e", source).returncode:
        findings.append(f"makers-absent {side}")
        return None
    blob = git(repo, "show", source)
    if blob.returncode:
        findings.append("git-error")
        return None
    try:
        document = json.loads(blob.stdout.decode("utf-8"), object_pairs_hook=unique_object,
                              parse_constant=reject_constant)
        if isinstance(document, dict) and isinstance(document.get("makers"), dict):
            return document["makers"]
    except (ValueError, RecursionError):
        pass
    findings.append(f"bad-json {side}")
    return None


def changed_fields(old, new):
    # This is a field projection, not full catalog validation. Non-object
    # entries have no named fields; absent fields are distinct from JSON null.
    old = old if isinstance(old, dict) else {}
    new = new if isinstance(new, dict) else {}
    fields = []
    for field in FIELDS:
        before, after = old.get(field, MISSING), new.get(field, MISSING)
        if type(before) is not type(after) or before != after:
            fields.append(field)
    return fields


def report(before, after, allowed, findings):
    added = after.keys() - before.keys()
    print(f"makers-from {len(before)}")
    print(f"makers-to {len(after)}")
    print(f"added {len(added)}")
    for key in sorted(added):
        print(f"added {key}")

    removed = origins = 0
    for key in sorted(before):
        if key not in after:
            if key in allowed:
                print(f"allowed {key}")
            else:
                print(f"removed {key}")
                removed += 1
            continue
        fields = changed_fields(before[key], after[key])
        if fields:
            if key in allowed:
                print(f"allowed {key}")
            else:
                print(f"changed {key} {','.join(fields)}")
                origins += int("place" in fields or "url" in fields)
    if removed:
        findings.append(f"maker-removed {removed}")
    if origins:
        findings.append(f"origin-changed {origins}")


def compare(repo, revisions, allowed, findings):
    if repo.is_symlink() or not repo.is_dir():
        findings.append("unsafe-repo")
        return
    if git(repo, "rev-parse", "--git-dir").returncode:
        findings.append("not-a-repo")
        return
    commits = []
    for side, rev in zip(("from", "to"), revisions):
        result = git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
        if result.returncode == 1:
            findings.append(f"bad-commit {side}")
        elif result.returncode:
            findings.append("git-error")
        else:
            commits.append(result.stdout.decode("ascii").strip())
    if findings:
        return
    ancestry = git(repo, "merge-base", "--is-ancestor", *commits).returncode
    if ancestry:
        findings.append("not-ancestor" if ancestry == 1 else "git-error")
        return

    before, after = (read_makers(repo, sha, side, findings)
                     for side, sha in zip(("from", "to"), commits))
    if before is not None and after is not None:
        report(before, after, allowed, findings)


def main(argv=None):
    parser = ArgumentParser(
        prog="content_maker_diff.py", description=__doc__, allow_abbrev=False,
        epilog="Compares FROM and TO states, not the commit footprint. "
               "A value changed and changed back between commits is not reported.",
    )
    parser.add_argument("--repo", required=True, type=Path, help="local Git clone")
    parser.add_argument("--from", required=True, dest="start", type=commit_id, metavar="REV")
    parser.add_argument("--to", required=True, dest="end", type=commit_id, metavar="REV")
    parser.add_argument("--allow", action="append", default=[], metavar="KEY",
                        help="allow an expected changed or removed maker key (repeatable)")
    args = parser.parse_args(argv)
    findings = []
    try:
        compare(args.repo, (args.start, args.end), set(args.allow), findings)
    except (OSError, UnicodeError):
        findings.append("git-error")
    for reason in dict.fromkeys(findings):
        print(f"FAIL {reason}")
    print("FAIL content_maker_diff" if findings else "PASS content_maker_diff")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
