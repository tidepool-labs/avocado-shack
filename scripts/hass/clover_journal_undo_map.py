#!/usr/bin/env python3
"""Count applied till changes and their undos from a private journal copy."""

import argparse
from collections import Counter
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.clover.drafts import KINDS


REPORT = "clover_journal_undo_map"
STORE = "journal.sqlite3"


class Finding(Exception):
    """A fixed, safe-to-print reason; never wrap raw exception text."""


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's diagnostics can quote arbitrary input arguments.
        super().error("expected --state DIR (see --help)")


def _temp_candidates():
    return (
        *(os.environ[key] for key in ("TMPDIR", "TEMP", "TMP") if os.environ.get(key)),
        "/tmp", "/var/tmp", "/usr/tmp", os.getcwd(),
    )


def _temp_parent(*input_dirs):
    inputs = [os.path.realpath(directory) for directory in input_dirs]
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)
                and all(os.path.commonpath((parent, source)) != source for source in inputs)):
            return parent
    raise Finding("temp-unavailable")


def _present_as(path, predicate, reason):
    try:
        if predicate(path.lstat().st_mode):
            return True
    except FileNotFoundError:
        return False
    except (OSError, ValueError):
        pass
    raise Finding(reason)


def _snapshot_rows(store, state):
    """Read only the byte copy; SQLite may recover or create sidecars there."""
    if not _present_as(store, stat.S_ISREG, "unsafe-state"):
        return None
    reason = f"not-sqlite {store.name}"
    sources = [store]
    for suffix in ("-wal", "-journal"):
        sidecar = store.with_name(store.name + suffix)
        if _present_as(sidecar, stat.S_ISREG, reason):
            sources.append(sidecar)

    parent = _temp_parent(state, store.parent)
    try:
        temporary = tempfile.TemporaryDirectory(dir=parent)
    except OSError:
        raise Finding("temp-unavailable") from None
    try:
        with temporary as directory:
            copy = Path(directory) / store.name
            for source in sources:
                shutil.copyfile(source, copy.with_name(source.name))
            with closing(sqlite3.connect(copy)) as db:
                db.execute("PRAGMA query_only=ON")
                return db.execute("SELECT draft, status FROM changes").fetchall()
    except (OSError, sqlite3.Error):
        raise Finding(reason) from None


def _reject_constant(_token):
    raise ValueError("not a JSON constant")


def _report(rows):
    all_ids = set()
    applied = []
    bad = 0
    for raw, status in rows:
        try:
            draft = json.loads(raw, parse_constant=_reject_constant)
        except (ValueError, TypeError, RecursionError):
            draft = None
        if not isinstance(draft, dict) or not all(
            isinstance(draft.get(key), str) for key in ("kind", "change_id")
        ):
            bad += 1
            continue
        all_ids.add(draft["change_id"])
        if status == "applied":
            applied.append(draft)

    kinds = Counter(draft["kind"] for draft in applied)
    targets = Counter(draft["undo_of"] for draft in applied if isinstance(draft.get("undo_of"), str))
    originals = [draft for draft in applied if draft.get("undo_of") is None]
    first_counts = 0
    for draft in originals:
        before = draft.get("before")
        if (draft["kind"] == "set_stock" and isinstance(before, dict)
                and "stock" in before and before["stock"] is None):
            first_counts += 1

    print(f"applied {len(applied)}")
    for kind in KINDS:
        if kinds[kind]:
            print(f"applied-kind {kind} {kinds[kind]}")
    other = sum(count for kind, count in kinds.items() if kind not in KINDS)
    if other:
        print(f"applied-kind other {other}")
    print(f"undo-applied {sum(targets.values())}")
    print(f"undone {sum(draft['change_id'] in targets for draft in originals)}")
    print(f"first-count {first_counts}")

    return [f"{reason} {count}" for reason, count in (
        ("bad-draft", bad),
        ("orphan-undo", sum(count for target, count in targets.items() if target not in all_ids)),
        ("double-undo", sum(count > 1 for count in targets.values())),
    ) if count]


def main(argv=None):
    parser = PrivateParser(prog=REPORT, description=__doc__)
    parser.add_argument("--state", required=True, type=Path, metavar="DIR", help="state copy directory")
    state = parser.parse_args(argv).state
    clover = state / "clover"
    findings = []
    try:
        if not _present_as(state, stat.S_ISDIR, "unsafe-state"):
            raise Finding("unsafe-state")
        rows = (_snapshot_rows(clover / STORE, state)
                if _present_as(clover, stat.S_ISDIR, "unsafe-state") else None)
        if rows is None:
            print("journal absent")
        else:
            findings = _report(rows)
    except Finding as finding:
        findings = [str(finding)]

    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} {REPORT}")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
