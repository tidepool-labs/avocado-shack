"""AV1104-09 (H18): count the owner trial per Pacific day without exposing its contents.

`python3 -B hass/trial_summary.py --state DIR --from YYYY-MM-DD [--days N] [--json]` reads `<DIR>/conversation.sqlite3`
read-only (one read transaction, query_only) and prints only counts: owner messages by disposition, drafts created
that day by their CURRENT state, approvals and interpreter calls. It selects only disposition/received_at,
state/created_at, approved_at and day/calls: never text, summaries, codes, ids, sender or chat.
Exit 0 ok, 1 store missing/unreadable/unsafe, 2 invalid arguments.
"""
import argparse, contextlib, json, os, re, sqlite3, stat, sys  # noqa: E401
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PACIFIC = "America/Los_Angeles"
NOT_OWNER = ("ignored", "echo", "edited-ignored")  # stored with a NULL time; never an owner message
MESSAGE_KEYS = ("approved", "rejected", "near-approval", "no-target", "needs-details", "not-drafted", "daily-limit",
                "too-long", "proposed", "question", "unsupported", "claim-question", "paused", "not-read", "approval-held",
                "commands", "attachment-unsupported", "attachment-many", "attachment-failed", "photo-duplicate",
                "photo-on-product", "photo-draft", "photo-refused", "npp-working", "npp-expired", "npp-unavailable",
                "other")
COMMANDS = frozenset({"status", "pause", "resume", "help", "history", "find", "show", "report", "post", "margin", "hidden",
                      "listing", "undo", "memory-list", "memory-none", "memory-forgot", "memory-saved", "memory-updated",
                      "memory-unchanged", "memory-invalid", "memory-ambiguous", "backlog-forgot", "backlog-none"})
# `backlog` itself stays other: it also records declined/unknown skill requests, so it cannot be told from a command
# keys of media.REPLIES (a test keeps this equal); only these suffixes of `photo-refused:` count as photo-refused
PHOTO_REFUSED = frozenset({"empty", "too-large", "unsupported-type", "truncated", "corrupt-store", "not-found", "unreadable",
                           "needs-rotation", "many", "audio"})
DRAFT_KEYS = ("applied", "checked", "failed", "undone", "expired", "cancelled", "waiting", "other")
DRAFT_STATES = {"applied": "applied", "verified": "checked", "failed": "failed", "reverted": "undone", "expired": "expired",
                "rejected": "cancelled", "proposed": "waiting", "needs-details": "waiting", "approved": "waiting"}
UNREADABLE_TEXT = "Trial summary unavailable."


class Unreadable(Exception): """The store cannot be counted; carries no value."""


def _bucket(disposition):
    if not isinstance(disposition, str): return "other"
    if disposition in MESSAGE_KEYS and disposition != "commands": return disposition
    if disposition in COMMANDS: return "commands"
    if disposition.startswith("photo-refused:") and disposition[14:] in PHOTO_REFUSED: return "photo-refused"
    return "other"


def _pacific_day(value):
    """The Pacific date (ISO string) of a timezone-aware ISO-8601 string; None for anything else."""
    if not isinstance(value, str) or not value: return None
    try: dt = datetime.fromisoformat(value)
    except ValueError: return None
    if dt.tzinfo is None or dt.utcoffset() is None: return None
    try: return dt.astimezone(ZoneInfo(PACIFIC)).date().isoformat()
    except (OverflowError, ValueError): return None


def _iso_day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value): return None
    try: return date.fromisoformat(value).isoformat()
    except ValueError: return None


def _blank():
    return {"messages": dict.fromkeys(MESSAGE_KEYS, 0), "drafts": dict.fromkeys(DRAFT_KEYS, 0), "approvals": 0,
            "interpreterCalls": 0}


def _add(into, other):
    for part in ("messages", "drafts"):
        for k, v in other[part].items(): into[part][k] += v
    into["approvals"] += other["approvals"]
    into["interpreterCalls"] += other["interpreterCalls"]


def _check_links(state_dir):
    """Static admission: lstat each component from the anchor; a symlink at any depth (even dangling) is refused. `..` only
    follows an already-checked real directory, so `link/../x` is refused at `link`. Not race-free."""
    cur = os.sep
    for part in os.path.join(os.getcwd(), os.fspath(state_dir)).split(os.sep):
        if part in ("", "."): continue
        cur = os.path.dirname(cur) if part == ".." else os.path.join(cur, part)
        if part != ".." and not stat.S_ISDIR(os.lstat(cur).st_mode): raise Unreadable  # S_ISDIR is false for a link


def _check_store(state_dir):
    """The store file path; the state directory must be real, with no symlink anywhere in its traversal."""
    sdir = Path(state_dir)
    try:
        _check_links(state_dir)
        if sdir.is_symlink() or not sdir.is_dir(): raise Unreadable
        st = os.lstat(path := sdir / "conversation.sqlite3")  # lstat: a dangling link is seen
    except OSError: raise Unreadable from None
    if not stat.S_ISREG(st.st_mode): raise Unreadable
    return path, (st.st_dev, st.st_ino)


def _same_leaf(path, ident):
    """Detection only, not confinement: refuse if the admitted leaf is no longer the same regular file (lstat, never
    following a link; no size/mtime test, so committed WAL growth is fine). A swap between checks is not prevented."""
    try: st = os.lstat(path)
    except OSError: raise Unreadable from None
    if not stat.S_ISREG(st.st_mode) or (st.st_dev, st.st_ino) != ident: raise Unreadable


def _fold(name):
    """ASCII-only fold (SQLite identifier equivalence); never Unicode casefold."""
    return name.translate(_ASCII_FOLD) if isinstance(name, str) else name


_ASCII_FOLD = {c: c + 32 for c in range(65, 91)}


def _rows(db, tables, table, wanted, optional):
    """Rows of `wanted` columns (required) plus `optional` ones (NULL when the old table lacks them); [] without the table; a lazy cursor, consumed before the connection closes."""
    if table not in tables: return []
    have = {_fold(r[1]) for r in db.execute(f"PRAGMA table_info({table})")}
    if not set(wanted) <= have: raise Unreadable
    cols = [*wanted, *(c if c in have else "NULL" for c in optional)]
    return db.execute(f"SELECT {', '.join(cols)} FROM {table}")


def summarize(state_dir, start, days):
    """The report dict for `days` Pacific days from date `start`; raises Unreadable."""
    path, ident = _check_store(state_dir)
    window = [(start + timedelta(n)).isoformat() for n in range(days)]
    buckets = {d: _blank() for d in window}
    unknown = _blank()

    def where(day):
        return unknown if day is None else buckets.get(day)  # None: dated, but outside the window

    try:
        _same_leaf(path, ident)
        with contextlib.closing(sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True)) as db:
            _same_leaf(path, ident)
            db.isolation_level = None
            db.execute("PRAGMA query_only = 1")
            db.execute("BEGIN")
            tables = {_fold(r[0]) for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            for disposition, at in _rows(db, tables, "messages", ["disposition"], ["received_at"]):
                if disposition in NOT_OWNER: continue
                if (b := where(_pacific_day(at))) is not None: b["messages"][_bucket(disposition)] += 1
            for state, at in _rows(db, tables, "drafts", ["state"], ["created_at"]):
                key = DRAFT_STATES.get(state, "other") if isinstance(state, str) else "other"
                if (b := where(_pacific_day(at))) is not None: b["drafts"][key] += 1
            for (at,) in _rows(db, tables, "approvals", [], ["approved_at"]):
                if (b := where(_pacific_day(at))) is not None: b["approvals"] += 1
            for day, calls in _rows(db, tables, "usage", ["day", "calls"], []):
                if type(calls) is not int or calls < 0: raise Unreadable
                if (b := where(_iso_day(day))) is not None: b["interpreterCalls"] += calls
            db.execute("COMMIT")
        _same_leaf(path, ident)
    except (sqlite3.Error, OSError, ZoneInfoNotFoundError): raise Unreadable from None  # missing tzdata: refuse whole
    totals = _blank()
    for d in window: _add(totals, buckets[d])
    _add(totals, unknown)
    return {"result": "ok", "from": window[0], "days": days, "timezone": PACIFIC,
            "daysSummary": [{"day": d, **buckets[d]} for d in window], "unknown": unknown, "totals": totals}


def _line(label, b):
    msgs = " ".join(f"{k}={v}" for k, v in b["messages"].items())
    drafts = " ".join(f"{k}={v}" for k, v in b["drafts"].items())
    return f"{label}: messages[{msgs}] drafts[{drafts}] approvals={b['approvals']} interpreterCalls={b['interpreterCalls']}"


def render(report):
    return "\n".join([*(_line(d["day"], d) for d in report["daysSummary"]), _line("day unknown", report["unknown"]),
                      _line("totals", report["totals"])])


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # never echo what was given
        self.exit(2, "usage: trial_summary.py --state DIR --from YYYY-MM-DD [--days 1-31] [--json]\n")


def main(argv=None):
    p = _Parser(prog="trial_summary.py", description="Count the owner trial per Pacific day; prints counts only.")
    p.add_argument("--state", required=True, help="state directory holding conversation.sqlite3")
    p.add_argument("--from", dest="start", required=True, help="first Pacific day, YYYY-MM-DD")
    p.add_argument("--days", default="7", help="1-31 days (default 7)")
    p.add_argument("--json", action="store_true", help="one JSON line")
    args = p.parse_args(argv)
    if _iso_day(args.start) is None or not re.fullmatch(r"[0-9]{1,2}", args.days) or not 1 <= int(args.days) <= 31:
        p.error("invalid")
    start, days = date.fromisoformat(args.start), int(args.days)
    try:
        (start + timedelta(days - 1)).isoformat()
        report = summarize(args.state, start, days)
    except OverflowError: p.error("invalid")
    except Unreadable:
        print(json.dumps({"result": "unreadable"}) if args.json else UNREADABLE_TEXT)
        return 1
    print(json.dumps(report, separators=(",", ":")) if args.json else render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
