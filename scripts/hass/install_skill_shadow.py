#!/usr/bin/env python3
"""Check skill precedence in operator-listed roots, without modifying them."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat


LABEL = re.compile(r"[A-Za-z0-9_-]+")
SHA256 = re.compile(r"[0-9a-fA-F]{64}")


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse messages can include raw paths or other private arguments.
        super().error("invalid arguments (see --help)")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def read_roster(path):
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError
    roster = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    if not isinstance(roster, dict) or not roster:
        raise ValueError
    return roster


def mode(path):
    try:
        return path.lstat().st_mode
    except FileNotFoundError:
        return 0


def root_entries(raw, skills, fail):
    if not isinstance(raw, str) or "\x00" in raw:
        return None, "bad-roots"
    if not raw.startswith("/"):
        return None, "not-absolute"
    # Check the roster spelling before Path can discard a dot component.
    if any(part in (".", "..") for part in raw.split("/")):
        return None, "bad-roots"
    root = Path(raw)
    try:
        # Check top-down so even a normal directory below a link is refused.
        # This is point-in-time evidence, not an attestation of loader behavior.
        for component in (*reversed(root.parents), root):
            component_mode = mode(component)
            if stat.S_ISLNK(component_mode):
                return None, "symlink"
            if not stat.S_ISDIR(component_mode):
                return None, "bad-roots"
        entries = [root]
        for entry in root.iterdir():
            entry_mode = mode(entry)
            if stat.S_ISDIR(entry_mode):
                entries.append(entry)
            elif stat.S_ISLNK(entry_mode) and entry.name not in skills:
                # Only real directories are scanned as categories. A link
                # named for a requested skill is already flagged by scan().
                fail("symlink")
        return entries, None
    except (OSError, ValueError):
        pass
    return None, "bad-roots"


def scan(entries, skill, fail):
    matches = []
    incomplete = False
    for parent in entries:
        directory = parent / skill
        try:
            directory_mode = mode(directory)
            if stat.S_ISLNK(directory_mode):
                fail("symlink")
                incomplete = True
            elif stat.S_ISDIR(directory_mode):
                leaf = directory / "SKILL.md"
                leaf_mode = mode(leaf)
                if stat.S_ISREG(leaf_mode):
                    matches.append(leaf)
                elif leaf_mode:
                    fail("symlink" if stat.S_ISLNK(leaf_mode) else "bad-roots")
                    incomplete = True
        except (OSError, ValueError):
            fail("bad-roots")
            incomplete = True
    return matches, incomplete


def check_skill(profile, skill, roots, expected, fail):
    key = f"{profile} {skill}"
    seen = False
    incomplete = False
    for index, entries in enumerate(roots):
        if entries is None:
            incomplete = True
            continue
        matches, uncertain = scan(entries, skill, fail)
        incomplete |= uncertain
        if len(matches) > 1:
            fail(f"ambiguous {key}")
        if seen:
            for _ in matches:
                fail(f"shadow {key} root[{index}]")
        elif len(matches) == 1 and not incomplete:
            try:
                with matches[0].open("rb") as source:
                    digest = hashlib.file_digest(source, "sha256").hexdigest()
            except OSError:
                fail("bad-roots")
            else:
                print(f"{key} winner root[{index}] sha256 {digest[:12]}")
                if expected is not None and digest != expected:
                    fail(f"sha-mismatch {key}")
        seen |= bool(matches)
    if not seen and not incomplete:
        fail(f"missing {key}")


def main(argv=None):
    parser = Parser(prog="install_skill_shadow.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--roots", required=True, type=Path,
                        help="JSON object mapping profiles to absolute roots, highest precedence first")
    parser.add_argument("--skill", action="append", required=True, metavar="NAME")
    parser.add_argument("--expect-sha256", action="append", default=[], metavar="NAME=HEX")
    args = parser.parse_args(argv)
    failed = False

    def fail(reason):
        nonlocal failed
        failed = True
        print(f"FAIL {reason}")

    skills = list(dict.fromkeys(args.skill))
    for skill in skills:
        if not LABEL.fullmatch(skill):
            fail("bad-label")
    skills = [skill for skill in skills if LABEL.fullmatch(skill)]
    expected = {}
    for pin in args.expect_sha256:
        name, sep, digest = pin.partition("=")
        if sep and not LABEL.fullmatch(name):
            fail("bad-label")
        elif not sep or name not in skills or not SHA256.fullmatch(digest) or name in expected:
            fail("bad-roots")
        else:
            expected[name] = digest.lower()

    try:
        roster = read_roster(args.roots)
    except (OSError, ValueError, RecursionError):
        fail("bad-roots")
        roster = {}
    for profile, raw_roots in roster.items():
        if not LABEL.fullmatch(profile):
            fail("bad-label")
            continue
        if not isinstance(raw_roots, list):
            fail("bad-roots")
            continue
        roots = []
        for raw in raw_roots:
            entries, reason = root_entries(raw, skills, fail)
            if reason:
                fail(reason)
            roots.append(entries)
        for skill in skills:
            check_skill(profile, skill, roots, expected.get(skill), fail)
    print(f"{'FAIL' if failed else 'PASS'} install_skill_shadow")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
