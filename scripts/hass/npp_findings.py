#!/usr/bin/env python3
"""Maintain the private NPP findings ledger in an operator-owned directory outside Git.

Summaries must be redacted before submission; the character check is a backstop,
not a detector for names or other private prose. A repeat stays marked after
closure so the repeat count cannot fall when its card is resolved.

`import` drafts open findings from the redacted weekly review export
(npp_review_export.py job summaries and event rows). It reads only the job id,
the summary's slow/stages/fallbacks/drifted_steps/questions/edits facts, and an
outgoing event's chat pseudonym and redacted text; every summary is a fixed
template. Summaries may not hold digits, so the job id (lowercase hex) and the
chat number are written as a reference with each digit 0-9 spelled g-p
(`c0de` -> `cgde`, `chat-12` -> `hi`). That reference plus the class is the
import key: a job's finding is never imported twice, in any week or state, and
a guard reply (event rows carry no job) is keyed by chat within the week.
"""

import argparse
from collections import Counter
from datetime import date, timedelta
import fcntl
import json
from math import isfinite
import os
from pathlib import Path
import re
import stat
import tempfile
import unicodedata


COLUMNS = "id week stage class summary case_id card state reason".split()
HEADER = "\t".join(COLUMNS)
STAGES = {f"S{n}" for n in range(1, 14)}
WEEK = re.compile(r"([0-9]{4})-W([0-9]{2})")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
CASE = re.compile(r"(?:case-[0-9]+-[a-z0-9]+(?:-[a-z0-9]+)*\.json|npp-[0-9]{8}-[0-9]+)")
CARD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")

JOB = re.compile(r"[0-9a-f]{4,12}")  # hass.npp.receipt.JOB_RE
CHAT = re.compile(r"chat-([1-9][0-9]*)")  # npp_review_export pseudonyms
REFERENCE = str.maketrans("0123456789", "ghijklmnop")
IMPORT_KEY = re.compile(r"(job|chat) ([a-p]+): ")
# A class suffix must be plain words: anything else (the export's [redacted],
# dotted or numbered names) collapses to `redacted` so it cannot carry values.
NAME = re.compile(r"[a-z]+(?:-[a-z]+)*")
NAME_MAX = 40
GUARDS = Path(__file__).resolve().parents[2] / "hass/npp/assets/hass-npp-reply/reply-templates.json"
GUARD_STAGES = {"render_failed": "S8", "live_check_failed": "S13"}  # others are S11 approval guards
STEP_STAGES = {"label": "S2", "identify": "S2", "research": "S4", "maker": "S4", "copy": "S5",
               "wording": "S5", "picture": "S6", "polish": "S6", "judge": "S7", "render": "S8", "edit": "S10"}


class LedgerError(ValueError):
    """An error message safe to print without echoing any source values."""


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's usual errors can echo private input, especially a bad quote.
        self.exit(2, "error: invalid arguments (see --help)\n")


def monday(value):
    match = WEEK.fullmatch(value)
    if not match:
        raise LedgerError("invalid ISO week")
    try:
        return date.fromisocalendar(int(match[1]), int(match[2]), 1)
    except ValueError:
        raise LedgerError("invalid ISO week") from None


def validate_add(week, stage, failure_class, summary):
    monday(week)
    if stage not in STAGES:
        raise LedgerError("invalid stage")
    if not SLUG.fullmatch(failure_class):
        raise LedgerError("invalid failure class")
    if (not summary.strip() or not summary.isprintable()
            or any(char.isdigit() or char in "@$" for char in summary)):
        raise LedgerError("summary must be redacted and on one line")


def validate_close(case, reason, card):
    if (not CARD.fullmatch(card) or bool(case) == bool(reason)
            or (case and not CASE.fullmatch(case))
            or (reason and not SLUG.fullmatch(reason))):
        raise LedgerError("closure requires a card and exactly one case filename, case tag or reason slug")


def _fold(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def guard_lines():
    """Map each guard reply line in the reviewed reply templates to its key."""
    try:
        guards = json.loads(GUARDS.read_text(encoding="utf-8"))["guards"]
        lines = {_fold(text): key for key, text in guards.items() if key != "guard_note"}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise LedgerError("guard templates unavailable") from None
    if not lines or not all(NAME.fullmatch(key.replace("_", "-")) for key in lines.values()):
        raise LedgerError("guard templates unavailable")
    return lines


def _name(value):
    name = value.replace("_", "-")
    return name if NAME.fullmatch(name) and len(name) <= NAME_MAX else "redacted"


def _names(value):
    # A job whose evidence is missing or bad carries None for each evidence fact.
    if value is None:
        return []
    if not isinstance(value, list) or not all(type(item) is str for item in value):
        raise ValueError
    return sorted({_name(item) for item in value})


def _count(value):
    if type(value) is not int or value < 0:
        raise ValueError
    return value


def _slowest_stage(stages):
    # The slowest recorded stage is the place to start; without stages, the reply stage.
    if stages is not None and not isinstance(stages, list):
        raise ValueError
    slowest = None
    for item in stages or []:
        stage, ms = item["stage"], item["ms"]
        if stage not in STAGES or type(ms) not in (int, float) or not isfinite(ms) or ms < 0:
            raise ValueError
        if slowest is None or ms > slowest[0]:
            slowest = (ms, stage)
    return slowest[1] if slowest else "S9"


def _job_findings(row):
    job, facts = row["job"], row["summary"]
    if type(job) is not str or not JOB.fullmatch(job) or not isinstance(facts, dict):
        raise ValueError
    if type(facts["slow"]) is not bool:
        raise ValueError
    ref = job.translate(REFERENCE)
    slow_stage = _slowest_stage(facts["stages"])
    fallbacks, drifted = _names(facts["fallbacks"]), _names(facts["drifted_steps"])
    questions, edits = _count(facts["questions"]), _count(facts["edits"])
    found = []

    def draft(stage, failure_class, text):
        found.append((("job", ref, failure_class), stage, failure_class, f"job {ref}: {text}"))

    if facts["slow"]:
        draft(slow_stage, "slow", "a work segment passed the time-to-card target")
    for code in fallbacks:
        draft(STEP_STAGES.get(code.split("-")[0], "S9"), f"fallback-{code}", f"the card used fallback {code}")
    if questions > 1:
        draft("S3", "question", "asked more than one question")
    for step in drifted:
        draft(STEP_STAGES.get(step.split("-")[0], "S7"), f"drift-{step}",
              f"step {step} returned a model other than its pin")
    if edits:
        draft("S10", "edit", "edited after a card was delivered")
    return found


def _guard_findings(row, guards):
    chat, direction, text = row["chat"], row["dir"], row["text_redacted"]
    match = CHAT.fullmatch(chat) if type(chat) is str else None
    if not match or direction not in ("in", "out") or type(text) is not str:
        raise ValueError
    key = guards.get(_fold(text)) if direction == "out" else None
    if key is None:
        return []
    ref = match[1].translate(REFERENCE)
    failure_class = "guard-" + key.replace("_", "-")
    summary = f"chat {ref}: guard reply {key.replace('_', ' ')} sent"
    return [(("chat", ref, failure_class), GUARD_STAGES.get(key, "S11"), failure_class, summary)]


def draft_findings(path, week):
    """Return {import key: (stage, class, summary)} in export order; refuse the whole file if any row is bad."""
    guards = guard_lines()
    drafts = {}
    try:
        with path.open(encoding="utf-8") as source:
            lines = source.read().splitlines()
        for line in lines:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError
            if "job" in row:
                found = _job_findings(row)
            elif "chat" in row:
                found = _guard_findings(row, guards)
            else:
                raise ValueError
            for key, stage, failure_class, summary in found:
                drafts.setdefault(key, (stage, failure_class, summary))
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError, RecursionError, OverflowError):
        raise LedgerError("bad-export") from None
    for stage, failure_class, summary in drafts.values():
        validate_add(week, stage, failure_class, summary)  # backstop: never store an unsafe draft
    return drafts


def import_key(kind, ref, failure_class, week):
    # Jobs keep their id across weekly exports; chat pseudonyms are numbered per export.
    return (kind, ref, failure_class) + ((week,) if kind == "chat" else ())


def ledger_keys(rows):
    keys = set()
    for row in rows:
        match = IMPORT_KEY.match(row["summary"])
        if match:
            keys.add(import_key(match[1], match[2], row["class"], row["week"]))
    return keys


def ledger_path(path):
    # Check both the supplied ancestry and its physical destination: neither a
    # Git worktree's .git file nor a symlink into a checkout may hide it.
    resolved = path.resolve()
    for parent in (*path.absolute().parents, *resolved.parents):
        if os.path.lexists(parent / ".git"):
            raise LedgerError("ledger must be outside Git worktrees")
    if path.is_symlink() or resolved.name == ".git":
        raise LedgerError("invalid ledger path")
    return resolved


def open_private(path, flags):
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
            raise LedgerError("ledger and lock must be regular private files")
    except BaseException:
        os.close(fd)
        raise
    return fd


def read_ledger(path):
    try:
        fd = open_private(path, os.O_RDONLY)
    except FileNotFoundError:
        return []
    rows = []
    weeks = Counter()
    with os.fdopen(fd, "rb") as source:
        line_no = 1
        try:
            if source.readline().decode("utf-8").removesuffix("\n").removesuffix("\r") != HEADER:
                raise LedgerError("invalid header")
            for line_no, raw in enumerate(source, 2):
                values = raw.decode("utf-8").removesuffix("\n").removesuffix("\r").split("\t")
                finding, week, stage, failure_class, summary, case, card, state, reason = values
                validate_add(week, stage, failure_class, summary)
                weeks[week] += 1
                if finding != f"F-{week}-{weeks[week]}" or state not in {"open", "closed", "repeat"}:
                    raise LedgerError("invalid finding id or state")
                if state == "closed" or (state == "repeat" and card):
                    validate_close(case, reason, card)
                elif case or card or reason:
                    raise LedgerError("unexpected closure fields")
                rows.append(dict(zip(COLUMNS, values)))
        except ValueError:
            raise LedgerError(f"bad-ledger {line_no}") from None
        if stat.S_IMODE(os.fstat(source.fileno()).st_mode) != 0o600:
            raise LedgerError("ledger mode must be 0600")
    return rows


def write_ledger(path, rows):
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".npp-findings-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(HEADER + "\n")
            for row in rows:
                output.write("\t".join(row[column] for column in COLUMNS) + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def append(rows, week, stage, failure_class, summary):
    number = 1 + sum(row["week"] == week for row in rows)
    finding = f"F-{week}-{number}"
    repeat = any(row["card"] and row["class"] == failure_class for row in rows)
    values = (finding, week, stage, failure_class, summary, "", "", "repeat" if repeat else "open", "")
    rows.append(dict(zip(COLUMNS, values)))
    return finding


def update(path, args, drafts=None):
    # Lock a stable sidecar, not the ledger inode replaced on each commit.
    fd = open_private(path.with_name(f".{path.name}.lock"), os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.fchmod(fd, 0o600)
        # Read under the lock, so concurrent imports of one export add each finding once.
        rows = read_ledger(path)
        changed = True
        if args.command == "add":
            output = [append(rows, args.week, args.stage, args.failure_class, args.summary)]
        elif args.command == "import":
            keys = ledger_keys(rows)
            drafts = drafts or {}
            output = []
            for (kind, ref, _), (stage, failure_class, summary) in drafts.items():
                full_key = import_key(kind, ref, failure_class, args.week)
                if full_key not in keys:
                    keys.add(full_key)
                    output.append(append(rows, args.week, stage, failure_class, summary))
            existing = len(drafts) - len(output)
            changed = bool(output)  # A repeat import leaves the ledger bytes untouched.
            output.append(f"PASS npp_findings import added={len(output)} existing={existing}")
        else:
            finding = args.id
            row = next((row for row in rows if row["id"] == finding), None)
            if row is None or row["card"]:
                raise LedgerError("no matching open finding")
            row.update(card=args.card, case_id=args.case or "", reason=args.reason or "")
            if row["state"] != "repeat":
                row["state"] = "closed"
            output = [finding]
        if changed:
            write_ledger(path, rows)
    finally:
        os.close(fd)
    for line in output:
        print(line)


def report(rows, as_of):
    pending = [row for row in rows if not row["card"]]
    repeats = sum(row["state"] == "repeat" for row in rows)
    print(f"open={len(pending)} closed={len(rows) - len(pending)} repeat={repeats}")
    for row in pending:
        print(row["id"])
    if any(as_of - monday(row["week"]) > timedelta(weeks=2) for row in pending):
        print("FAIL npp_findings stale")
        return 1
    print("PASS npp_findings")
    return 0


def main(argv=None):
    parser = PrivateParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add")
    add.add_argument("--week", required=True)
    add.add_argument("--stage", required=True)
    add.add_argument("--class", dest="failure_class", required=True)
    add.add_argument("--summary", required=True)
    close = commands.add_parser("close")
    close.add_argument("id")
    closure = close.add_mutually_exclusive_group(required=True)
    closure.add_argument("--case")
    closure.add_argument("--reason")
    close.add_argument("--card", required=True)
    weekly = commands.add_parser("report")
    weekly.add_argument("--week", required=True, help="ISO week used to check the age of all open findings")
    drafts = commands.add_parser("import", help="draft open findings from a redacted npp_review_export file")
    drafts.add_argument("--export", required=True, type=Path)
    drafts.add_argument("--week", required=True, help="ISO week the new findings are filed under")
    args = parser.parse_args(argv)
    try:
        path = ledger_path(args.ledger)
        if args.command == "report":
            return report(read_ledger(path), monday(args.week))
        if args.command == "import":
            monday(args.week)
            update(path, args, draft_findings(args.export, args.week))
            return 0
        if args.command == "add":
            validate_add(args.week, args.stage, args.failure_class, args.summary)
        else:
            validate_close(args.case or "", args.reason or "", args.card)
        update(path, args)
    except LedgerError as error:
        print(f"FAIL {error}")
        return 1
    except (OSError, ValueError, RuntimeError):
        print("FAIL npp_findings ledger I/O")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
