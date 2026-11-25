#!/usr/bin/env python3
"""Check a RESTORED Hass conversation for local ops review, without echoing it.

Reads a restored state dir's private transcript (hass.transcript.read: owned 0700 dir, 0600 regular file, no links)
and, optionally, the restored media dir (originals/<aa>/<sha>.<jpg|png>, npp/<job>/card-<sha>.png). It proves that

  * the events come back in id order (and, with --reference, in exactly the order and shape of the pre-backup export),
  * every picture a message names is a restored regular file whose bytes hash to that name,
  * no restored entry is a link, so nothing can point outside the restored roots.

Stdout/stderr carry only counts and fixed labels: never names, message text, ids, paths or picture bytes. An ops
viewer page, if wanted, is written with --page to a private 0600 file outside any Git worktree by reusing
scripts/hass/npp_chat_page.py; that page is the only output that holds conversation content, and it stays local.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from hass import transcript  # noqa: E402

SHA = re.compile(r"[0-9a-f]{64}")
ORIGINAL = re.compile(r"originals/([0-9a-f]{2})/\1([0-9a-f]{62})\.(?:jpg|png)")
CARD = re.compile(r"npp/[0-9a-f]{4,12}/card-([0-9a-f]{64})\.png")
SIDECAR = re.compile(r"originals/[0-9a-f]{2}/[0-9a-f]{64}\.json")
MAX_BYTES = 20 * 1024 * 1024  # hass/media.py MAX_BYTES
PNG_MAGIC, JPEG_MAGIC = b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"


class Refused(Exception):
    """A fixed diagnostic label, never an input value."""


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "restored_chat_view: invalid arguments\n")


def plain_path(path):
    """True when no component of the absolute path is a link (the path equals its own real path)."""
    absolute = os.path.abspath(path)
    return os.path.realpath(absolute) == absolute


def read_nofollow(top, rel):
    """Bytes of the regular file `rel` under `top`, opened component by component without following any link."""
    parts = rel.split("/")
    fd = os.open(top, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    finally:
        os.close(fd)
    with os.fdopen(leaf, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise OSError
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise OSError
    return data


def columns(db):
    return [(name, kind.upper(), bool(notnull), bool(pk))
            for _cid, name, kind, notnull, _default, pk in db.execute("PRAGMA table_info(events)")]


def expected_columns():
    """The column list hass.transcript itself creates, read from its own SCHEMA."""
    with contextlib.closing(sqlite3.connect(":memory:")) as db:
        db.executescript(transcript.SCHEMA)
        return columns(db)


def rows(state):
    try:
        if not plain_path(state):
            raise Refused("state-path-has-a-link")
        with contextlib.closing(transcript.read(state)) as db:
            db.row_factory = sqlite3.Row
            if columns(db) != expected_columns():  # the shape is checked on its own, so an empty or partial table fails
                raise Refused("transcript-unsafe-or-unreadable")
            out = []
            for row in db.execute("SELECT * FROM events ORDER BY rowid"):
                doc = dict(row)
                doc["attachments"] = json.loads(doc["attachments"])
                if (type(doc["id"]) is not int or not isinstance(doc["attachments"], list)
                        or not all(isinstance(s, str) and SHA.fullmatch(s) for s in doc["attachments"])):
                    raise Refused("bad-event")
                out.append(doc)
            return out
    except Refused:
        raise
    except Exception:  # a store of the wrong shape (missing table/column, bad JSON) is a label, never a traceback
        raise Refused("transcript-unsafe-or-unreadable") from None


def media_index(media):
    """({sha: relative path}, problem counts). A link, odd entry, unreadable folder or bad file is a failure."""
    problems, found = {"link": 0, "bad-name": 0, "bad-bytes": 0}, {}
    if media is None:
        return found, problems
    top = Path(media)
    if not plain_path(top) or not top.is_dir():
        raise Refused("media-unsafe")
    if stat.S_IMODE(top.lstat().st_mode) & 0o077:
        raise Refused("media-not-private")

    def unreadable(_error):
        raise Refused("media-unreadable")

    for here, dirs, names in os.walk(top, followlinks=False, onerror=unreadable):
        for name in dirs + names:
            entry = Path(here, name)
            mode = entry.lstat().st_mode
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode):
                problems["link"] += 1  # a link, device, socket or fifo; never followed
                continue
            rel = entry.relative_to(top).as_posix()
            if SIDECAR.fullmatch(rel) or re.fullmatch(r"npp/[0-9a-f]{4,12}/receipt\.json", rel):
                continue
            card, original = CARD.fullmatch(rel), ORIGINAL.fullmatch(rel)
            if not (card or original):
                problems["bad-name"] += 1
                continue
            sha = card.group(1) if card else original.group(1) + original.group(2)
            try:
                data = read_nofollow(top, rel)
            except OSError:
                problems["link"] += 1  # swapped for a link or unreadable between the listing and the open
                continue
            # The bytes must be the picture the name says, in the kind the extension says.
            magic = PNG_MAGIC if rel.endswith(".png") else JPEG_MAGIC
            if hashlib.sha256(data).hexdigest() != sha or not data.startswith(magic):
                problems["bad-bytes"] += 1
                continue
            found.setdefault(sha, (top, rel))
    return found, problems


def shots_index(state, found, problems):
    """Add the state dir's own editor pictures (screenshots/*.png, screenshots/<sha>.jpg) to `found`, keyed by the sha of
    their bytes: the transcript names an editor preview by the hash of its bytes, but the file name is the change id.
    A link or other non-regular entry is a failure; the media tree's pictures win when both hold the same bytes."""
    top = Path(state) / "screenshots"
    if not os.path.lexists(top):
        return
    if top.is_symlink() or not top.is_dir():
        problems["link"] += 1
        return
    for entry in sorted(os.scandir(top), key=lambda e: e.name):
        mode = os.lstat(entry.path).st_mode
        if not stat.S_ISREG(mode):
            problems["link"] += 1
            continue
        if not entry.name.endswith((".png", ".jpg")):
            continue
        rel = "screenshots/" + entry.name
        try:
            data = read_nofollow(state, rel)
        except OSError:
            problems["link"] += 1
            continue
        magic = PNG_MAGIC if rel.endswith(".png") else JPEG_MAGIC
        if not data.startswith(magic):
            problems["bad-bytes"] += 1
            continue
        found.setdefault(hashlib.sha256(data).hexdigest(), (Path(state), rel))


def compare(events, reference):
    """Index of the first event that differs from the pre-backup export, or None when order and shape match."""
    ref = []
    try:
        for line in Path(reference).read_text(encoding="utf-8").splitlines():
            doc = json.loads(line)
            if not isinstance(doc, dict):
                raise ValueError
            ref.append(doc)
    except (OSError, ValueError):
        raise Refused("reference-unreadable") from None
    for index, (mine, theirs) in enumerate(zip(events, ref)):
        if mine != theirs:
            return index
    return None if len(events) == len(ref) else min(len(events), len(ref))


def page(events, found, media, out, force, source):
    spec = importlib.util.spec_from_file_location("npp_chat_page", Path(__file__).with_name("npp_chat_page.py"))
    if spec is None or spec.loader is None:
        raise Refused("page-unavailable")
    chat_page = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chat_page)
    staged = Path(tempfile.mkdtemp(prefix=".restored-chat-"))
    try:
        os.chmod(staged, 0o700)
        for sha, (base, rel) in found.items():  # flat, sha-named copies read without following links; the page re-checks them
            target = staged / sha
            target.write_bytes(read_nofollow(base, rel))
            os.chmod(target, 0o600)
        destination = chat_page.output_path(Path(out), Path(source), staged, force)
        html, missing, _ambiguous = chat_page.render(events, staged)
        if missing:  # a picture the page cannot show must not leave a page that looks complete
            raise Refused("page-picture-unrenderable")
        chat_page.write_page(destination, html, force)
    except chat_page.PageError as error:
        raise Refused("page-" + ("inside-git" if "git" in str(error) else "refused")) from None
    finally:
        shutil.rmtree(staged, ignore_errors=True)


def main(argv=None):
    parser = PrivateParser(prog="restored_chat_view", description=__doc__)
    parser.add_argument("--state", type=Path, required=True, help="restored state dir (holds transcript.sqlite3)")
    parser.add_argument("--media", type=Path, help="restored media dir (originals/, npp/)")
    parser.add_argument("--reference", type=Path, help="JSONL from `hass.transcript export`, taken before the backup")
    parser.add_argument("--page", type=Path, help="also write the local ops page (holds conversation content) here")
    parser.add_argument("--force", action="store_true", help="replace an existing --page file")
    args = parser.parse_args(argv)
    try:
        if args.state.is_symlink():
            raise Refused("state-is-a-link")
        events = rows(args.state)
        found, problems = media_index(args.media)
        shots_index(args.state, found, problems)
        failures = [label for label, count in problems.items() if count]
        ids = [event["id"] for event in events]
        if ids != sorted(set(ids)):
            failures.append("order")
        first = None
        if args.reference is not None:
            first = compare(events, args.reference)
            if first is not None:
                failures.append(f"reference-differs-at-event-{first}")
        named = {sha for event in events for sha in event["attachments"]}
        missing = sorted(named - found.keys())
        if missing and args.media is not None:
            failures.append(f"attachments-missing-{len(missing)}")
        if args.media is None and missing:
            failures.append("media-not-given")
        if args.page is not None and not failures:
            out_dir = args.page.parent.resolve()
            for root in (args.state, args.media):  # the page holds content: never inside what it was read from
                if root is not None and os.path.commonpath((out_dir, root.resolve())) == os.fspath(root.resolve()):
                    raise Refused("page-inside-input")
            page(events, found, args.media, args.page, args.force, args.state / transcript.NAME)
        counts = (f"events={len(events)} attachments={len(named)} linked={len(named & found.keys())}"
                  f" reference={'none' if args.reference is None else 'matched' if first is None else 'differs'}")
        if failures:
            print("FAIL restored_chat_view " + " ".join(failures) + " " + counts)
            return 1
        print("PASS restored_chat_view " + counts)
        return 0
    except Refused as why:
        print(f"FAIL restored_chat_view {why}")
        return 1
    except Exception:  # last resort: a fixed label, never a traceback that could carry a path or a value
        print("FAIL restored_chat_view could-not-check")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
