#!/usr/bin/env python3
"""Check the waiting Clover link draft against offline copies; print counts only."""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.clover import cache, links, reads, reports


class Finding(Exception):
    """A fixed diagnostic, never an input value or a raw exception."""


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse can echo arbitrary unrecognized arguments, including paths.
        super().error("invalid arguments (see --help)")


def _temp_candidates():
    for key in ("TMPDIR", "TEMP", "TMP"):
        if value := os.environ.get(key):
            yield value
    yield from ("/tmp", "/var/tmp", "/usr/tmp")
    yield os.getcwd()


def _temp_parent(inputs):
    roots = tuple(os.path.realpath(path) for path in inputs)
    for candidate in _temp_candidates():
        parent = os.path.realpath(candidate)
        if (os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)
                and all(os.path.commonpath((parent, root)) != root for root in roots)):
            return parent
    raise Finding("temp-unavailable")


def _snapshot(store, inputs):
    invalid = f"not-sqlite {store.name}"
    try:
        if not stat.S_ISREG(store.lstat().st_mode):
            raise Finding("unsafe-state")
    except FileNotFoundError:
        raise Finding("cache-absent") from None
    except OSError:
        raise Finding("unsafe-state") from None

    files = [store]
    try:
        for suffix in ("-wal", "-journal"):
            sidecar = store.with_name(store.name + suffix)
            try:
                mode = sidecar.lstat().st_mode
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(mode):
                raise Finding(invalid)
            files.append(sidecar)
    except OSError:
        raise Finding(invalid) from None

    try:
        temporary = tempfile.TemporaryDirectory(dir=_temp_parent(inputs))
    except OSError:
        raise Finding("temp-unavailable") from None
    try:
        with temporary as directory:
            scratch = Path(directory)
            for source in files:
                shutil.copyfile(source, scratch / source.name)
            with closing(sqlite3.connect(scratch / store.name)) as db:
                db.execute("PRAGMA query_only=ON")
                rows = db.execute("SELECT id, name, sku FROM items").fetchall()
                meta = dict(db.execute("SELECT key, value FROM meta"))
    except (OSError, sqlite3.Error):
        raise Finding(invalid) from None
    as_of = cache._parse_iso(meta.get("asOf"))
    if as_of is None:
        raise Finding("cache-absent")
    return reads.Snapshot(tuple(SimpleNamespace(id=i, name=n, sku=s) for i, n, s in rows), as_of)


def _read_draft(state):
    folder = state / cache.DIRNAME
    try:
        if not stat.S_ISDIR(state.lstat().st_mode):
            raise Finding("unsafe-state")
        try:
            mode = folder.lstat().st_mode
        except FileNotFoundError:
            return None
        if not stat.S_ISDIR(mode):
            raise Finding("unsafe-state")
    except (OSError, ValueError):
        # Path errors (including a NUL in a programmatic argv) are private.
        raise Finding("unsafe-state") from None
    try:
        draft = json.loads(reports._read_regular(folder / links.DRAFT))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, RecursionError, cache.CacheUnsafe):
        raise Finding("draft-unreadable") from None
    if not (isinstance(draft, dict) and isinstance(draft.get("code"), str)
            and isinstance(draft.get("asOf"), str)
            and isinstance(draft.get("pairs"), dict) and draft["pairs"]):
        raise Finding("draft-unreadable")
    return draft


def _read_links(state):
    # Mirror reports.read_inputs' private-link checks. Its product path is
    # worktree-relative, whereas this CLI takes the copied content directory.
    path = links.table(state)
    try:
        if not cache._private_dir(path.parent, create=False):
            return {}
        try:
            st = path.lstat()
        except FileNotFoundError:
            return {}
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise Finding("unsafe-state")
        saved = json.loads(reports._read_regular(path))
    except (OSError, ValueError, RecursionError, cache.CacheUnsafe):
        raise Finding("unsafe-state") from None
    if not isinstance(saved, dict):
        raise Finding("unsafe-state")
    return saved


def _read_products(folder):
    try:
        content = json.loads(reports._read_regular(folder / "products.json"))
    except (OSError, ValueError, RecursionError, cache.CacheUnsafe):
        raise Finding("unreadable products") from None
    if not isinstance(content, dict) or not isinstance(content.get("products"), list):
        raise Finding("unreadable products")
    return content


def _check(state, content_dir):
    draft = _read_draft(state)
    if draft is None:
        print("draft absent")
        return []
    print(f"pairs {len(draft['pairs'])}")
    saved = _read_links(state)
    content = _read_products(content_dir)
    snapshot = _snapshot(cache.path_for(state), (state, content_dir))
    try:
        now = links.suggest(snapshot, content, saved)[0]
    except (AssertionError, AttributeError, KeyError, TypeError, RecursionError):
        # A JSON container can be readable yet unusable by the matcher. Do not
        # let a matcher traceback print its private labels or values.
        raise Finding("unreadable products") from None
    findings = []
    if draft["asOf"] != snapshot.fetched_at.isoformat():
        findings.append("draft-stale asof")
    changed = sum(now.get(pid) != value for pid, value in draft["pairs"].items())
    if changed:
        findings.append(f"draft-stale pairs {changed}")
    if not findings:
        print("draft current")
    return findings


def main(argv=None):
    parser = PrivateParser(prog="clover_link_draft_check.py", description=__doc__)
    parser.add_argument("--state", required=True, type=Path, help="copied state directory")
    parser.add_argument("--content", required=True, type=Path, help="directory with copied products.json")
    args = parser.parse_args(argv)
    try:
        findings = _check(args.state, args.content)
    except Finding as error:
        findings = [str(error)]
    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} clover_link_draft_check")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
