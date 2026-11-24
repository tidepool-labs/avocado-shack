"""HASS-VOICE-1: the correspondence log. One row for every moment where talking with Mike went wrong, so wording
improves over time.

Where: `<state>/correspondence/<UTC day>.jsonl` (state folder only; never copied off the box: the state backup lists
the files it takes and this folder is not one of them). Append-only: a row is added with O_APPEND and never edited.
Retention is 90 days: whole day files older than that are deleted (`prune`), never rewritten.

A row: {"at", "kind", "reason", "msg", "reply", "excerpt", "seconds"}.
  kind    one of KINDS
  reason  a short neutral code (letters, digits, dashes), never a sentence
  msg     12 hex characters, one way: the message it was about (stagelog.short); reply: the same for our reply
  excerpt at most 80 characters of what Mike wrote, with numbers, addresses and links blanked; "" when none is needed
  seconds optional finite elapsed time, rounded to one decimal place
Writing never raises: a full disk or a bad folder means no row, never a lost reply.

Command line (for G, on the box):  python3 hass/corrlog.py problems --state DIR   |   weekly --state DIR
"""
import argparse, json, math, os, re, stat, sys  # noqa: E401
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import voice  # noqa: E402
from hass.stagelog import short  # noqa: E402

FOLDER = "correspondence"
RETENTION_DAYS = 90
EXCERPT_MAX = 80
SLOW_SECONDS = 20
KINDS = {
    "did-not-understand": "I did not understand",
    "could-not-do": "I could not do it",
    "asked-again": "I asked something he had already answered",
    "error": "something went wrong",
    "slow": "a reply took more than 20 seconds",
    "voice-fallback": "my wording was not fit to send",
    "corrected": "he corrected me or said no",
}
SUGGESTIONS = {  # kind -> the one fix to suggest in the weekly line (plain words, for G)
    "did-not-understand": "collect the phrases that were unclear and teach Hass to understand them",
    "could-not-do": "decide whether to build the thing he keeps asking for",
    "asked-again": "make the question list what is already known before asking",
    "error": "look at the most common cause and fix it at the source",
    "slow": "look for what makes replies slow and fix that first",
    "voice-fallback": "rewrite the wording that was held back",
    "corrected": "read the corrected messages and improve the draft wording",
}
_REASON_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
_SECRETS = (  # blanked before an excerpt is kept
    (re.compile(r"https?://\S+|www\.\S+", re.I), "[link]"),
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[address]"),
    (re.compile(r"\+?\d[\d ().-]{5,}\d"), "[number]"),
    (re.compile(r"\b[A-Za-z0-9_-]{24,}\b"), "[long code]"),
)


def _clean(text) -> str:
    """At most EXCERPT_MAX characters of what Mike wrote, on one line, with numbers, addresses and links blanked."""
    text = " ".join(str(text or "").split())
    for rx, repl in _SECRETS: text = rx.sub(repl, text)
    return text[:EXCERPT_MAX]


class CorrLog:
    """state: the Hass state folder (a Path or str). clock: callable returning an aware datetime."""

    def __init__(self, state, clock):
        self.dir, self.clock = Path(state) / FOLDER, clock
        self._pruned_on = None  # the day this instance last pruned: old files go without anyone running prune

    def _real_directory(self) -> bool:
        try: return stat.S_ISDIR(self.dir.lstat().st_mode)
        except OSError: return False

    def record(self, kind, reason, *, msg=None, reply=None, excerpt=None, seconds=None) -> bool:
        """Add one row. True when it was written. Never raises."""
        try:
            if kind not in KINDS: return False
            reason = str(reason).lower()
            if not _REASON_RE.fullmatch(reason): reason = "other"
            now = self.clock().astimezone(timezone.utc)
            row = {"at": now.isoformat(timespec="seconds"), "kind": kind, "reason": reason,
                   "msg": short(msg) if msg is not None else "", "reply": short(reply) if reply is not None else "",
                   "excerpt": _clean(excerpt)}
            if isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
                try:
                    elapsed = round(float(seconds), 1)
                except OverflowError:
                    pass  # The timing is unavailable, not the event.
                else:
                    if math.isfinite(elapsed): row["seconds"] = elapsed
            self.dir.mkdir(mode=0o700, exist_ok=True)
            if not self._real_directory(): return False
            if self._pruned_on != now.date():  # at most one directory scan a day; prune never raises
                self._pruned_on = now.date()
                self.prune()
            path = self.dir / f"{now:%Y-%m-%d}.jsonl"
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode): return False
                pending = memoryview((json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
                while pending:
                    written = os.write(fd, pending)
                    if written == 0: return False
                    pending = pending[written:]
            finally: os.close(fd)
            return True
        except Exception:  # noqa: BLE001 - a log row is never worth a lost reply
            return False

    def rows(self, days=RETENTION_DAYS) -> list:
        """Valid rows from the last `days` days, oldest first. Unreadable lines and files are skipped."""
        out, cutoff = [], self.clock().astimezone(timezone.utc) - timedelta(days=days)
        if not self._real_directory(): return []
        try: files = sorted(p for p in self.dir.iterdir() if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.jsonl", p.name))
        except OSError: return []
        for path in files:
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                try:
                    if not stat.S_ISREG(os.fstat(fd).st_mode): continue
                    with os.fdopen(fd, "r", encoding="utf-8", errors="replace", closefd=False) as stream:
                        text = stream.read()
                finally: os.close(fd)
            except OSError: continue
            for raw in text.splitlines():
                try: row = json.loads(raw)
                except (ValueError, RecursionError): continue  # RecursionError: nesting beyond the decoder's depth
                if isinstance(row, dict) and isinstance(row.get("kind"), str) and row["kind"] in KINDS and isinstance(row.get("at"), str):
                    if "excerpt" in row and not isinstance(row["excerpt"], str): continue  # damaged row: skip only it
                    try: at = datetime.fromisoformat(row["at"])
                    except ValueError: continue
                    if at.tzinfo is not None and at >= cutoff: out.append((at, row))
        out.sort(key=lambda pair: pair[0])  # stable: by real instant, equal instants keep scan order
        return [row for _, row in out]

    def prune(self) -> int:
        """Delete whole day files older than RETENTION_DAYS. Returns how many were deleted. Never raises."""
        removed, cutoff = 0, (self.clock().astimezone(timezone.utc) - timedelta(days=RETENTION_DAYS)).date()
        if not self._real_directory(): return removed
        try:
            for path in self.dir.iterdir():
                m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.jsonl", path.name)
                if not (m and path.is_file() and not path.is_symlink()): continue
                try: day = datetime.strptime(m[1], "%Y-%m-%d").date()
                except ValueError: continue  # named like a day but not a real date (2026-02-30): not ours, left untouched
                if day < cutoff:
                    path.unlink()
                    removed += 1
        except OSError:
            pass
        return removed

    def last(self, n=10) -> list:
        return self.rows()[-n:][::-1]  # newest first

    def top(self, days=7, n=3) -> list:
        """[(kind, count)] for the most common problems of the last `days` days."""
        counts = Counter(r["kind"] for r in self.rows(days))
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


def _local(iso, clock) -> str:
    from zoneinfo import ZoneInfo
    try: at = datetime.fromisoformat(iso).astimezone(ZoneInfo("America/Los_Angeles"))
    except (TypeError, ValueError, OverflowError): return "an unknown time"  # OverflowError: conversion leaves the calendar
    return f"{at:%a %b} {at.day}, {at.hour % 12 or 12}:{at:%M} {'am' if at.hour < 12 else 'pm'}"


def problems_text(log, n=10) -> str:
    """For G only: the last n problem moments in plain words, newest first."""
    rows = log.last(n)
    if not rows: return "No problems have been logged lately."
    lines = [f"The last {len(rows)} problem{'s' if len(rows) != 1 else ''}, newest first:"]
    for r in rows:
        extra = f' He wrote: {voice.quote(chr(34) + r["excerpt"] + chr(34))}.' if r.get("excerpt") else ""
        lines.append(f"- {_local(r['at'], log.clock)}: {KINDS[r['kind']]} ({r.get('reason', 'other')}).{extra}")
    return "\n".join(lines)


def weekly_line(log) -> str:
    """For G only (never Mike): the three most common problems this week, and one suggested fix each."""
    top = log.top(7, 3)
    if not top: return "Talking with Mike this week: no problems logged."
    parts = [f"{KINDS[k]} ({n} time{'s' if n != 1 else ''}; try: {SUGGESTIONS[k]})" for k, n in top]
    return "Talking with Mike this week, the most common problems were: " + "; ".join(parts) + "."


def main(argv=None, out=None) -> int:
    parser = argparse.ArgumentParser(prog="hass/corrlog.py", description="Read the correspondence log (G only).")
    parser.add_argument("what", choices=("problems", "weekly", "prune"))
    parser.add_argument("--state", required=True)
    args = parser.parse_args(argv)
    log = CorrLog(args.state, lambda: datetime.now(timezone.utc))
    print({"problems": problems_text, "weekly": weekly_line}.get(args.what, lambda lg: f"Deleted {lg.prune()} old day files.")(log),
          file=out or sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
