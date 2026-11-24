"""Build and store finance-local inventory receipts. No till or chat I/O."""
import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from hass.clover.cache import CacheUnsafe, _private_dir, _private_file
from hass.conversation import sender_key

# Copy only the inventory wire fields, never a whole request/response envelope.
_WIRE = frozenset("name price priceType unitName sku hidden available quantity elements category item id".split())
_FACTS = _WIRE | {"stock", "itemStock", "categories", "modifiedTime", "stockModifiedTime"}
_FINDINGS = frozenset("not-found hidden name price sku count category ambiguous-name unlinked price-unit "
                      "hidden-vs-active no-word stock-word".split())
_PHONE = re.compile(r"(?P<guid>\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b)"
                    r"|(?<!\w)(?:\+(?:[ .()-]*\d){8,15}|(?:\d|\(\d)(?:[ .()-]*\d){9,14})(?!\w)", re.I)
_BEARER = re.compile(r"(?i)\bbearer[ \t]+[^\s,;]+")
_HEADER = re.compile(r"(?im)^[ \t]*(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*:[^\n]*")


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def _pick(value, keys):
    if isinstance(value, dict):
        return {k: _pick(v, keys) for k, v in value.items() if k in keys}
    if isinstance(value, (list, tuple)):
        return [_pick(v, keys) for v in value]
    return value


def _secrets(value):
    """Find explicit credential fields so duplicates elsewhere are masked too."""
    if isinstance(value, dict):
        for key, child in value.items():
            label = re.sub(r"[^a-z]", "", key.lower())
            if isinstance(child, str) and (label.endswith(("token", "apikey", "authorization")) or label == "cookie"):
                if child:
                    yield child
                    if child.lower().startswith("bearer ") and child[7:].strip():
                        yield child[7:].strip()
            else:
                yield from _secrets(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _secrets(child)


def _clean(value, secrets):
    if isinstance(value, str):
        value = _HEADER.sub("[redacted]", value)
        for secret in secrets:
            value = value.replace(secret, "[redacted]")
        return _PHONE.sub(lambda m: m.group("guid") or "[redacted]", _BEARER.sub("[redacted]", value))
    if isinstance(value, dict):
        return {k: _clean(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v, secrets) for v in value]
    return value


def _verdict(verdict):
    return None if verdict is None else {"ok": verdict.ok, "findings": [w for w in verdict.findings if w in _FINDINGS]}


def _requests(requests, item_id=None):
    calls = []
    for req in requests:
        body = _pick(req["json"], _WIRE)
        if item_id:
            body = json.loads(json.dumps(body).replace("{newItemId}", item_id))
        calls.append({"method": req["method"], "path": req["path"], "json": body})
    return calls


def build(bundle_row, journal_rows, preview_text, register_verdict, site_verdict, approver_role, transcript) -> dict[str, Any]:
    """Project a BundleJournal row and ordered changes rows (SQLite or decoded).

    ``transcript`` maps count/preview/yes to provider IDs or transcript event
    dicts (provider_id, utc, and optionally sender on yes), plus optional chat_page.
    The journal does not retain per-call delivery evidence on a live failure.
    Such requests are recorded as planned, not claimed as sent.
    """
    if approver_role not in ("mike", "g"):
        raise ValueError("approver role")
    bundle = bundle_row["bundle"]
    code = bundle["code"]
    rows = [dict(row) for row in journal_rows]
    primary = next((row for row in rows if row["code"] == code), {})
    events = {key: transcript.get(key) for key in ("count", "preview", "yes")}
    yes_sender = events["yes"].get("sender") if isinstance(events["yes"], dict) else None
    sender = yes_sender or primary.get("sender") or bundle_row["sender"]
    normalized = sender_key(sender)
    if normalized is None:
        raise ValueError("receipt sender")
    links = {key: event.get("provider_id") if isinstance(event, dict) else event for key, event in events.items()}
    if transcript.get("chat_page"):
        links["chat_page"] = os.fspath(transcript["chat_page"])
    expires = primary["expires"] if primary else bundle_row["expires"]
    times = {"expires": expires, **{k: e["utc"] for k, e in events.items() if isinstance(e, dict) and e.get("utc")}}
    day = primary.get("day")
    if not day:
        moment = datetime.fromisoformat(times["yes"]) if "yes" in times else datetime.fromtimestamp(expires, timezone.utc)
        day = moment.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
    times["day"] = day

    requests, journal, read_back = [], [], []
    sources = [bundle_row, rows, transcript]
    for row in rows:
        draft, result = _json(row["draft"]), _json(row["result"])
        sources.extend((draft, result))
        status = row["status"]
        journal.append({k: row[k] for k in ("code", "status", "expires", "day")})
        if status == "dry-run":
            calls, evidence = _requests(result), "rehearsed"
        elif isinstance(result, dict) and result.get("result_item_id"):
            # Resolve the same create placeholder as apply. Recovery can confirm
            # state without observing delivery, so this is not a transport log.
            calls = _requests(result.get("requests", draft["requests"]), result["result_item_id"])
            evidence = "settled"
            observed = result.get("read_back")
            if observed is None and status == "applied":
                # Only a match establishes the approved values. Older failed
                # rows without explicit read-back evidence remain unknown.
                observed = result.get("after", draft.get("after", {}))
            read_back.append({"code": row["code"], "item_id": result["result_item_id"],
                              "revision": _pick(result.get("result_base"), _FACTS),
                              "values": _pick(observed, _FACTS)})
        else:
            calls, evidence = _requests(draft["requests"]), "planned"
        requests.append({"code": row["code"], "evidence": evidence, "calls": calls})
    if not rows and bundle.get("till"):
        requests.append({"code": code, "evidence": "planned", "calls": _requests(bundle["till"]["requests"])})

    state = bundle_row["state"]
    receipt = {"code": code, "approver_role": approver_role, "times": times,
               "preview_text": preview_text, "bundle_hash": bundle["bundle_hash"], "requests": requests,
               "journal": journal, "bundle_state": state, "till_state": bundle_row["till"],
               "site_state": bundle_row["site"], "read_back": read_back, "transcript": links,
               "register_verdict": _verdict(register_verdict), "site_verdict": _verdict(site_verdict)}
    if state != "undone" and (bundle_row.get("undo_result") or any(r["status"] == "applied" for r in rows)):
        # Existing undo commands take the applied change's code, not a newly minted approval.
        receipt["undo_code"] = code
    secrets = sorted({sender, normalized, *_secrets(sources)}, key=len, reverse=True)
    return {**{k: _clean(v, secrets) for k, v in receipt.items()},
            "sender_key": hashlib.sha256(normalized.encode()).hexdigest(),
            "preview_hash": hashlib.sha256(preview_text.encode()).hexdigest()}


def _guard_path(folder):
    for part in (*reversed(folder.parents), folder):
        if part.is_symlink() or os.path.lexists(part / ".git"):
            raise CacheUnsafe("receipt folder")


def write(state, receipt):
    """Use the recorded day on first write; atomically replace by code thereafter."""
    day, code = receipt["times"]["day"], receipt["code"]
    if date.fromisoformat(day).isoformat() != day or not re.fullmatch(r"[0-9a-f]{8}", code):
        raise ValueError("receipt name")
    state = Path(state).absolute()
    folder = state / "clover" / "receipts"
    if ".." in state.parts:
        raise CacheUnsafe("receipt folder")
    _guard_path(folder)
    for private in (state, folder.parent, folder):
        _private_dir(private, create=True)
    # Serialize path selection and replacement, including first writes on
    # different dates. Lock the directory so no extra receipt file is needed.
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        year, pair = "[0-9]" * 4, "[0-9]" * 2
        existing = list(folder.glob(f"{year}-{pair}-{pair}-{code}.json"))
        if len(existing) > 1:
            raise CacheUnsafe("duplicate receipt code")
        path = existing[0] if existing else folder / f"{day}-{code}.json"
        _replace_receipt(path, receipt)
        return path
    finally:
        os.close(fd)


def _replace_receipt(path, receipt):
    if os.path.lexists(path) and not stat.S_ISREG(path.lstat().st_mode):
        raise CacheUnsafe("receipt file")
    _private_file(path, create=False)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        pending = Path(tmp.name)
        try:
            _private_file(pending, create=False)
            json.dump(receipt, tmp, ensure_ascii=False, allow_nan=False, sort_keys=True)
            tmp.write("\n")
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp.close()
            os.replace(pending, path)
        finally:
            pending.unlink(missing_ok=True)


def summary(receipts):
    """Count each receipt once by outcome, and each failed check by finding."""
    totals = dict.fromkeys(("changes", "applied", "dry-run", "undone", "failed"), 0)
    findings = Counter()
    for receipt in receipts:
        totals["changes"] += 1
        states = {row["status"] for row in receipt["journal"]} | {receipt["till_state"]}
        bundle = receipt["bundle_state"]
        if bundle == "undone":
            totals["undone"] += 1
        elif "dry-run" in states:
            totals["dry-run"] += 1
        elif bundle in {"failed", "split", "partial", "till-uncertain"} or states & {"failed", "uncertain"}:
            totals["failed"] += 1
        elif "applied" in states:
            totals["applied"] += 1
        for key in ("register_verdict", "site_verdict"):
            if (verdict := receipt.get(key)) and not verdict["ok"]:
                findings.update(_FINDINGS.intersection(verdict["findings"]))
    return {**totals, "check_failures": dict(sorted(findings.items()))}
