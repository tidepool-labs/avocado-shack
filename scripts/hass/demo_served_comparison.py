#!/usr/bin/env python3
"""L17: the check the person running the OFF demo reads AFTER the yes: does the shop serve the card that was approved?

    python3 -B scripts/hass/demo_served_comparison.py --state STATE --worktree WT --job JOB --photo FILE --version N

It READS only (nothing is opened for writing, nothing is sent, no service is touched) and joins:

  approved  the version's saved draft (the exact public fields the owner saw on the delivered card: name, price, descriptor,
            picture description, shelf, brand) and the photo that draft carries
  served    the shop's catalog in the worktree and the photo file that catalog record points to

`MATCH undo` (exit 0) only when exactly one served record carries the approved name and every approved field and the approved photo
bytes are what the shop serves, the record holds public fields only, and no other record serves that photo. Anything else prints
`MISMATCH <label>[,<label>...]` (exit 1, labels sorted): a record for the wrong item, a stale or swapped photo, an edited price or
descriptor, a leftover duplicate, a non-public field. It never looks at the approval history: "posted" in the chat does not make a
mismatch pass. `undo` is the take-down word.

Every path (state, worktree, photo, served photo) must be free of links: each component is opened without following one.
Output is a fixed word and fixed labels only: never a name, text, price, id, path or byte. Exit 2 for unusable arguments.
A rehearsal aid for the attended demo: it does not authorize or perform a yes or a take-down, and it is not a live listing.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_gate():
    spec = importlib.util.spec_from_file_location("demo_pre_yes_gate", HERE / "demo_pre_yes_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()

PUBLIC_KEYS = {"id", "name", "brand", "category", "image", "description", "producerKey", "displayBrand",
               "imageAlt", "sellingPrice", "addedOn"}
PRIVATE_RE = re.compile(r"\b(cost|qty|quantity|stock|count|margin|wholesale|supplier)(?:s|es)?\b", re.I)
# approved product.add argument -> (served record key, label when they differ)
FIELDS = (("name", "name", "name-differs"), ("sellingPrice", "sellingPrice", "price-differs"),
          ("description", "description", "descriptor-differs"), ("imageAlt", "imageAlt", "picture-text-differs"),
          ("category", "category", "shelf-differs"), ("brand", "brand", "brand-differs"),
          ("producerKey", "producerKey", "maker-differs"))


def served_list(worktree):
    """The served catalog's records in order; None when it cannot be read (or a link is on its path)."""
    data = gate.read_plain(Path(worktree) / gate.CATALOG)
    if data is None:
        return None
    first = data.split(b"\n", 1)[0]
    if not first.startswith(gate.CATALOG_HEAD):
        return None
    try:
        products = json.loads(first[len(gate.CATALOG_HEAD):].rstrip(b";"))
    except ValueError:
        return None
    return products if isinstance(products, list) and all(isinstance(p, dict) for p in products) else None


def approved_card(db, job, version):
    """(approved product.add args, approved photo sha, version photo sha) or a label string when it cannot be found."""
    ver = db.execute("SELECT change_id, listing_json, image_sha256 FROM npp_versions WHERE job_id=? AND n=?", (job, version)).fetchone()
    if ver is None:
        return "version-mismatch"
    try:
        name = json.loads(ver["listing_json"]).get("name")
    except (TypeError, ValueError, AttributeError):
        name = None
    draft = db.execute("SELECT ops_json FROM drafts WHERE change_id=?", (ver["change_id"],)).fetchone() if ver["change_id"] else None
    if draft is None:  # the saved approval row appears only once the yes has been typed
        return "not-approved"
    if not name:
        return "approved-card-missing"
    try:
        ops = json.loads(draft["ops_json"])
    except (TypeError, ValueError):
        return "approved-card-missing"
    mine = [o.get("args") for o in ops if isinstance(o, dict) and o.get("op") == "product.add"
            and isinstance(o.get("args"), dict) and o["args"].get("name") == name]
    if len(mine) != 1:
        return "approved-card-missing"
    photo = mine[0].get("photo")
    if not (isinstance(photo, str) and gate.SHA.fullmatch(photo)) or photo != ver["image_sha256"]:
        return "approved-card-missing"
    return mine[0], photo


def served_photo_sha(worktree, record):
    image = record.get("image")
    if not isinstance(image, str) or not image or image.startswith("/") or ".." in Path(image).parts:
        return None
    return gate.sha256_file(Path(worktree) / "storefront-mockup" / image)


def compare(worktree, records, args, photo_sha):
    """Sorted labels for every way the shop differs from the approved card; empty means it serves what was approved."""
    same_name = [r for r in records if r.get("name") == args["name"]]
    if not same_name:
        return ["not-served"]
    out = set()
    ids = [r.get("id") for r in same_name]
    if len(same_name) > 1 or any(sum(1 for r in records if r.get("id") == i) > 1 for i in ids):
        out.add("duplicate-served")
    for record in same_name:
        for key, served_key, label in FIELDS:
            if key in args and record.get(served_key) != args[key]:
                out.add(label)
        if not set(record) <= PUBLIC_KEYS:
            out.add("non-public-field")
        if any(isinstance(v, str) and PRIVATE_RE.search(v) for k, v in record.items() if k != "image"):
            out.add("private-word")
        served = served_photo_sha(worktree, record)
        if served is None:
            out.add("served-photo-unreadable")
        elif served != photo_sha:
            out.add("served-photo-differs")
    for record in records:
        if record.get("name") != args["name"] and served_photo_sha(worktree, record) == photo_sha:
            out.add("photo-on-another-item")
    return sorted(out)


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "demo_served_comparison: invalid arguments\n")


def main(argv=None):
    parser = PrivateParser(prog="demo_served_comparison", description=__doc__.split("\n\n")[0])
    parser.add_argument("--state", type=Path, required=True, help="restored (or live OFF) state dir")
    parser.add_argument("--worktree", type=Path, required=True, help="the shop worktree that is served")
    parser.add_argument("--job", required=True)
    parser.add_argument("--photo", type=Path, required=True, help="the photo file you hold for this listing")
    parser.add_argument("--version", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        held = gate.sha256_file(args.photo)
        if held is None:
            print("MISMATCH photo-unreadable")
            return 1
        if not (isinstance(args.job, str) and gate.JOB.fullmatch(args.job)) or args.version < 1:
            print("MISMATCH no-such-listing" if not gate.JOB.fullmatch(args.job) else "MISMATCH version-mismatch")
            return 1
        with contextlib.closing(gate.open_conversation(args.state)) as db:
            row = db.execute("SELECT photo_sha FROM npp_jobs WHERE job_id=?", (args.job,)).fetchone()
            if row is None:
                print("MISMATCH no-such-listing")
                return 1
            if row["photo_sha"] != held:
                print("MISMATCH photo-mismatch")
                return 1
            approved = approved_card(db, args.job, args.version)
            if isinstance(approved, str):
                print(f"MISMATCH {approved}")
                return 1
            records = served_list(args.worktree)
            if records is None:
                print("MISMATCH catalog-unreadable")
                return 1
            labels = compare(args.worktree, records, *approved)
    except Exception:  # a fixed label, never a traceback that could carry a path or a value
        print("MISMATCH could-not-check")
        return 1
    if labels:
        print("MISMATCH " + ",".join(labels))
        return 1
    print("MATCH undo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
