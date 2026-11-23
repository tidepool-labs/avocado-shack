#!/usr/bin/env python3
"""Check that recorded edits rebuild earlier templates in a checkout copy."""

import argparse
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import re
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.template_compat import TEMPLATE_EDITS, previous_bytes


REPORT = "template_compat_chain_check"
TEMPLATE_PATH = re.compile(r"hass/templates/[a-z0-9/_-]+\.html")


def read_template(repo, path):
    parts = Path(path).parts
    directory = repo
    # Do not follow symlinks inside the checkout, including directory aliases.
    for part in parts[:-1]:
        directory = directory / part
        if not stat.S_ISDIR(directory.lstat().st_mode):
            return None
    target = directory / parts[-1]
    if not stat.S_ISREG(target.lstat().st_mode):
        return None
    return target.read_bytes()


def check_path(repo, path, links):
    if not TEMPLATE_PATH.fullmatch(path):
        return ["unsafe-input"]
    try:
        data = read_template(repo, path)
    except OSError:
        data = None
    if data is None:
        return [f"missing {path}"]

    currents = {current for current, _ in links}
    heads = currents - {previous for _, previous in links}
    digest = sha256(data).hexdigest()
    findings = []
    if digest not in currents:
        findings.append(f"unrecorded-edit {path}")
    recorded_head = heads == {digest}
    print(f"path {path} current-recorded {'yes' if recorded_head else 'no'}")

    print(f"step 0 {digest[:12]}")
    seen = {digest}
    steps = 0
    while (data := previous_bytes(path, data)) is not None:
        digest = sha256(data).hexdigest()
        if digest in seen:
            break  # A cycle does not rebuild another earlier version.
        seen.add(digest)
        steps += 1
        print(f"step {steps} {digest[:12]}")
    print(f"steps {steps}")
    print(f"recorded {len(links)}")
    if steps < len(links):
        findings.append(f"broken-chain {path} {steps}")
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--repo", type=Path, required=True, help="checkout copy (read only)")
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        parser.error("unrecognized arguments")  # Don't echo input paths.

    try:
        safe_repo = stat.S_ISDIR(args.repo.lstat().st_mode)
    except (OSError, ValueError):
        safe_repo = False

    findings = []
    if not safe_repo:
        findings.append("unsafe-input")
    else:
        by_path = defaultdict(list)
        for path, current, previous, _, _ in TEMPLATE_EDITS:
            by_path[path].append((current, previous))
        for path, links in sorted(by_path.items()):
            findings.extend(check_path(args.repo, path, links))

    # An unprintable path is also reported without exposing its value.
    for reason in dict.fromkeys(findings):
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} {REPORT}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
