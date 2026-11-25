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


class Refused(Exception):
    """A fixed diagnostic label, never an input value."""


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "restored_chat_view: invalid arguments\n")


def rows(state):
    try:
        with contextlib.closing(transcript.read(state)) as db:
            db.row_factory = sqlite3.Row
            out = []
            for row in db.execute("SELECT * FROM events ORDER BY rowid"):
                doc = dict(row)
                doc["attachments"] = json.loads(doc["attachments"])
                if (type(doc["id"]) is not int or not isinstance(doc["attachments"], list)
                        or not all(isinstance(s, str) and SHA.fullmatch(s) for s in doc["attachments"])):
                    raise Refused("bad-event")
                out.append(doc)
            return out
    except (OSError, ValueError, TypeError, sqlite3.Error):
        raise Refused("transcript-unsafe-or-unreadable") from None


def media_index(media):
    """{sha: restored file}. Any link, non-regular entry or mis-named/mis-hashed file is refused or counted."""
    problems, found = {"link": 0, "bad-name": 0, "bad-bytes": 0}, {}
    if media is None:
        return found, problems
    top = Path(media)
    if top.is_symlink() or not top.is_dir():
        raise Refused("media-unsafe")
    if stat.S_IMODE(top.lstat().st_mode) & 0o077:
        raise Refused("media-not-private")
    for here, dirs, names in os.walk(top, followlinks=False):
        for name in dirs + names:
            entry = Path(here, name)
            mode = entry.lstat().st_mode
            if stat.S_ISLNK(mode):
                problems["link"] += 1
            elif stat.S_ISREG(mode) or stat.S_ISDIR(mode):
                if stat.S_ISREG(mode):
                    rel = entry.relative_to(top).as_posix()
                    if SIDECAR.fullmatch(rel) or re.fullmatch(r"npp/[0-9a-f]{4,12}/receipt\.json", rel):
                        continue
                    named = CARD.fullmatch(rel) or ORIGINAL.fullmatch(rel)
                    if not named:
                        problems["bad-name"] += 1
                        continue
                    sha = named.group(1) if CARD.fullmatch(rel) else named.group(1) + named.group(2)
                    if mode_size(entry) > MAX_BYTES or hashlib.sha256(entry.read_bytes()).hexdigest() != sha:
                        problems["bad-bytes"] += 1
                        continue
                    found.setdefault(sha, entry)
            else:
                problems["link"] += 1  # a device, socket or fifo is as unwelcome as a link
    return found, problems


def mode_size(path):
    return path.lstat().st_size


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


def page(events, found, out, force, source):
    spec = importlib.util.spec_from_file_location("npp_chat_page", Path(__file__).with_name("npp_chat_page.py"))
    if spec is None or spec.loader is None:
        raise Refused("page-unavailable")
    chat_page = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chat_page)
    staged = Path(tempfile.mkdtemp(prefix=".restored-chat-"))
    try:
        os.chmod(staged, 0o700)
        for sha, restored in found.items():  # flat, sha-named copies: the page code refuses links and checks the digest
            target = staged / sha
            shutil.copyfile(restored, target)
            os.chmod(target, 0o600)
        destination = chat_page.output_path(Path(out), Path(source), staged, force)
        html, _missing, _ambiguous = chat_page.render(events, staged)
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
        if args.media is None and named:
            failures.append("media-not-given")
        if args.page is not None and not failures:
            out_dir = args.page.parent.resolve()
            for root in (args.state, args.media):  # the page holds content: never inside what it was read from
                if root is not None and os.path.commonpath((out_dir, root.resolve())) == os.fspath(root.resolve()):
                    raise Refused("page-inside-input")
            page(events, found, args.page, args.force, args.state / transcript.NAME)
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
    except (OSError, RuntimeError, ValueError):
        print("FAIL restored_chat_view could-not-check")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
