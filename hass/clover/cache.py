"""HASS-CLOVER-2: the PRIVATE till cache: `<state>/clover/cache.sqlite3` (folder 0700, file 0600, owned by the service user).

`hass/clover/cli.py sync` is the only writer; the conversation and `hass/health.py` only read (sqlite mode=ro). The cache holds the
inventory fields Hass answers from (name, SKU or code, price in cents, category ids, hidden, stock count) and when they were read. It never
holds a token, a header, a response body, or any sales, order, customer, payment or employee data, and it is never in git or on the site
(the state folder is neither). One sync replaces every row in ONE transaction, so a reader sees the old pull or the new one, never half.

Meta rows: `asOf` (UTC ISO of the last good pull), `lastAttempt`, `lastResult` ("ok" or one fixed word), `failures` (in a row) and
`nextAttempt` (the backoff: a failing till is asked less often, up to every BACKOFF_MAX_MINUTES).

HASS-CLOVER-1-FIX-2 (RETURN t_54d7c993): the cache knows which till it holds. Meta rows `environment`, `merchantId` and `schema`
(SCHEMA_VERSION) are written in the SAME transaction as the items and the backoff rows. `read` and `facts` take the configured
Identity and refuse (reason word `identity`) a cache written for another environment or merchant, or one with no identity (an older
cache): no item is quoted and no backoff is obeyed. The first good pull of the configured till replaces it; a failed pull of the
configured till starts that till's own record (the other till's rows are dropped: they can never be shown under this configuration).
"""
import json
import os
import sqlite3
import stat
from collections import namedtuple
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from hass.clover.mapper import CloverItem
from hass.clover.reads import Snapshot

DIRNAME, FILENAME = "clover", "cache.sqlite3"
SCHEMA_VERSION = "clover-cache-1"
REFUSED = "identity"
BACKOFF_MINUTES, BACKOFF_MAX_MINUTES = 15, 240
RESULTS = ("ok", "token", "refused-key", "unreachable", "rate-limited", "clover-error", "bad-data")
SCHEMA = """
CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY, name TEXT NOT NULL, sku TEXT NOT NULL, code TEXT NOT NULL, price_cents INTEGER,
  price_type TEXT NOT NULL, unit_name TEXT NOT NULL, category_ids TEXT NOT NULL, categories TEXT NOT NULL, hidden INTEGER NOT NULL,
  available INTEGER NOT NULL, stock TEXT, stock_modified INTEGER, modified_time INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots(taken TEXT NOT NULL, id TEXT NOT NULL, stock TEXT NOT NULL, PRIMARY KEY(taken, id));
"""
READ_MARK = ""   # one row per read with this id keeps the time of a read in which no item had a count (never an item id)
SNAPSHOT_DAYS = 14   # HASS-POS-1: counts per read, kept this long (count drops for "what sold"); written and pruned with the sync
COLUMNS = ("id", "name", "sku", "code", "price_cents", "price_type", "unit_name", "category_ids", "categories", "hidden", "available", "stock",
           "stock_modified", "modified_time")


class CacheUnsafe(Exception):
    """The cache folder or file is not private to the service user (a link, another owner, a wider mode). Nothing was read or written."""


Identity = namedtuple("Identity", "environment merchant_id")   # the till a cache belongs to: host.json clover.environment + merchantId
IDENTITY_KEYS = ("environment", "merchantId", "schema")


def identity_of(config):
    """The Identity of a hass.clover.config.CloverConfig."""
    return Identity(config.environment, config.merchant_id)


def _complete(identity):
    return (isinstance(identity, tuple) and len(identity) == 2 and all(isinstance(v, str) and v for v in identity))


def _identity_meta(identity):
    return {"environment": identity[0], "merchantId": identity[1], "schema": SCHEMA_VERSION}


def _refusal(meta, identity):
    """None when the cache's meta names exactly the configured (complete) till and this schema, else REFUSED."""
    if _complete(identity) and {k: meta.get(k) for k in IDENTITY_KEYS} == _identity_meta(identity):
        return None
    return REFUSED


def path_for(state):
    return Path(state) / DIRNAME / FILENAME


def _iso(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(text):
    try:
        moment = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else None


def _private_dir(folder, create):
    try:
        st = os.lstat(folder)
    except FileNotFoundError:
        if not create:
            return False
        os.mkdir(folder, 0o700)
        st = os.lstat(folder)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise CacheUnsafe("folder")
    return True


def _private_file(path, create):
    """The cache file exists (or is created 0600) as a regular file of this user with no group/other bits."""
    flags = os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0) | (os.O_CREAT if create else 0)
    try:
        fd = os.open(path, flags, 0o600)
    except FileNotFoundError:
        return False
    except OSError:
        raise CacheUnsafe("file") from None
    try:
        st = os.fstat(fd)
    finally:
        os.close(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise CacheUnsafe("file")
    return True


def _open_write(state):
    path = path_for(state)
    _private_dir(path.parent, create=True)
    _private_file(path, create=True)
    db = sqlite3.connect(path, isolation_level=None, timeout=10)
    db.executescript(SCHEMA)
    return db


def _open_read(state):
    """A read-only connection, or None when there is no cache yet. Raises CacheUnsafe for a cache that is not private."""
    path = path_for(state)
    if not _private_dir(path.parent, create=False):
        return None
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise CacheUnsafe("file")
    return sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True, timeout=5, isolation_level=None)


def _meta(db):
    try:
        return dict(db.execute("SELECT key, value FROM meta"))
    except sqlite3.Error:
        return {}


def _count(value):
    """A stored counter as an int; an unreadable one (text, a fraction) is 0 and never echoed."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _set_meta(db, values):
    db.executemany("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                   [(k, str(v)) for k, v in values.items()])


def write_items(state, rows, now, identity):
    """Replace every cached item with `rows` (dicts with COLUMNS), mark the pull good and record the till it came from (`identity`,
    the configured Identity), all in one transaction. Raises ValueError for an incomplete identity (nothing is written)."""
    if not _complete(identity):
        raise ValueError("identity")
    with closing(_open_write(state)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            if _refusal(_meta(db), identity):
                db.execute("DELETE FROM snapshots")   # a switch to another till: its counts never show under this one
            db.execute("DELETE FROM items")
            db.executemany(f"INSERT INTO items({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
                           [tuple(r[c] for c in COLUMNS) for r in rows])
            db.execute("DELETE FROM snapshots WHERE taken < ?", (_iso(now - timedelta(days=SNAPSHOT_DAYS)),))
            db.executemany("INSERT OR REPLACE INTO snapshots(taken, id, stock) VALUES (?, ?, ?)",
                           [(_iso(now), READ_MARK, "0"), *((_iso(now), r["id"], r["stock"]) for r in rows if r["stock"] is not None)])
            _set_meta(db, {"asOf": _iso(now), "lastAttempt": _iso(now), "lastResult": "ok", "failures": 0, "nextAttempt": "",
                           "itemCount": len(rows), **_identity_meta(identity)})
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise


def backoff_minutes(failures, retry_after_seconds=None):
    wait = min(BACKOFF_MAX_MINUTES, BACKOFF_MINUTES * 2 ** max(0, failures - 1))
    if retry_after_seconds:
        wait = max(wait, -(-int(retry_after_seconds) // 60))
    return wait


def record_failure(state, word, now, retry_after_seconds=None, identity=None):
    """Note a failed pull (one fixed word) and when to try next. The items and `asOf` are kept, so answers say how old they are.

    `identity` is the configured till that failed (cli.sync always passes it). When the cache holds another till, or no identity, this
    is that till's FIRST failure: the other rows are dropped and the record restarts under `identity` (failures 1, no good pull yet).
    None keeps the cache's own identity (for a caller that only notes a failure of the till already in the cache)."""
    if word not in RESULTS or word == "ok":
        word = "clover-error"
    with closing(_open_write(state)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            meta = _meta(db)
            if identity is not None and _refusal(meta, identity):
                if not _complete(identity):
                    raise ValueError("identity")
                db.execute("DELETE FROM items")
                db.execute("DELETE FROM snapshots")   # another till's counts are never shown under this one
                _set_meta(db, {"asOf": "", "itemCount": 0, **_identity_meta(identity)})
                failures = 1
            else:
                failures = _count(meta.get("failures")) + 1
            nxt = now + timedelta(minutes=backoff_minutes(failures, retry_after_seconds))
            _set_meta(db, {"lastAttempt": _iso(now), "lastResult": word, "failures": failures, "nextAttempt": _iso(nxt)})
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    return failures


def facts(state, identity):
    """{asOf, lastAttempt, lastResult, failures, nextAttempt, itemCount, environment, merchantId} as plain values, or None when there is
    no cache yet. For `cli status`, health and the backoff; no item data. A cache that is not for `identity` (the configured till) gives
    only {"refused": "identity", environment, merchantId} (what the cache says it holds, None when it says nothing): no freshness and
    no backoff from another till. Raises CacheUnsafe for a cache that is not private."""
    conn = _open_read(state)
    if conn is None:
        return None
    with closing(conn) as db:
        meta = _meta(db)
    if _refusal(meta, identity):
        return {"refused": REFUSED, "environment": meta.get("environment") or None, "merchantId": meta.get("merchantId") or None}
    return {"asOf": meta.get("asOf") or None, "lastAttempt": meta.get("lastAttempt") or None, "lastResult": meta.get("lastResult") or None,
            "failures": _count(meta.get("failures")), "nextAttempt": meta.get("nextAttempt") or None,
            "itemCount": _count(meta.get("itemCount")), "environment": meta["environment"], "merchantId": meta["merchantId"]}


def _item(row):
    r = dict(zip(COLUMNS, row))
    stock = None if r["stock"] is None else Decimal(r["stock"])
    return CloverItem(id=r["id"], name=r["name"], sku=r["sku"], code=r["code"], price_cents=r["price_cents"], price_type=r["price_type"],
                      unit_name=r["unit_name"], categories=tuple(json.loads(r["categories"])), tags=(), stock=stock,
                      stock_modified=r["stock_modified"], hidden=bool(r["hidden"]), available=bool(r["available"]),
                      modified_time=r["modified_time"])


def read(state, identity):
    """(snapshot or None, reachable): the last good pull of the configured till (`identity`) as a reads.Snapshot (None when there never
    was one) and whether the LAST attempt for that till worked (True when nothing was tried yet). A cache of another till or with no
    identity is refused (reason REFUSED): (None, True), "nothing read for this till yet". A cache that is not private or not readable
    reads as (None, False). The meta and the items are read in ONE read transaction, so they come from the same pull."""
    try:
        conn = _open_read(state)
    except CacheUnsafe:
        return None, False
    if conn is None:
        return None, True
    with closing(conn) as db:
        try:
            db.execute("BEGIN")
        except sqlite3.Error:
            return None, False
        meta = _meta(db)
        if _refusal(meta, identity):
            return None, True
        reachable = meta.get("lastResult", "ok") == "ok"
        as_of = _parse_iso(meta.get("asOf"))
        if as_of is None:
            return None, reachable
        try:
            items = tuple(_item(r) for r in db.execute(f"SELECT {', '.join(COLUMNS)} FROM items ORDER BY name, id"))
        except (sqlite3.Error, ValueError, ArithmeticError, TypeError):   # TypeError: valid JSON that is not a list (null, number, bool)
            return None, False
    return Snapshot(items, as_of), reachable


def history(state, identity):
    """HASS-POS-1: [(taken, {item id: count})] oldest first for the configured till; [] when none, refused or unreadable."""
    try:
        conn = _open_read(state)
    except CacheUnsafe:
        return []
    if conn is None:
        return []
    out = {}
    with closing(conn) as db:
        if _refusal(_meta(db), identity):
            return []
        try:
            for taken, iid, stock in db.execute("SELECT taken, id, stock FROM snapshots ORDER BY taken"):
                counts = out.setdefault(taken, {})
                if iid != READ_MARK:
                    counts[iid] = Decimal(stock)
        except (sqlite3.Error, ArithmeticError):
            return []
    return [(_parse_iso(t), out[t]) for t in out if _parse_iso(t)]
