#!/usr/bin/env python3
"""Count NPP invariant violations in a settled copy of a Hass state directory."""

import argparse
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.npp.job import ACTIVE  # noqa: E402


STORE = "conversation.sqlite3"
NOT_SQLITE = f"not-sqlite {STORE}"
TOOL = "npp_state_invariants"


class StateError(Exception):
    """A fixed reason that can be reported without exposing the input."""


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's original diagnostic can echo an unrecognized private path.
        super().error("invalid arguments; see --help")


def _temp_candidates():
    for name in ("TMPDIR", "TEMP", "TMP"):
        if value := os.environ.get(name):
            yield value
    yield from ("/tmp", "/var/tmp", "/usr/tmp")
    yield os.getcwd()


def _temp_parent(state):
    source = os.path.realpath(state)
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.commonpath((source, parent)) != source
                and os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)):
            return parent
    raise StateError("temp-unavailable")


def _snapshot_report(state):
    """Open only the private copy, including any pending WAL or journal."""
    try:
        if not stat.S_ISDIR(state.lstat().st_mode):
            raise StateError("no-state")
    except OSError:
        raise StateError("no-state") from None

    sources = []
    try:
        for suffix in ("", "-wal", "-journal"):
            source = state / (STORE + suffix)
            try:
                mode = source.lstat().st_mode
            except FileNotFoundError:
                if not suffix:
                    raise StateError("no-state") from None
                continue
            if not stat.S_ISREG(mode):
                raise StateError(NOT_SQLITE)
            sources.append(source)
    except OSError:
        raise StateError(NOT_SQLITE) from None

    try:
        temporary = tempfile.TemporaryDirectory(dir=_temp_parent(state))
    except OSError:
        raise StateError("temp-unavailable") from None

    try:
        with temporary as directory:
            snapshot = Path(directory)
            for source in sources:
                shutil.copyfile(source, snapshot / source.name)
            with closing(sqlite3.connect(snapshot / STORE)) as db:
                db.execute("PRAGMA query_only=ON")
                return _report(db)
    except (OSError, sqlite3.Error):
        raise StateError(NOT_SQLITE) from None


def _report(db):
    tables = {name for (name,) in db.execute("""
        SELECT name FROM sqlite_master WHERE type = 'table'
        AND name IN ('npp_jobs', 'npp_versions', 'npp_approvals', 'npp_questions', 'drafts')
    """)}
    if "npp_jobs" not in tables:
        raise StateError("no-npp-tables")
    if not {"npp_versions", "npp_approvals", "npp_questions"} <= tables:
        raise StateError(NOT_SQLITE)

    def count(sql):
        return db.execute(sql).fetchone()[0]

    totals = {
        "jobs": count("SELECT COUNT(*) FROM npp_jobs"),
        "open": count("SELECT COUNT(*) FROM npp_jobs WHERE closed_at IS NULL"),
        "versions": count("SELECT COUNT(*) FROM npp_versions"),
        "approvals": count("SELECT COUNT(*) FROM npp_approvals"),
    }
    # The job's approval_row is a conversation draft key, not an NPP approval ID.
    draft_match = ("AND NOT EXISTS (SELECT 1 FROM drafts d WHERE d.row_id = j.approval_row)"
                   if "drafts" in tables else "")
    findings = {
        "approval-undelivered": count("""
            SELECT COUNT(*) FROM npp_approvals a WHERE NOT EXISTS (
                SELECT 1 FROM npp_versions v WHERE v.job_id = a.job_id AND v.n = a.n
                AND v.delivered_at IS NOT NULL)
        """),
        "approval-outbox-mismatch": count("""
            SELECT COUNT(*) FROM npp_approvals a WHERE EXISTS (
                SELECT 1 FROM npp_versions v WHERE v.job_id = a.job_id AND v.n = a.n
                AND v.outbox_id IS NOT a.outbox_id)
        """),
        "approval-row-dangling": count(f"""
            SELECT COUNT(*) FROM npp_jobs j WHERE j.approval_row IS NOT NULL {draft_match}
        """),
        "current-version-missing": count("""
            SELECT COUNT(*) FROM npp_jobs j WHERE j.current_version IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM npp_versions v WHERE v.job_id = j.job_id AND v.n = j.current_version)
        """),
        "delivered-without-card": count("""
            SELECT COUNT(*) FROM npp_versions WHERE delivered_at IS NOT NULL AND card_png_sha IS NULL
        """),
        "approved-without-draft": count("""
            SELECT COUNT(*) FROM npp_versions WHERE state = 'approved' AND draft_hash IS NULL
        """),
        "over-two-questions": count("""
            SELECT COUNT(*) FROM (
                SELECT asked_outbox_id FROM npp_questions GROUP BY asked_outbox_id HAVING COUNT(*) > 2)
        """),
        "state-closed-mismatch": count(f"""
            SELECT COUNT(*) FROM npp_jobs WHERE (closed_at IS NULL) IS NOT (state IN ({ACTIVE}))
        """),
    }
    return totals, findings


def main(argv=None):
    parser = PrivateParser(prog=f"{TOOL}.py", description=__doc__)
    parser.add_argument("--state", required=True, type=Path, metavar="DIR", help="settled state copy")
    args = parser.parse_args(argv)
    try:
        totals, findings = _snapshot_report(args.state)
    except StateError as error:
        reasons = [str(error)]
    else:
        for name, total in totals.items():
            print(f"{name} {total}")
        reasons = [f"{name} {total}" for name, total in findings.items() if total]
    for reason in reasons:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if reasons else 'PASS'} {TOOL}")
    return int(bool(reasons))


if __name__ == "__main__":
    sys.exit(main())
