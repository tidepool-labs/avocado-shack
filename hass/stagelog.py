"""HASS-FAST-1: a read-only stage-time log. One JSON line per stage: {"t": epoch seconds, "stage": name, "id": 12 hex}.
The id is the first 12 hex characters of SHA-256 of a message id (or a reply id), so a line never carries message
text, a sender, a chat, an address, a path or a secret. Writing is best effort and can never raise: a full disk, a
missing directory or a bad path just means no line. The file stops growing at MAX_BYTES (one rollover to `.1`).
`table()` joins the Mac log and the host log into the stage table (offsets from the first stage of each message).
Nothing here reads a clock the callers do not pass in, opens a socket or changes any state.
"""
import hashlib, json, math, os, stat, time  # noqa: E401
from pathlib import Path

MAX_BYTES = 512 * 1024
ORDER = ("sent", "webhook-in", "accepted", "ack-start", "ack-end", "post-start", "receiver-accepted", "post-end", "worker-pickup",
         "finance-start", "finance-end", "interp-start", "interp-end", "style-start", "label-start", "label-end", "style-ready",
         "card-start", "card-end", "handled", "reply-queued", "reply-pulled", "bb-send-start", "bb-send-end")


def short(value) -> str:
    """The log id of a message or reply id (12 hex characters, one way)."""
    return hashlib.sha256(str(value).encode("utf-8", "surrogatepass")).hexdigest()[:12]


class StageLog:
    """Append-only, size-capped, never raises. `path` None means off. `clock` is a callable returning epoch seconds."""

    def __init__(self, path=None, clock=time.time):
        self.path, self.clock = (os.fspath(path) if path else None), clock

    def __call__(self, stage, ident, **extra):
        if not self.path: return
        try:
            line = json.dumps({"t": round(self.clock(), 3), "stage": stage, "id": short(ident), **extra}, sort_keys=True) + "\n"
            try:
                if os.stat(self.path).st_size > MAX_BYTES: os.replace(self.path, self.path + ".1")
            except FileNotFoundError: pass
            # O_NONBLOCK: a FIFO with no reader fails the open instead of waiting; only a regular file is ever written.
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            try:
                if stat.S_ISREG(os.fstat(fd).st_mode): os.write(fd, line.encode("utf-8"))
            finally: os.close(fd)
        except Exception:  # noqa: BLE001 - a log line is never worth a crash; nothing is kept about the error
            pass


def off(stage, ident, **extra): return None  # noqa: E704 - the no-op stand-in


def _usable(t) -> bool:
    """True for a finite int/float timestamp (not bool; huge ints that cannot become a float are unusable)."""
    if type(t) not in (int, float): return False
    try: return math.isfinite(t)
    except OverflowError: return False


def read(path) -> list:
    """The valid lines of one stage log, in file order; unreadable or malformed lines are skipped."""
    out = []
    # Non-blocking open so a FIFO without a writer cannot hang; the open descriptor (not the path) decides regularness.
    try: fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except (OSError, ValueError): return out
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode): return out
        with open(fd, "r", encoding="utf-8", errors="replace", closefd=False) as fh: text = fh.read()
    except OSError: return out
    finally: os.close(fd)
    # Records end at LF only (read_text already folded CRLF/CR to LF). str.splitlines would also cut at U+0085/U+2028/U+2029,
    # which are legal literal characters inside a JSON string, and the two fragments would both be dropped as malformed.
    for raw in text.split("\n"):
        try: row = json.loads(raw)
        # Excessive nesting is malformed diagnostic input too; skip only this line.
        except (ValueError, RecursionError): continue
        if type(row) is dict and _usable(row.get("t")) and type(row.get("stage")) is str and type(row.get("id")) is str:
            out.append(row)
    return out


def _offset(t, origin):
    """round(t - origin, 3), or None when the difference is not a usable finite number."""
    try: delta = t - origin
    except OverflowError: return None
    return round(delta, 3) if _usable(delta) else None


def table(rows) -> list:
    """[(message id, {stage: seconds after that message's first stage})] from the merged rows of both logs. Reply stages
    (keyed by reply id) join their message through the `reply-queued` line, which carries both `id` and `rid`.
    Reply-only stages with conflicting bindings are omitted. A stage whose offset cannot be represented
    (two finite extremes whose difference overflows) is omitted; origins are unchanged."""
    by_reply = {}
    for r in rows:
        rid = r.get("rid")
        if r["stage"] == "reply-queued" and type(rid) is str:
            if by_reply.setdefault(rid, r["id"]) != r["id"]:
                by_reply[rid] = None  # Ambiguous for the rest of this table, even if a binding repeats.
    first, seen = {}, {}
    for r in sorted(rows, key=lambda r: r["t"]):
        ident = r["id"]
        if r["stage"] in ("reply-pulled", "bb-send-start", "bb-send-end"):
            ident = by_reply.get(ident, ident)
            if ident is None:
                continue
        seen.setdefault(ident, {}).setdefault(r["stage"], r["t"])
        first[ident] = min(first.get(ident, r["t"]), r["t"])
    return [(i, {s: d for s, t in sorted(st.items(), key=lambda kv: ORDER.index(kv[0]) if kv[0] in ORDER else 99)
                 if (d := _offset(t, first[i])) is not None})
            for i, st in seen.items() if "accepted" in st or "webhook-in" in st]


def _display(token: str) -> str:
    """CLI-only form of an id or stage name: a token with whitespace or a non-printable character (controls, ESC, line
    separators, lone surrogates) is shown as a quoted ASCII JSON string; everything else is unchanged. Keys are never altered."""
    if any(c.isspace() or not c.isprintable() for c in token): return json.dumps(token, ensure_ascii=True)
    return token


def main(argv=None) -> int:
    """`python3 hass/stagelog.py LOG [LOG ...]`: read-only; prints one line per message, seconds after its first stage, for the
    Mac log (spool dir `stages.jsonl`) and the host log (host dir `stages.jsonl`) together. Both machines' clocks should be in step.
    Unsafe ids/stage names (control characters, surrogates) are printed as quoted JSON escapes, never raw."""
    import sys
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(main.__doc__)
        return 2
    for ident, stages in table([r for path in args for r in read(path)]):
        print(_display(ident), " ".join(f"{_display(s)}={t}" for s, t in stages.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
