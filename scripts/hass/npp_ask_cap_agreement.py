#!/usr/bin/env python3
"""Check the job runner's question caps against the pinned S3 rules offline."""

import argparse
import ast
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from hass import npp

JOB_PATH = REPO / "hass/npp/job.py"
RULES_ASSET = "hass-missing-info/missing-info.json"


def job_ask_cap():
    """Read the unique SQL count comparison without importing the job runner."""
    tree = ast.parse(JOB_PATH.read_bytes())
    matches = []
    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef) or cls.name != "Jobs":
            continue
        for method in cls.body:
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) or method.name != "finish":
                continue
            for node in ast.walk(method):
                match node:
                    case ast.Compare(
                        left=ast.Subscript(value=ast.Call(args=[ast.Constant(value=sql), *_])),
                        ops=[ast.Lt()], comparators=[ast.Constant(value=cap)],
                    ) if isinstance(sql, str) and "COUNT(*) FROM npp_questions" in sql and type(cap) is int:
                        matches.append(cap)
    return matches[0] if len(matches) == 1 else None


def pinned_caps():
    _, files, replies = npp.assets()
    rules = json.loads(files[RULES_ASSET])
    caps = (rules["max_asks_per_essential"], rules["max_questions"],
            replies["caps"]["max_questions_per_reply"])
    if any(type(cap) is not int for cap in caps):
        raise ValueError("question caps must be integers")
    return caps


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    argv = sys.argv[1:] if argv is None else argv
    parser.parse_args(argv)
    if argv:  # argparse would otherwise accept a bare end-of-options marker.
        parser.error("no arguments accepted")

    findings = []
    try:
        job = job_ask_cap()
    except (OSError, SyntaxError, ValueError, RecursionError):
        job = None
    try:
        asks_rule, questions_rule, caps = pinned_caps()
    except (OSError, KeyError, TypeError, ValueError, RecursionError):
        findings.append("cap-unreadable")
    else:
        if job is None:
            findings.append("cap-unreadable")
        else:
            print(f"cap job={job} rules={asks_rule}")
            if job != asks_rule:
                findings.append("ask-cap-drift")
        print(f"questions caps={caps} rules={questions_rule}")
        if caps != questions_rule:
            findings.append("question-cap-drift")

    for finding in findings:
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} npp_ask_cap_agreement")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
