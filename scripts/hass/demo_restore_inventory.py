#!/usr/bin/env python3
"""L18: the restore inventory the OFF demo owner reads BEFORE restoring a state backup (and to compare two of them).

    python3 -B scripts/hass/demo_restore_inventory.py BACKUP
    python3 -B scripts/hass/demo_restore_inventory.py BACKUP --against OTHER_BACKUP

For each listing (logical item, by its job code) it joins the three things a restore must bring back together:

  history  the saved chat: incoming photo messages and outgoing card messages that belong to that listing
  media    the photo original and the delivered card picture the listing's newest version names
  served   the shop as it was served: the catalog and photo inside the backup's content bundle

and classifies it: `served` (the approved name is in the served catalog and its photo is the approved photo), `served-photo-differs`,
`waiting-for-yes`, `in-progress`, `ended` or `incomplete-<first missing piece>` (photo-original-missing, card-file-missing,
card-not-delivered, photo-not-in-history, card-not-in-history, listing-has-no-name).

A backup that has no served-state input (no content bundle, i.e. history and media only) is REFUSED: restoring it could replay a
yes that the shop no longer shows, or hide that a listing is already served. A backup that does not verify, or whose history or served
state cannot be read, is REFUSED too. With --against it prints what differs per listing between the two backups.

READ-ONLY: both backups are only read (nothing in them, in any state dir, worktree or the live shop is written or touched; the
bundle is unpacked into a private scratch folder that is removed afterwards). Output is fixed words, job codes and counts only: never
a name, text, price, path or byte. Exit 0 (an inventory, or `COMPARE same`), 1 (REFUSED or `COMPARE differs`), 2 unusable arguments.
A rehearsal aid for the attended demo: it does not restore, approve or post anything.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hass import statebackup  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load("demo_pre_yes_gate")
viewer = gate._viewer()
GIT_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
BLOB_MAX = 20 * 1024 * 1024


class Refused(Exception):
    """A fixed label; never carries a value."""


def git(repo, *args, cwd=None):
    done = subprocess.run(["git", f"--git-dir={repo}", "-c", "core.hooksPath=/dev/null", *args], cwd=cwd, env=GIT_ENV,
                          capture_output=True, timeout=60)
    if done.returncode != 0:
        raise Refused("served-state-unreadable")
    return done.stdout


def served_state(backup, commit):
    """({name: [photo sha or None, ...]}, count) of the catalog inside the backup's content bundle at `commit`; scratch is removed."""
    bundle = Path(backup) / statebackup.BUNDLE
    with tempfile.TemporaryDirectory(prefix="restore-inventory-") as tmp:
        repo = Path(tmp) / "r.git"
        subprocess.run(["git", "init", "-q", "--bare", str(repo)], env=GIT_ENV, capture_output=True, timeout=60, check=True)
        git(repo, "bundle", "unbundle", str(bundle))
        raw = git(repo, "cat-file", "blob", f"{commit}:{gate.CATALOG}")
        first = raw.split(b"\n", 1)[0]
        if not first.startswith(gate.CATALOG_HEAD):
            raise Refused("served-state-unreadable")
        try:
            records = json.loads(first[len(gate.CATALOG_HEAD):].rstrip(b";"))
        except ValueError:
            raise Refused("served-state-unreadable") from None
        names = {}
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("name"), str):
                continue
            photo, image = None, record.get("image")
            if isinstance(image, str) and image and not image.startswith("/") and ".." not in Path(image).parts:
                with contextlib.suppress(Refused):
                    blob = git(repo, "cat-file", "blob", f"{commit}:storefront-mockup/{image}")
                    photo = hashlib.sha256(blob).hexdigest() if len(blob) <= BLOB_MAX else None
            names.setdefault(record["name"], []).append(photo)
        return names


def listing_name(raw):
    try:
        return json.loads(raw).get("name")
    except (TypeError, ValueError, AttributeError):
        return None


def classify(job, version, files, events, names):
    """(class, counts dict) for one listing."""
    photo_sha = job["photo_sha"]
    card_sha = version["card_png_sha"] if version else None
    originals = sum(1 for rel in files if re.fullmatch(rf"{statebackup.ORIG}[0-9a-f]{{2}}/{re.escape(photo_sha)}\.(?!json$)\w+", rel))
    card_file = f"{statebackup.NPP}{job['job_id']}/card-{card_sha}.png" in files if card_sha else False
    photos_in = sum(1 for e in events if e["direction"] == "in" and photo_sha in e["attachments"])
    cards_out = sum(1 for e in events if e["direction"] == "out" and card_sha and card_sha in e["attachments"])
    name = listing_name(version["listing_json"]) if version else None
    counts = dict(history=f"{photos_in}/{cards_out}", originals=originals, card=int(card_file), served="no")
    if name and name in names:
        counts["served"] = "yes"
        same = [p for p in names[name] if p == (version["image_sha256"])]
        return ("served" if len(names[name]) == 1 and same else "served-photo-differs"), counts
    if job["closed_at"]:
        return "ended", counts
    if not originals:
        return "incomplete-photo-original-missing", counts
    if version is None or not card_sha or version["state"] != "delivered" or not version["delivered_at"]:
        return ("in-progress" if job["state"] in ("working", "asking", "editing", "retake") else "incomplete-card-not-delivered"), counts
    if not card_file:
        return "incomplete-card-file-missing", counts
    if not photos_in:
        return "incomplete-photo-not-in-history", counts
    if not cards_out:
        return "incomplete-card-not-in-history", counts
    if not name:
        return "incomplete-listing-has-no-name", counts
    return ("waiting-for-yes" if job["state"] == "card_out" else "in-progress"), counts


def inventory(backup):
    """{'commit': sha, 'items': {job: (class, counts)}} or raises Refused(label). Reads only."""
    bdir = Path(backup).absolute()
    if bdir.is_symlink() or not viewer.plain_path(bdir):
        raise Refused("backup-not-intact")
    if statebackup.verify(bdir).get("result") != "ok":
        raise Refused("backup-not-intact")
    doc = statebackup._manifest(bdir)
    files = doc["files"]
    commit = doc.get("contentCommit")
    if not commit or statebackup.BUNDLE not in files:
        raise Refused("no-served-state")
    try:
        events = viewer.rows(bdir)
    except Exception:
        raise Refused("history-unreadable") from None
    names = served_state(bdir, commit)
    items = {}
    try:
        with contextlib.closing(gate.open_conversation(bdir)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='npp_jobs'").fetchone():
                return {"commit": commit, "items": items}
            for job in db.execute("SELECT * FROM npp_jobs ORDER BY rowid").fetchall():
                version = db.execute("SELECT * FROM npp_versions WHERE job_id=? AND n=?", (job["job_id"], job["current_version"])).fetchone()
                items[str(job["job_id"])] = classify(job, version, files, events, names)
    except Refused:
        raise
    except Exception:
        raise Refused("history-unreadable") from None
    return {"commit": commit, "items": items}


def show(inv):
    lines = [f"BACKUP ok items={len(inv['items'])} served-state=present"]
    for job, (kind, c) in sorted(inv["items"].items()):
        lines.append(f"ITEM {job} {kind} history={c['history']} originals={c['originals']} card={c['card']} served={c['served']}")
    return lines


def compare(a, b):
    """Sorted DIFF lines between two inventories; empty means same."""
    out = []
    if a["commit"] != b["commit"]:
        out.append("CONTENT served-state-commit-differs")
    for job in sorted(set(a["items"]) | set(b["items"])):
        if job not in b["items"]:
            out.append(f"DIFF {job} only-in-first")
        elif job not in a["items"]:
            out.append(f"DIFF {job} only-in-second")
        else:
            (ka, ca), (kb, cb) = a["items"][job], b["items"][job]
            labels = [label for label, bad in (("class-differs", ka != kb), ("history-differs", ca["history"] != cb["history"]),
                                               ("media-differs", (ca["originals"], ca["card"]) != (cb["originals"], cb["card"])),
                                               ("served-differs", ca["served"] != cb["served"])) if bad]
            if labels:
                out.append(f"DIFF {job} " + ",".join(labels))
    return out


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "demo_restore_inventory: invalid arguments\n")


def main(argv=None):
    parser = PrivateParser(prog="demo_restore_inventory", description=__doc__.split("\n\n")[0])
    parser.add_argument("backup", type=Path)
    parser.add_argument("--against", type=Path, help="a second backup to compare with")
    args = parser.parse_args(argv)
    try:
        first = inventory(args.backup)
        second = inventory(args.against) if args.against else None
    except Refused as why:
        print(f"REFUSED {why}")
        return 1
    except Exception:  # a fixed label, never a traceback that could carry a path or a value
        print("REFUSED could-not-check")
        return 1
    if second is None:
        print("\n".join(show(first)))
        return 0
    diffs = compare(first, second)
    print("\n".join(["COMPARE differs" if diffs else "COMPARE same", *diffs]))
    return 1 if diffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
