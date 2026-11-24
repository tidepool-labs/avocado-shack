"""Check Clover write readiness from private, quiescent local state files only."""
import argparse
import json
import os
import sqlite3
import stat
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Support direct invocation from a checkout, without installing Hass.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.clover import cache, credential  # noqa: E402
from hass.clover.config import ConfigProblem, from_settings  # noqa: E402
from hass.clover.journal import Journal  # noqa: E402
from hass.host import HostConfigError, _private_json  # noqa: E402


CHECKS = ("read_only_day", "write_token_file", "settings", "daily_cap", "testitem")
INVENTORY = "testitem_inventory"
INPUT_ERRORS = (cache.CacheUnsafe, OSError, sqlite3.Error, ValueError, TypeError, KeyError, RecursionError)
GAP = timedelta(minutes=30)


def _database(path):
    """Open a private offline snapshot without SQLite creating sidecars.

    Refuse snapshots with pending journal files rather than silently ignoring
    them in immutable mode. Run with the state quiescent (or on an offline copy).
    """
    if not cache._private_dir(path.parent, create=False):
        raise FileNotFoundError
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise PermissionError
    if any(os.path.lexists(str(path) + suffix) for suffix in ("-wal", "-journal", "-shm")):
        raise sqlite3.OperationalError
    return closing(sqlite3.connect(path.absolute().as_uri() + "?mode=ro&immutable=1", uri=True))


def _read_only_day(state, config, now):
    # Read the same metadata and successful-pull markers as cache.facts/history,
    # without loading inventory values or opening two different snapshots.
    with _database(cache.path_for(state)) as db:
        meta = dict(db.execute("SELECT key, value FROM meta"))
        if cache._refusal(meta, cache.identity_of(config)):
            return "identity"
        if meta.get("lastResult") != "ok" or meta.get("failures") != "0":
            return "last_attempt"
        times = [datetime.fromisoformat(t) for (t,) in db.execute(
            "SELECT taken FROM snapshots WHERE id = ?", (cache.READ_MARK,))]
    if any(t.tzinfo is None for t in times):
        raise ValueError
    times.sort()
    if not times or not timedelta(0) <= now - times[-1] <= GAP:
        return "stale"
    # Only the recent uninterrupted run matters, not gaps before it started.
    end = times[-1]
    for earlier, later in zip(reversed(times[:-1]), reversed(times[1:])):
        if later - earlier > GAP:
            break
        if end - earlier >= timedelta(days=1):
            return "ok"
    return "coverage"


def _write_token(config, path):
    if not path:
        return "missing"
    if os.path.realpath(path) == os.path.realpath(config.token_file):
        return "same_file"
    reason = credential.inspect(path)
    if reason:
        return reason
    # This metadata comparison is solely for distinctness (hard-link aliases).
    try:
        if os.path.samefile(path, config.token_file):
            return "same_file"
    except FileNotFoundError:
        pass
    except OSError:
        return "unreadable"
    return "ok"


def _testitem(state, config):
    journal = Journal(state, config)  # locating it does not open or lock it
    hidden, stocked = set(), set()
    changes = {}
    with _database(journal.path) as db:
        row = db.execute("SELECT v FROM meta WHERE k = 'identity'").fetchone()
        if row != (journal.identity,):
            return "identity", "identity"
        for draft, result in db.execute("SELECT draft, result FROM changes WHERE status = 'applied' ORDER BY rowid"):
            entry = json.loads(draft)
            kind = entry["kind"]
            if kind == "create_item":
                new_id = json.loads(result)["result_item_id"]
                if isinstance(new_id, str) and new_id:
                    changes[new_id] = [entry]
            elif kind in ("set_hidden", "set_stock") and entry["item_id"] in changes:
                if kind == "set_stock":
                    stocked.add(entry["item_id"])
                elif entry["after"]["hidden"] is True:
                    hidden.add(entry["item_id"])
            if kind != "create_item" and isinstance(entry.get("item_id"), str) and entry["item_id"] in changes:
                changes[entry["item_id"]].append(entry)
    legacy = ("ok" if hidden & stocked else "warn_missing_stock") if hidden else "missing_proof"
    try:
        return legacy, _testitem_inventory(changes)
    except INPUT_ERRORS:
        return legacy, "unreadable"


def _testitem_inventory(changes):
    if not changes:
        return "no-create"
    filed = [entries for entries in changes.values() if any(
        req["method"] == "POST" and req["path"] == "/category_items"
        for req in entries[0].get("requests", ())
    )]
    if not filed:
        return "no-category"
    counted = [entries for entries in filed if any(e["kind"] == "set_stock" for e in entries)]
    if not counted:
        return "no-count"
    for entries in counted:
        last = entries[-1]
        if last["kind"] == "set_hidden" and last["after"]["hidden"] is True:
            return "ok"
    return "not-hidden"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, type=Path)
    parser.add_argument("--now", metavar="ISO")
    parser.add_argument("--for", dest="purpose", choices=("inventory",))
    args = parser.parse_args(argv)
    checks: dict[str, str] = dict.fromkeys((*CHECKS, INVENTORY), "unreadable")
    unreadable = False
    try:
        now = datetime.fromisoformat(args.now) if args.now is not None else datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        # Only validate settings consumed here, not the service's live-site settings.
        host = _private_json(args.host)
        state = host["state"]
        if not isinstance(state, str) or not state:
            raise ValueError
        raw = host.get("clover", {})
        if raw == {}:
            checks = dict.fromkeys(checks, "not_configured")
        else:
            if not isinstance(raw, dict):
                raise ValueError
            # Isolate the distinct-file check so an exact alias yields a check
            # failure, rather than making the whole host input unreadable.
            settings = dict(raw)
            path = settings.get("writeTokenFile", "")
            if "tokenFile" in settings and path == settings["tokenFile"]:
                settings.pop("writeTokenFile", None)
            config = from_settings(settings)
            checks["settings"] = "ok" if {"writes", "liveApproved", "writeTokenFile"} <= raw.keys() else "missing"
            checks["daily_cap"] = "ok" if config.daily_write_cap <= 5 else "over_cap"
            checks["write_token_file"] = _write_token(config, path)
            try:
                checks["read_only_day"] = _read_only_day(state, config, now)
            except FileNotFoundError:
                checks["read_only_day"] = "missing"
            except INPUT_ERRORS:
                unreadable = True
            try:
                checks["testitem"], checks[INVENTORY] = _testitem(state, config)
            except FileNotFoundError:
                checks["testitem"], checks[INVENTORY] = "missing", "no-create"
            except INPUT_ERRORS:
                unreadable = True
    except (HostConfigError, ConfigProblem, OSError, ValueError, KeyError):
        unreadable = True
    passed = all(word == "ok" or name == "testitem" and word == "warn_missing_stock"
                 for name, word in checks.items() if name != INVENTORY or args.purpose == "inventory")
    if args.purpose == "inventory" and checks[INVENTORY] == "unreadable":
        unreadable = True
    print(json.dumps({"result": "pass" if passed else "fail", "checks": checks}))
    return 2 if unreadable else 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
