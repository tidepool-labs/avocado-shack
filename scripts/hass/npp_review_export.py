#!/usr/bin/env python3
"""Project a private Hass transcript export and NPP receipts to local review JSONL."""

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.npp import evidence
from hass.npp.private_numbers import values
from hass.npp.receipt import JOB_RE, read_artifact


URL = re.compile(r"\b(?:[a-z][a-z0-9+.-]*://|www\.)[^\s<>\"']+", re.I)
EMAIL = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@(?:[\w-]+\.)+[\w-]+")
# Require an alphabetic final label: a decimal such as 3.50 is not a host.
BARE_URL = re.compile(r"(?<![\w-])(?<![\w-]\.)(?:(?:[^\W_]|-)+\.)+[^\W\d_]{2,}"
                      r"(?![\w-]|\.[\w-])(?::[0-9]+)?(?:[/?#][^\s<>\"']*)?")
PHONE = re.compile(
    r"(?<!\w)(?:\+\d(?:[ .()\t-]*\d){6,14}|"
    r"(?:1[ .\t-]?)?(?:\(\d{3}\)|\d{3})[ .\t-]*\d{3}[ .\t-]*\d{4}|"
    r"\d{3}[ .\t-]+\d{4})(?:[ \t]*(?:ext\.?|x|#)[ \t]*\d+)?(?!\w)", re.I)
# A suffix lets us remove street names even when no house number is supplied.
ADDRESS = re.compile(
    r"(?<![\w<])(?:\d+[a-z]?[ \t]+)?(?:[^\W\d_][\w’'-]*[ \t]+){1,5}"
    r"(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|lane|ln|court|ct|"
    r"place|pl|way|terrace|ter|circle|cir|parkway|pkwy|highway|hwy)\b\.?"
    r"(?:[ \t]+(?:apt\.?|suite|unit|#)[ \t]*[\w-]+)?", re.I)
MONEY = re.compile(r"[$¢€£¥₹]|\b(?:usd|cad|aud|eur|gbp|jpy|bucks?|dollars?|cents?|euros?|quid|pence)\b", re.I)
OTHER_NUMBERS = re.compile(
    r"\b(?:oh|hundreds?|thousands?|millions?|billions?|trillions?|grand|point|"
    r"half|halves|quarters?|couples?|pairs?|scores?|gross)\b", re.I)
JOB_STATES = frozenset("working asking card_out editing retake expired approved published publish_failed".split())
VERSION_STATES = frozenset("building queued delivered superseded approved".split())
IMAGE_VARIANTS = (None, "raw", "house", "polished")
SLOW_SEGMENT_S = 75  # Design section 1.3: per-segment p90 target.


def redact(text):
    """Redact supported contact, street-address, money and number forms in free text."""
    return _redact(text)


def _redact(text, identities=None):
    text = unicodedata.normalize("NFKC", text)
    # Match whole contacts before identities that may occur inside them. Keep
    # the angle delimiters for the later matchers, but protect the markers from
    # identity matching and do not mistake literal private-use text for a marker.
    prefix = "<"
    codes = "\ue000\ue001\ue002\ue003\ue004"
    while any(prefix + code + ">" in text for code in codes):
        prefix += "\ue000"
    url, email, identity, phone, address = (prefix + code + ">" for code in codes)
    for pattern, replacement in ((URL, url), (EMAIL, email), (BARE_URL, url),
                                 (PHONE, phone), (ADDRESS, address)):
        text = pattern.sub(replacement, text)
    if identities:
        parts = re.split(f"({re.escape(prefix)}[{codes}]>)", text)
        parts[::2] = [identities.sub(identity, part) for part in parts[::2]]
        text = "".join(parts)
    text = MONEY.sub("<money>", text)
    # Apply from the right to keep private_numbers' original offsets intact.
    for number in reversed(values(text)):
        text = text[:number.start] + "<n>" + text[number.end:]
    text = OTHER_NUMBERS.sub("<n>", text)
    for code, name in zip(codes, ("url", "email", "id", "phone", "address")):
        text = text.replace(prefix + code + ">", f"<{name}>")
    return re.sub(r"<{2,}", "<", text)


def _day(value):
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError
    return date.fromisoformat(value)


def _since(value):
    try:
        return _day(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from None


def events(path, since):
    raw = []
    private = set()
    with path.open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            if not isinstance(row, dict) or not all(isinstance(row.get(key), str) for key in
                    ("utc", "chat", "sender", "direction", "kind", "text", "disposition")):
                raise ValueError
            timestamp = datetime.fromisoformat(row["utc"])
            if (timestamp.tzinfo is None or row["direction"] not in ("in", "out")
                    or not row["chat"] or not isinstance(row.get("attachments"), list)):
                raise ValueError
            private.update(unicodedata.normalize("NFKC", row[key]) for key in ("chat", "sender") if row[key])
            if timestamp.date() >= since:
                raw.append((timestamp.date().isoformat(), row))
    # Responses can echo another row's identity inside a larger token. Prefer
    # the longest literal when identities share a prefix.
    identities = (re.compile("|".join(re.escape(value) for value in sorted(private, key=lambda s: (-len(s), s))),
                             re.I) if private else None)
    chats = {}
    return [dict(day=day, chat=chats.setdefault(row["chat"], f"chat-{len(chats) + 1}"),
                 dir=row["direction"], kind=_redact(row["kind"], identities),
                 text_redacted=_redact(row["text"], identities), attachments=len(row["attachments"]),
                 disposition=_redact(row["disposition"], identities)) for day, row in raw]


def _instant(value):
    """An aware time, None for an absent one; anything else makes the receipt bad."""
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError
    moment = datetime.fromisoformat(value)
    if moment.utcoffset() is None:
        raise ValueError
    return moment


def _segment_seconds(segment):
    # An open segment, or one written without times, has no measured duration.
    start, end = _instant(segment.get("accepted_at")), _instant(segment.get("ended_at"))
    if start is None or end is None:
        return None
    if end < start:
        raise ValueError
    return (end - start).total_seconds()


EVIDENCE_FACTS = ("stages", "fallbacks", "drifted_steps", "failed_checks", "approval_role")


def _review_names(names):
    # Schema-valid identifiers can still be private. Treat any dotted name as
    # ambiguous here: even a hostname missed by the prose redactor (e.g. an
    # ASCII-encoded IDN) must not pass through. Keep one entry per distinct name.
    return sorted("[redacted]" if "." in name or redact(name) != name else name for name in set(names))


def _evidence_summary(row):
    """Return (summary fields, status) from validated evidence only; never a partial record."""
    doc = row.get("evidence")
    if doc is None:  # Receipts written before HRM-03 carry no evidence.
        return dict.fromkeys(EVIDENCE_FACTS), "missing"
    try:
        problems = evidence.validate(doc)
    except (TypeError, ValueError, AttributeError, RecursionError):
        problems = ["evidence: unreadable"]
    if problems:
        return dict.fromkeys(EVIDENCE_FACTS), "bad"
    return dict(
        stages=[dict(stage=s["stage"], ms=round(s["ended_ms"] - s["started_ms"], 3), outcome=s["outcome"])
                for s in doc["stages"]],
        fallbacks=_review_names(doc["fallbacks"]),
        drifted_steps=_review_names(m["step"] for m in doc["models"] if m["drift"]),
        failed_checks=_review_names(c["name"] for c in doc["checks"] if c["verdict"] == "fail"),
        approval_role=doc["approval"]["role"] if doc["approval"] else None,
    ), "recorded"


def receipt_summary(path):
    """Return the export row and job summary for one receipt; raise if the receipt itself is bad."""
    job = path.parent.name
    if not re.fullmatch(JOB_RE, job) or path.parent.is_symlink():
        raise ValueError
    row = json.loads(read_artifact(path))
    if row["job_id"] != job or row["state"] not in JOB_STATES:
        raise ValueError
    if not isinstance(row["segments"], list) or not all(isinstance(s, dict) for s in row["segments"]):
        raise ValueError
    if not isinstance(row["versions"], list):
        raise ValueError
    versions = []
    delivered = set()
    for version in row["versions"]:
        if not isinstance(version, dict):
            raise ValueError
        n, state, image = version["n"], version["state"], version["image_variant"]
        if type(n) is not int or n < 1 or state not in VERSION_STATES or image not in IMAGE_VARIANTS:
            raise ValueError
        # A later edit marks a delivered card superseded, so the receipt time is the delivery
        # signal; delivered and approved states imply delivery for receipts without that time.
        if _instant(version.get("delivered_at")) is not None or state in ("delivered", "approved"):
            delivered.add(n)
        versions.append(dict(n=n, state=state, image_variant=image))
    seconds = [_segment_seconds(segment) for segment in row["segments"]]
    facts, status = _evidence_summary(row)
    summary = dict(
        segment_s=[None if s is None else round(s, 3) for s in seconds],  # receipt order
        slow=any(s is not None and s > SLOW_SEGMENT_S for s in seconds),
        **facts,
        edits=max(len(delivered) - 1, 0),
        # Each question reply ends its segment with outcome "question".
        questions=sum(segment.get("outcome") == "question" for segment in row["segments"]),
        evidence=status,
    )
    return dict(job=job, state=row["state"], segments=len(row["segments"]), versions=versions, summary=summary)


class UnsafeOutput(ValueError):
    """A fixed, non-sensitive output refusal reason."""


def output_path(path):
    parent = path.parent.resolve(strict=True)
    for start in (path.absolute().parent, parent):
        for folder in (start, *start.parents):
            marker = folder / ".git"
            if folder.name == ".git" or marker.exists() or marker.is_symlink():
                raise UnsafeOutput("output-in-worktree")
    target = parent / path.name
    if target.is_symlink():
        raise UnsafeOutput("output-symlink")
    return target


def write_output(path, rows, force):
    # Stage privately; neither a partial export nor a previously broad file mode is exposed.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as out:
        tmp = Path(out.name)
        try:
            os.fchmod(out.fileno(), 0o600)
            for row in rows:
                out.write(json.dumps(row, ensure_ascii=True) + "\n")
            out.close()
            if force:
                os.replace(tmp, path)
            else:
                os.link(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", required=True, type=Path, help="JSONL from hass.transcript export")
    parser.add_argument("--receipts", required=True, type=Path, help="NPP root containing job directories")
    parser.add_argument("--since", required=True, type=_since, help="inclusive transcript day (YYYY-MM-DD)")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    try:
        rows = events(args.export, args.since)
    except (OSError, ValueError, RecursionError):
        print("FAIL bad-export")
        return 1
    try:
        root = args.receipts.resolve(strict=True)
        receipts = sorted(root.glob("*/receipt.json")) if root.is_dir() else None
        if receipts is None:
            raise ValueError
    except (OSError, ValueError, RuntimeError):
        print("FAIL bad-receipts-dir")
        return 1
    jobs = []
    for path in receipts:
        try:
            job = receipt_summary(path)
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            job = path.parent.name
            print("NOTE bad-receipt " + (job if re.fullmatch(JOB_RE, job) else "<invalid-job>"))
            continue
        if job["summary"]["evidence"] == "bad":  # The job stays; its evidence facts are left out.
            print("NOTE bad-evidence " + job["job"])
        jobs.append(job)
    try:
        out = output_path(args.out)
        if out == args.export.resolve() or out in receipts:
            raise UnsafeOutput("output-is-input")
        write_output(out, (*rows, *jobs), args.force)
    except FileExistsError:
        print("FAIL output-exists")
        return 1
    except UnsafeOutput as exc:
        print(f"FAIL {exc}")
        return 1
    except (OSError, ValueError, RuntimeError):
        print("FAIL output-unavailable")
        return 1
    print(f"PASS npp_review_export {len(rows)} events {len(jobs)} jobs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
