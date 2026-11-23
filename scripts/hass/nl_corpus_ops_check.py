#!/usr/bin/env python3
"""Check expected NL corpus ops against the editor registry offline."""

import argparse
from pathlib import Path
import re
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import nl_eval  # noqa: E402
from hass.content_model import load_and_validate  # noqa: E402
from hass.ops import check_args, load_registry  # noqa: E402


CASE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,40}")


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse may include unrecognized values (including paths) in message.
        super().error("invalid arguments; see --help")


def _has_type(path, predicate):
    try:
        return predicate(path.lstat().st_mode)
    except (OSError, ValueError):
        return False


def _finish(findings):
    for finding in findings:
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} nl_corpus_ops_check")
    return int(bool(findings))


def main(argv=None):
    parser = PrivateParser(prog="nl_corpus_ops_check.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--content", required=True, type=Path, metavar="DIR", help="content copy")
    parser.add_argument("--corpus", default=nl_eval.CORPUS, type=Path, metavar="FILE",
                        help="override the checked-in corpus")
    args = parser.parse_args(argv)
    if not (_has_type(args.content, stat.S_ISDIR) and _has_type(args.corpus, stat.S_ISREG)):
        return _finish(["unsafe-input"])
    try:
        content = load_and_validate(args.content, None)
    except (OSError, ValueError):  # ContentError and decode errors are ValueErrors.
        return _finish(["content-invalid"])
    try:
        corpus = nl_eval.load_corpus(args.corpus)
        registry = load_registry()
    except (nl_eval.EvalError, ImportError, OSError, ValueError):
        # Without a usable registry, the corpus expectations cannot be validated.
        return _finish(["corpus-invalid"])

    calls = missing_required = invalid_ids = 0
    findings = []
    for case in corpus:
        case_id = case["id"]
        suffix = f" {case_id}" if CASE_ID.fullmatch(case_id) else ""
        invalid_ids += not suffix
        reasons = {}
        for call in case["expect"].get("ops", ()):
            calls += 1
            op = registry.get(call["op"])
            if op is None:
                reasons["unknown-op"] = None
                continue
            try:
                problems, missing = check_args(op, call["args"], content.makers, None)
            except TypeError:
                # The current image validator needs a site directory even for
                # a well-formed image path. An uncheckable call is a finding.
                reasons["arg-problem"] = None
            else:
                missing_required += bool(missing)
                if problems:
                    reasons["arg-problem"] = None
        findings.extend(reason + suffix for reason in reasons)

    print(f"cases {len(corpus)}")
    print(f"calls {calls}")
    print(f"missing-required {missing_required}")
    if invalid_ids:
        print(f"note invalid-id {invalid_ids}")
    return _finish(findings)


if __name__ == "__main__":
    sys.exit(main())
