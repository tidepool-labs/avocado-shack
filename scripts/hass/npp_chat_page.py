#!/usr/bin/env python3
"""Render a Hass JSONL export and an attachment copy as a private offline page."""

import argparse
import base64
from datetime import datetime
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import unicodedata

ROOT = str(Path(__file__).resolve().parents[2])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SHA = re.compile(r"[0-9a-f]{64}")
# Receipt folders and bounds as hass/npp/receipt.py writes them; states are npp_versions.state values.
JOB = re.compile(r"[0-9a-f]{4,12}")
RECEIPT_MAX = 256 << 10
STATES = ("building", "queued", "delivered", "superseded", "approved")
RECEIPT_CSS = """.version { font-size: .85rem; font-weight: bold; color: #345675; }
.receipt { margin: .65rem 0; padding: .5rem .85rem; border: .1rem solid #b9c6d2;
           border-radius: .5rem; background: #fff; }
.receipt.bad { border-color: #a33a3a; }
.receipt h2 { margin: 0; font-size: 1rem; }
.receipt ul { margin: .25rem 0 0; padding-left: 1.1rem; }
"""
YES = re.compile(r"\byes\s+[0-9a-f]{4,12}-[1-9][0-9]{0,8}\b", re.I | re.ASCII)
TEXT_FIELDS = ("utc", "chat", "sender", "direction", "kind", "text")
# Transcript export primary key and NOT NULL columns:
# (id, utc, chat, sender, direction, kind, text, attachments, disposition)
REQUIRED_FIELDS = ("id", *TEXT_FIELDS, "attachments", "disposition")
HEAD = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">
<title>Private Hass conversation</title>
<style>
body { margin: 1rem auto; padding: 0 .75rem; max-width: 45rem;
       font: 1rem/1.5 system-ui, sans-serif; background: #f5f6f7; color: #18222c; }
h1 { font-size: 1.35rem; }
.bubble { box-sizing: border-box; max-width: 88%; width: fit-content;
          margin: .65rem 0; padding: .65rem .85rem; border-radius: .9rem;
          overflow-wrap: anywhere; }
.in { margin-right: auto; background: #fff; }
.out { margin-left: auto; background: #dceeff; }
.meta, .missing { font-size: .85rem; color: #415264; }
.message { white-space: pre-wrap; }
.marker { font-weight: bold; border-left: .2rem solid #345675; padding-left: .4rem; }
img { display: block; max-width: 100%; height: auto; margin-top: .4rem; }
</style>
<header><h1>Private Hass conversation</h1>
"""


class PageError(Exception):
    """An operator-safe diagnostic; never include input data or paths."""


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error can echo an unrecognized private argument.
        self.print_usage(sys.stderr)
        self.exit(2, "npp_chat_page: error: invalid arguments\n")


def read_events(path, chat):
    events = []
    try:
        with path.open(encoding="utf-8") as source:
            for number, line in enumerate(source, start=1):
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise PageError("invalid event")
                for field in REQUIRED_FIELDS:
                    if field not in event:
                        raise PageError(f"missing-field {field} line {number}")
                if (type(event["id"]) is not int
                        or any(not isinstance(event[key], str) for key in TEXT_FIELDS)
                        or event["direction"] not in ("in", "out")
                        or not isinstance(event["attachments"], list)
                        or any(not isinstance(sha, str) or not SHA.fullmatch(sha)
                               for sha in event["attachments"])):
                    raise PageError("invalid event")
                if chat is None or event["chat"] == chat:
                    events.append(event)
    except ValueError:
        raise PageError("invalid export JSON") from None
    except OSError:
        raise PageError("export unavailable") from None
    return sorted(events, key=lambda event: event["id"])


def picture(sha, directory, *, png_only=False):
    for candidate in (directory / sha, directory / f"card-{sha}.png",
                      *sorted(directory.glob(f"{sha}.*"))):
        try:
            # The operator supplies copies, not symlinks back to the live store.
            if not stat.S_ISREG(candidate.lstat().st_mode):
                continue
            raw = candidate.read_bytes()
        except OSError:
            continue
        if raw.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif not png_only and raw.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        else:
            continue
        if hashlib.sha256(raw).hexdigest() == sha:
            return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
    return None


def aware(value):
    try:
        return datetime.fromisoformat(value).utcoffset() is not None
    except (TypeError, ValueError):
        return False


def evidence_items(record):
    """Summary lines from validated evidence only, and whether the evidence failed validation."""
    doc = record.get("evidence")
    if doc is None:  # Receipts written before HRM-03 carry no evidence.
        return ["no evidence recorded"], False
    try:
        from hass.npp import evidence  # HRM-03; needed only for recorded evidence.
    except ImportError:
        raise PageError("evidence validator unavailable") from None
    try:
        problems = evidence.validate(doc)
    except (TypeError, ValueError, AttributeError, RecursionError):
        problems = ["evidence: unreadable"]
    if problems:
        return ["bad evidence: failed validation"], True
    approval, publish = doc["approval"], doc["publish"]
    return [f"fallbacks: {', '.join(doc['fallbacks']) or 'none'}",
            f"approval role: {approval['role'] if approval else 'none'}",
            f"publish change id: {publish['change_id'] if publish else 'none'}",
            f"live_verify: {(publish or {}).get('live_verify') or 'none'}"], False


def read_receipt(folder):
    """Check one <job>/receipt.json copy; raise ValueError or OSError if any check fails."""
    if not stat.S_ISDIR(folder.lstat().st_mode):
        raise ValueError("not a job folder")
    fd = os.open(folder / "receipt.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as file:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("not a regular receipt")
        data = file.read(RECEIPT_MAX + 1)
    record = json.loads(data) if len(data) <= RECEIPT_MAX else None
    # A receipt copied into another job's folder must not label that job's cards.
    if (not isinstance(record, dict) or record.get("job_id") != folder.name
            or not isinstance(record.get("versions"), list)):
        raise ValueError("invalid receipt")
    versions = {}
    for row in record["versions"]:
        if not isinstance(row, dict):
            raise ValueError("invalid version")
        n, card, at, state = (row.get(key) for key in ("n", "card_png_sha", "delivered_at", "state"))
        if (type(n) is not int or n < 1 or n in versions
                or type(state) is not str or state not in STATES
                or not (card is None or type(card) is str and SHA.fullmatch(card))
                or not (at is None or type(at) is str and aware(at))):
            raise ValueError("invalid version")
        versions[n] = (card, at, state)
    return versions, *evidence_items(record)


def load_receipts(root):
    """Map each job folder to (versions, summary lines, bad evidence); None marks an unreadable receipt."""
    jobs = {}
    for folder in sorted(root.iterdir()):
        if JOB.fullmatch(folder.name):
            try:
                jobs[folder.name] = read_receipt(folder)
            except (OSError, ValueError, RecursionError):
                jobs[folder.name] = None
    return jobs


def card_index(jobs):
    """Full card PNG digest -> every (job, n, delivered_at, state) that froze exactly that card."""
    cards = {}
    for job, receipt in jobs.items():
        if receipt is None:
            continue
        for n, (card, at, state) in sorted(receipt[0].items()):
            if card is not None:
                cards.setdefault(card, []).append((job, n, at, state))
    return cards


def receipt_boxes(jobs, clean=None):
    boxes = ['<div class="receipts">']
    for job, receipt in jobs.items():
        items, bad = (["receipt unreadable"], True) if receipt is None else receipt[1:]
        if clean is not None:
            items = [clean(item) for item in items]
        boxes.append(f'<section class="receipt{" bad" if bad else ""}" data-job="{job}"><h2>Job {job}</h2>'
                     f'<ul>{"".join(f"<li>{escape(item)}</li>" for item in items)}</ul></section>')
    boxes.append("</div>")
    return boxes


def review_redactor(events):
    try:
        from scripts.hass.npp_review_export import redact
    except ImportError:
        raise PageError("review redactor unavailable") from None

    # The public text redactor handles contact and number forms, not arbitrary
    # transcript identities. Use the whole export, including filtered-out rows.
    known = {unicodedata.normalize("NFKC", event[key]) for event in events
             for key in ("chat", "sender") if event[key]}
    if not known:
        return redact
    longest_first = sorted(known, key=lambda value: (-len(value), value))
    identities = re.compile("|".join(map(re.escape, longest_first)), re.I)
    folded = sorted({value.casefold() for value in known}, key=lambda value: (-len(value), value))
    folded_identities = re.compile("|".join(map(re.escape, folded)))

    def clean(text):
        text = unicodedata.normalize("NFKC", text)
        # Match on fully folded text, but replace in the original normalized
        # text. A character such as ß occupies two positions after folding.
        folded_text = [char.casefold() for char in text]
        offsets = [index for index, part in enumerate(folded_text) for _ in part]
        spans = [(offsets[match.start()], offsets[match.end() - 1] + 1)
                 for match in folded_identities.finditer("".join(folded_text))]
        # Keep the previous re.I matches too (e.g. dotless i vs ASCII i).
        spans.extend(match.span() for match in identities.finditer(text))
        # A word marker can be consumed by the contact scrubber if the identity
        # occurred inside a URL or email. Angle brackets would split that match.
        marker = "nppidentityplaceholder"
        while marker in text.lower():
            marker += "x"
        pieces, cursor = [], 0
        # Overlapping spans from the two matchers need just one marker.
        for start, end in sorted(spans):
            if start >= cursor:
                pieces.extend((text[cursor:start], marker))
            cursor = max(cursor, end)
        pieces.append(text[cursor:])
        return redact("".join(pieces)).replace(marker, "<id>")

    return clean


def render(events, directory, jobs=None, *, clean=None):
    body, pictures, missing, ambiguous = [], {}, set(), {}
    if clean is not None and jobs is not None:
        jobs = {str(index): receipt for index, receipt in enumerate(jobs.values(), 1)}
    cards = None if jobs is None else card_index(jobs)
    messages_in = count = 0
    for event in events:
        inbound = event["direction"] == "in"
        messages_in += inbound
        meta = "" if clean is not None else (
            f'<div class="meta">{escape(event["sender"])} · {escape(event["utc"])}</div>')
        body.append(f'<article class="bubble {event["direction"]}">{meta}')
        text = event["text"]
        shown = clean(text) if clean is not None else text
        original_lines = text.split("\n")
        for index, line in enumerate(shown.split("\n")):
            marker = ""
            if not inbound and index < len(original_lines):
                if original_lines[index].startswith("Posted:"):
                    marker = " marker posted"
                elif YES.search(original_lines[index]):
                    marker = " marker approval"
            body.append(f'<div class="message{marker}">{escape(line) or "<br>"}</div>')
        for sha in event["attachments"]:
            if clean is not None and inbound:
                body.append('<div class="missing">Owner photo omitted</div>')
                continue
            if sha not in pictures:
                pictures[sha] = picture(sha, directory, png_only=clean is not None)
            uri = pictures[sha]
            if uri is None:
                missing.add(sha)
                label = "picture" if clean is not None else f"picture {sha[:8]}"
                body.append(f'<div class="missing">{label} not in copy</div>')
            else:
                count += 1
                body.append(f'<img src="{uri}" alt="Chat picture">')
            if cards is not None and not inbound:
                # Exact full digest only; a shared card is labelled with every version and flagged.
                matches = cards.get(sha, ())
                for job, n, at, state in matches:
                    delivery = at or "not delivered"
                    if clean is not None and at is not None:
                        delivery = "delivered"
                    body.append(f'<div class="version">{job}-{n} {state} · {escape(delivery)}</div>')
                if len(matches) > 1:
                    ambiguous.setdefault(sha, None)
                    body.append(f'<div class="missing">card matches {len(matches)} versions</div>')
        body.append("</article>")
    counts = (f"<p>{messages_in} messages in · {len(events) - messages_in} messages out"
              f" · {count} pictures</p></header>\n<main>")
    head, boxes = HEAD, []
    if jobs is not None:
        head, boxes = HEAD.replace("</style>", RECEIPT_CSS + "</style>", 1), receipt_boxes(jobs, clean)
    if clean is not None:
        head = head.replace("Private Hass conversation", "Redacted Hass conversation")
    return "\n".join([head, counts, *body, *boxes, "</main></html>\n"]), sorted(missing), list(ambiguous)


def output_path(path, source, directory, force, receipts=None):
    parent = path.parent.resolve()
    for start in (path.absolute().parent, parent):
        for ancestor in (start, *start.parents):
            if os.path.lexists(ancestor / ".git"):
                raise PageError("output inside git worktree")
    destination = parent / path.name
    input_roots = (source.parent.resolve(), directory, *(() if receipts is None else (receipts,)))
    if (destination == source.resolve()
            or any(os.path.commonpath((destination, root)) == os.fspath(root) for root in input_roots)):
        raise PageError("out-inside-input")
    if os.path.lexists(destination):
        if not force:
            raise PageError("output exists (use --force)")
        if not stat.S_ISREG(destination.lstat().st_mode):
            raise PageError("output must be a regular file")
    return destination


def write_page(path, html, force):
    # Prepare the complete page privately, then install it without following or
    # truncating an existing inode. link() also guards against a late collision.
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".npp-chat-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            os.fchmod(file.fileno(), 0o600)
            file.write(html)
        if force:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv=None):
    parser = PrivateParser(prog="npp_chat_page", description=__doc__)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--attachments", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--chat", help="only show events from this chat ID")
    parser.add_argument("--redact", action="store_true",
                        help="remove chat identities, redact message text and omit owner photos")
    parser.add_argument("--force", action="store_true", help="replace an existing output file")
    parser.add_argument("--receipts", type=Path, metavar="DIR",
                        help="copy of NPP job folders (<job>/receipt.json): label card versions and"
                             " add a summary box per job")
    args = parser.parse_args(argv)
    try:
        events = read_events(args.export, None if args.redact else args.chat)
        clean = review_redactor(events) if args.redact else None
        if args.redact and args.chat is not None:
            events = [event for event in events if event["chat"] == args.chat]
        directory = args.attachments.resolve()
        if not directory.is_dir():
            raise PageError("attachment copy unavailable")
        receipts = None if args.receipts is None else args.receipts.resolve()
        if receipts is not None and not receipts.is_dir():
            raise PageError("receipts unavailable")
        destination = output_path(args.out, args.export, directory, args.force, receipts)
        jobs = None if receipts is None else load_receipts(receipts)
        page, missing, ambiguous = render(events, directory, jobs, clean=clean)
        write_page(destination, page, args.force)
    except PageError as error:
        print(f"FAIL {error}")
    except (OSError, RuntimeError, ValueError):
        print("FAIL could not create page")
    else:
        for job, receipt in (jobs or {}).items():
            if receipt is None:
                print(f"NOTE bad-receipt {job}")
        for job, receipt in (jobs or {}).items():
            if receipt is not None and receipt[2]:
                print(f"NOTE bad-evidence {job}")
        for sha in ambiguous:
            print(f"NOTE ambiguous-card {sha[:8]}")
        for sha in missing:
            print(f"NOTE missing-attachment {sha[:8]}")
        print(f"PASS npp_chat_page {len(events)} events")
        return 0
    print("FAIL npp_chat_page")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
