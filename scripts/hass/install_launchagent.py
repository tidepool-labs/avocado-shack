#!/usr/bin/env python3
"""Check two offline LaunchAgent plist copies and the configured forwarder script."""

import argparse
from itertools import zip_longest
from pathlib import Path, PurePosixPath
import plistlib
import sys
from xml.parsers.expat import ExpatError


TOKENS = ("@PYTHON@", "@REPO@", "@CONFIG@", "@LOGDIR@")
PYTHON_FLAGS = ("-B", "-u")  # Supported no-operand flags before the script.
MISSING = object()


def read_plist(path):
    try:
        with path.open("rb") as source:
            document = plistlib.load(source)
    except (OSError, ValueError, plistlib.InvalidFileException, ExpatError,
            IndexError, TypeError, AttributeError, OverflowError, RecursionError):
        return None, "bad-plist"
    if not isinstance(document, dict):
        return None, "not-dict"
    return document, None


def has_template(value):
    if isinstance(value, str):
        return any(token in value for token in TOKENS)
    if isinstance(value, dict):
        return any(has_template(key) or has_template(item) for key, item in value.items())
    if isinstance(value, list):
        return any(map(has_template, value))
    return False


def key_segment(key):
    # Escape delimiters and control characters so one path stays on one line.
    if not isinstance(key, str):
        raise TypeError("plist keys must be strings")
    return "".join(
        "\\" + char if char in "\\.[]\"" else
        char if char.isprintable() else char.encode("unicode_escape").decode("ascii")
        for char in key
    ) or '""'


def changed_paths(before, after, path=""):
    if type(before) is not type(after):
        yield path
    elif isinstance(before, dict):
        for key in sorted(before.keys() | after.keys()):
            if not path and key == "Label":
                continue  # The root label has its own finding.
            segment = key_segment(key)
            child = f"{path}.{segment}" if path else segment
            yield from changed_paths(before.get(key, MISSING), after.get(key, MISSING), child)
    elif isinstance(before, list):
        for index, (old, new) in enumerate(zip_longest(before, after, fillvalue=MISSING)):
            yield from changed_paths(old, new, f"{path}[{index}]")
    elif before != after:
        yield path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--forwarder", required=True, help="absolute Mac path, matched verbatim")
    args = parser.parse_args(argv)

    before, before_error = read_plist(args.before)
    after, after_error = read_plist(args.after)
    findings = [error for error in (before_error, after_error) if error]
    try:
        if any(has_template(doc) for doc in (before, after)):
            findings.append("unrendered-template")
        if before is not None and after is not None:
            label = after.get("Label")
            if not isinstance(label, str) or before.get("Label") != label:
                findings.append("label-changed")
            findings.extend(f"changed {path}" for path in list(changed_paths(before, after)))
    except (TypeError, RecursionError):
        findings.append("bad-plist")

    matches = []
    if not PurePosixPath(args.forwarder).is_absolute():
        findings.append("not-absolute")
    if after is not None:
        arguments = after.get("ProgramArguments")
        if not isinstance(arguments, list):
            arguments = []
        matches = [i for i, value in enumerate(arguments) if value == args.forwarder]
        if not matches:
            findings.append("forwarder-not-loaded")
        elif len(matches) > 1:
            findings.append("forwarder-ambiguous")
        # The template supplies its Python executable in argv[0], without a
        # separate Program override. This checks shape, not executable identity.
        elif (matches[0] == 0 or "Program" in after
              or not isinstance(arguments[0], str)
              or not PurePosixPath(arguments[0]).is_absolute()
              or any(arg not in PYTHON_FLAGS for arg in arguments[1:matches[0]])):
            findings.append("forwarder-not-script")

    if findings:
        for finding in findings:
            print(f"FAIL {finding}")
        print("FAIL install_launchagent")
        return 1
    print(f"forwarder_arg {matches[0]}")
    print("PASS install_launchagent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
