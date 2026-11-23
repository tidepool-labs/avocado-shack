#!/usr/bin/env python3
"""Report differences and findings for a proposed maker sources.json, offline."""

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.claims import fold  # noqa: E402


LABEL = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")


class ReviewParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse's default diagnostic can echo unexpected paths and values.
        super().error("invalid arguments or makers file; see --help")


def reject_constant(_value):
    raise ValueError("not a JSON number")


def read_object(path):
    try:
        # Refuse a symlink at open time and never block on a named pipe.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, encoding="utf-8") as stream:
            if stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                value = json.load(stream, parse_constant=reject_constant)
                if isinstance(value, dict):
                    return value
    except (OSError, ValueError, RecursionError):
        pass
    return None


def domain_form(domain):
    labels = domain.split(".")
    if len(labels) < 2 or not all(LABEL.fullmatch(label) for label in labels):
        return False
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        return True
    return False


def entry_pairs(entries):
    # Only these two fields belong in the report, not the rest of each entry.
    return {(entry["maker"], entry["domain"]) for entry in entries
            if isinstance(entry, dict) and all(
                isinstance(entry.get(key), str) and entry[key] for key in ("maker", "domain")
            )}


def deny_domains(document):
    values = document.get("deny_domains")
    return {value for value in values if isinstance(value, str)} if isinstance(values, list) else set()


def known_makers(makers):
    names = {fold(key) for key in makers}
    for record in makers.values():
        if isinstance(record, dict) and isinstance(record.get("name"), str):
            names.add(fold(record["name"]))
    return names


def findings(document, denied, known):
    shape = document.get("allowlist_entry_shape")
    seen = set()
    for i, entry in enumerate(document["allowlist"]):
        if not isinstance(entry, dict):
            yield f"entry-shape {i}"
            continue
        if (not isinstance(shape, dict) or entry.keys() != shape.keys()
                or not all(isinstance(value, str) and value for value in entry.values())
                or entry.get("added_by") != "G"):
            yield f"entry-shape {i}"
        domain = entry.get("domain")
        if isinstance(domain, str):
            if not domain_form(domain):
                yield f"domain-form {i}"
            elif any(label.startswith("xn--") for label in domain.split(".")):
                yield f"domain-punycode {i}"
            if any(domain == suffix or domain.endswith("." + suffix) for suffix in denied):
                yield f"domain-denied {i}"
        maker = entry.get("maker")
        if isinstance(maker, str) and maker:
            name = fold(maker)
            if isinstance(domain, str) and domain:
                pair = (name, domain)
                if pair in seen:
                    yield f"duplicate-entry {i}"
                seen.add(pair)
            if known is not None and name not in known:
                yield f"maker-unknown {i}"


def same_json(left, right):
    # Python treats booleans as numbers; JSON does not, even inside containers.
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(same_json(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(same_json(a, b) for a, b in zip(left, right))
    return left == right


def report_changes(current, proposed, old_denied, denied, emit):
    old_pairs = entry_pairs(current["allowlist"])
    pairs = entry_pairs(proposed["allowlist"])
    for maker, domain in sorted(pairs - old_pairs):
        emit("allowlist-added", maker, domain)
    for maker, domain in sorted(old_pairs - pairs):
        emit("allowlist-removed", maker, domain)
    for domain in sorted(denied - old_denied):
        emit("deny-added", domain)
    for domain in sorted(old_denied - denied):
        emit("deny-removed", domain)
    for key in sorted((current.keys() | proposed.keys()) - {"allowlist", "deny_domains"}):
        if key not in current or key not in proposed or not same_json(current[key], proposed[key]):
            emit("changed-key", key)


def main(argv=None):
    parser = ReviewParser(prog="npp_sources_review.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--proposed", required=True, type=Path)
    parser.add_argument("--makers", type=Path, help="optional makers.json for name checks")
    args = parser.parse_args(argv)

    current = read_object(args.current)
    proposed = read_object(args.proposed)
    unreadable = []
    for role, document in (("current", current), ("proposed", proposed)):
        if document is None or not isinstance(document.get("allowlist"), list):
            unreadable.append(f"unreadable {role}")
    if unreadable:
        for reason in unreadable:
            print(f"FAIL {reason}")
        print("FAIL npp_sources_review")
        return 1
    assert current is not None and proposed is not None

    known = None
    if args.makers is not None:
        makers = read_object(args.makers)
        if makers is None or not isinstance(makers.get("makers"), dict):
            parser.error("invalid makers file")
        known = known_makers(makers["makers"])

    paths = {str(path.absolute()) for path in (args.current, args.proposed, args.makers)
             if path is not None}

    def emit(kind, *fields):
        line = " ".join((kind, *fields))
        for path in sorted(paths, key=len, reverse=True):
            line = line.replace(path, "[redacted]")
        # Keep malformed report fields from forging lines or terminal controls.
        print("".join(c if c.isprintable() else ascii(c)[1:-1] for c in line))

    denied = deny_domains(proposed)
    report_changes(current, proposed, deny_domains(current), denied, emit)
    print(f"entries {len(proposed['allowlist'])}")
    failed = False
    for reason in findings(proposed, denied, known):
        failed = True
        print(f"FAIL {reason}")
    print(f"{'FAIL' if failed else 'PASS'} npp_sources_review")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
