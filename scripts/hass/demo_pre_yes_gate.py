#!/usr/bin/env python3
"""L15: the gate the person running the OFF demo reads BEFORE typing a `yes`, and the check they read AFTER it.

    python3 -B scripts/hass/demo_pre_yes_gate.py before --state STATE --media MEDIA --worktree WT --job JOB --photo FILE --version N
    python3 -B scripts/hass/demo_pre_yes_gate.py after  --state STATE --worktree WT --job JOB --photo FILE --version N

It joins only things that match, and READS only (nothing is opened for writing, nothing is sent, no service is touched):

  listing  the job the photo started (its stored photo SHA-256) and the version the owner is about to approve
  card     that version's rendered card as DELIVERED in the chat: a confirmed delivery, a regular media file whose bytes hash to the
           version's card hash, and an outgoing chat event that attaches it
  served   what the shop serves now (the public catalog in the worktree and its photo file)

`before` prints `READY yes <job>-<n>` only when: the job exists and is waiting for a yes; the photo in your hand is the listing's
photo; the version is the newest one and the one you hold; its card was delivered and its file bytes match; the card is in the
chat; the card's picture (when it is the owner's own photo) is the listing's photo; the listing has a name; and the shop does
not serve that name yet. Anything else prints `ABORT <label>` and you do NOT type the yes.
`after` prints `SERVED undo` when the served photo file is the listing's photo, otherwise `ABORT <label>`. `undo` is the take-down word.

Output is a fixed word and a fixed label only: never a name, text, id, path or byte. Exit 0 READY/SERVED, 1 ABORT, 2 unusable arguments.
This is a rehearsal aid for the attended demo: it does not authorize or perform a yes, and it is not a live listing.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import stat
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SHA = re.compile(r"[0-9a-f]{64}")
JOB = re.compile(r"[0-9a-f]{4,64}")
CATALOG = "storefront-mockup/catalog-products.js"
CATALOG_HEAD = b"const catalog="
PHOTO_MAX = 20 * 1024 * 1024
DB_NAME = "conversation.sqlite3"


def _viewer():
    spec = importlib.util.spec_from_file_location("restored_chat_view", HERE / "restored_chat_view.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_file(path, limit=PHOTO_MAX):
    """SHA-256 of a regular, non-link file no bigger than `limit`; None for anything else."""
    path = Path(path)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def open_conversation(state):
    """Read-only handle on the saved conversation DB (no mkdir, no chmod, no create, no link followed)."""
    path = Path(os.path.abspath(state)) / DB_NAME
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077:
        raise ValueError("unsafe conversation store")
    db = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=1)
    db.row_factory = sqlite3.Row
    return db


def served_records(worktree):
    """{public name: record} from the worktree's served catalog; None when it cannot be read."""
    try:
        path = Path(worktree) / CATALOG
        if path.is_symlink() or not path.is_file():
            return None
        first = path.read_bytes().split(b"\n", 1)[0]
        if not first.startswith(CATALOG_HEAD):
            return None
        products = json.loads(first[len(CATALOG_HEAD):].rstrip(b";"))
        return {p["name"]: p for p in products if isinstance(p, dict) and isinstance(p.get("name"), str)}
    except (OSError, ValueError):
        return None


def before_yes(db, media, events, job, photo_sha, version, served_names):
    """('READY', yes_line) or ('ABORT', label). `events` = transcript rows, `served_names` = public names served now."""
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        return "ABORT", "version-mismatch"
    if not (isinstance(job, str) and JOB.fullmatch(job)):
        return "ABORT", "no-such-listing"
    row = db.execute("SELECT state, photo_sha, current_version FROM npp_jobs WHERE job_id=?", (job,)).fetchone()
    if row is None:
        return "ABORT", "no-such-listing"
    if not (isinstance(photo_sha, str) and SHA.fullmatch(photo_sha)) or row["photo_sha"] != photo_sha:
        return "ABORT", "photo-mismatch"
    if row["state"] != "card_out":
        return "ABORT", "listing-not-waiting-for-a-yes"
    if row["current_version"] != version:
        return "ABORT", "version-mismatch"
    ver = db.execute("SELECT state, delivered_at, card_png_sha, image_variant, image_sha256, listing_json "
                     "FROM npp_versions WHERE job_id=? AND n=?", (job, version)).fetchone()
    if ver is None:
        return "ABORT", "version-mismatch"
    if ver["state"] != "delivered" or not ver["delivered_at"]:
        return "ABORT", "card-not-delivered"
    card_sha = ver["card_png_sha"]
    if not (isinstance(card_sha, str) and SHA.fullmatch(card_sha)):
        return "ABORT", "card-not-delivered"
    if sha256_file(Path(media) / "npp" / job / f"card-{card_sha}.png") != card_sha:
        return "ABORT", "card-bytes-missing-or-changed"
    if not any(e["direction"] == "out" and card_sha in e["attachments"] for e in events):
        return "ABORT", "card-not-in-chat"
    if ver["image_variant"] == "raw" and ver["image_sha256"] != photo_sha:
        return "ABORT", "card-photo-differs-from-listing-photo"
    try:
        name = json.loads(ver["listing_json"]).get("name")
    except (TypeError, ValueError, AttributeError):
        name = None
    if not name:
        return "ABORT", "listing-has-no-name"
    if name in served_names:
        return "ABORT", "already-served"
    return "READY", f"yes {job}-{version}"


def after_yes(worktree, record, photo_sha):
    """('SERVED', 'undo') when the served photo file is the listing's photo, else ('ABORT', label)."""
    if record is None:
        return "ABORT", "not-served"
    image = record.get("image")
    if not isinstance(image, str) or not image or image.startswith("/") or ".." in Path(image).parts:
        return "ABORT", "served-photo-differs"
    if sha256_file(Path(worktree) / "storefront-mockup" / image) != photo_sha:
        return "ABORT", "served-photo-differs"
    return "SERVED", "undo"


def listing_name(db, job, version):
    row = db.execute("SELECT listing_json FROM npp_versions WHERE job_id=? AND n=?", (job, version)).fetchone()
    try:
        return json.loads(row["listing_json"]).get("name") if row else None
    except (TypeError, ValueError, AttributeError):
        return None


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "demo_pre_yes_gate: invalid arguments\n")


def main(argv=None):
    parser = PrivateParser(prog="demo_pre_yes_gate", description=__doc__.split("\n\n")[0])
    parser.add_argument("gate", choices=("before", "after"))
    parser.add_argument("--state", type=Path, required=True, help="restored (or live OFF) state dir")
    parser.add_argument("--media", type=Path, help="media dir (needed for `before`)")
    parser.add_argument("--worktree", type=Path, required=True, help="the shop worktree that is served")
    parser.add_argument("--job", required=True)
    parser.add_argument("--photo", type=Path, required=True, help="the photo file you hold for this listing")
    parser.add_argument("--version", type=int, required=True)
    args = parser.parse_args(argv)
    if args.gate == "before" and args.media is None:
        parser.error("media")
    try:
        photo_sha = sha256_file(args.photo)
        if photo_sha is None:
            print("ABORT photo-unreadable")
            return 1
        with contextlib.closing(open_conversation(args.state)) as db:
            records = served_records(args.worktree)
            if records is None:
                print("ABORT catalog-unreadable")
                return 1
            if args.gate == "before":
                events = _viewer().rows(args.state)
                gate, detail = before_yes(db, args.media, events, args.job, photo_sha, args.version, set(records))
            else:
                if db.execute("SELECT 1 FROM npp_jobs WHERE job_id=? AND photo_sha=?", (args.job, photo_sha)).fetchone() is None:
                    gate, detail = "ABORT", "photo-mismatch"
                else:
                    gate, detail = after_yes(args.worktree, records.get(listing_name(db, args.job, args.version)), photo_sha)
    except Exception:  # a fixed label, never a traceback that could carry a path or a value
        print("ABORT could-not-check")
        return 1
    print(f"{gate} {detail}")
    return 0 if gate in ("READY", "SERVED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
