#!/usr/bin/env python3
"""L11: one executable OFF walkthrough for the attending owner: checkout -> photo -> preview -> yes -> served site -> take-down.

    python3 -B scripts/hass/hidden_listing_walkthrough.py --repo CHECKOUT --sha FULL_SHA --remote-url URL \\
        --photo PHOTO_FILE --out RECEIPT_DIR

Rehearsal only (OFF): the listing is made in a throwaway fixture shop with the same chat, listing job, editor and local
writer the real service uses; the "site" is a loopback web server over that throwaway folder. Nothing touches Clover, the
live site, a service or the network beyond 127.0.0.1. It proves the steps work and how long they take; it is NOT a live
listing and not the attended proof on the real hidden TESTITEM.

Steps, in order, stopping at the first FAIL (nothing after a failed step is run):
  checkout   scripts/hass/install_tools_checkout.py (the existing check): the tools checkout is the reviewed commit, clean,
             with the expected origin. A wrong checkout stops here, before anything is made.
  photo      the photo file exists, is a plain file (not a link), is a PNG or JPEG, and is not empty or huge. A missing or
             odd photo stops here, before any preview or yes.
  preview    the owner's photo + `sell $12.34` produce the card and a code. BEFORE the yes is sent, the photo in the approved
             draft must be the very photo supplied (SHA-256), nothing may have been saved, and the site must be unchanged.
  confirm    one coded `yes <code>`: one commit, the public card is what the preview showed (name, descriptor, public price,
             photo description, photo bytes; no cost/qty).
  served     what a visitor is served over loopback (Market page, catalog script, photo) equals the approved card.
  takedown   `undo` changes nothing a visitor sees; one coded `yes` removes the card; the served catalog is byte-identical
             to the pre-publication one.
Each step prints PASS/FAIL with its seconds; the total is printed and recorded. The receipt (RECEIPT_DIR, a private 0700
folder outside the repo) holds step names, seconds, counts and 12-character digest prefixes only: no photo, path, code,
transcript or chat text. Exit 0 all steps PASS, 1 a step FAILED, 2 unusable arguments.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import stat
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NAME = "hidden_listing_walkthrough"
PHOTO_MAX = 8 * 1024 * 1024
MAGIC = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpeg"))


class Args(argparse.ArgumentParser):
    def error(self, message):
        super().error("invalid arguments")  # argparse would echo a mistyped private value


def load_checkout_tool():
    spec = importlib.util.spec_from_file_location("install_tools_checkout", HERE / "install_tools_checkout.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_checkout(args) -> tuple[bool, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            code = load_checkout_tool().main(["--repo", str(args.repo), "--sha", args.sha, "--remote-url", args.remote_url])
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    fails = [line[5:] for line in out.getvalue().splitlines() if line.startswith("FAIL ") and line != "FAIL install_tools_checkout"]
    return code == 0, ", ".join(fails) if code else "reviewed tools checkout verified"


def read_photo(path) -> tuple[bytes | None, str]:
    """(bytes, "") for a usable photo, else (None, reason). The path is never echoed."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None, "photo file is missing"
    except OSError:
        return None, "photo file cannot be opened (a link or no permission)"
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            return None, "photo is not a plain file"
        if info.st_size == 0:
            return None, "photo file is empty"
        if info.st_size > PHOTO_MAX:
            return None, "photo file is too large"
        data = os.read(fd, info.st_size + 1)
    finally:
        os.close(fd)
    if len(data) != info.st_size:
        return None, "photo file changed while it was read"
    if not any(data.startswith(magic) for magic, _kind in MAGIC):
        return None, "photo is not a PNG or JPEG"
    return data, ""


class Steps:
    """Ordered PASS/FAIL rows with seconds. The first FAIL ends the walkthrough."""

    def __init__(self, out):
        self.rows, self.out, self.started = [], out, time.monotonic()
        self.last = self.started

    def add(self, step, ok, detail, **facts):
        now = time.monotonic()
        row = {"step": step, "result": "PASS" if ok else "FAIL", "seconds": round(now - self.last, 3), "detail": detail, **facts}
        self.last = now
        self.rows.append(row)
        print(f"{row['result']} {step} ({row['seconds']}s): {detail}", file=self.out)
        return ok

    @property
    def total(self):
        return round(time.monotonic() - self.started, 3)


def run_fixture(photo: bytes, steps: Steps, delivered: bytes | None = None) -> dict:
    """preview, confirm, served and takedown in a throwaway shop, with the photo the owner supplied. Returns facts.

    `delivered` is a test seam: the bytes the chat actually hands the shop (default: the supplied photo itself)."""
    from hass.tests import test_hidden_listing_served_projection as served_tests
    from hass.tests import test_npp_undo_journey as journey

    wanted = hashlib.sha256(photo).hexdigest()
    facts = {"yes_sent": 0, "commits_before_yes": None}

    class Walk(served_tests.HiddenListingServedProjectionTests):
        def fetch(self, provider_id, count):
            return [photo if delivered is None else delivered][:count]

        def approved_photo_digest(self):
            (_path, digest), = self.engine.show(self.change)["draft"]["assets"].items()
            return digest.removeprefix("sha256:")

        gated = False

        def say(self, text, *, photos=0):
            is_yes = text.startswith("yes ")
            if is_yes and not self.gated:
                self.gated = True
                self.gate()  # a failure raises here, before the first yes is delivered
            result = super().say(text, photos=photos)
            facts["yes_sent"] += is_yes
            return result

        def gate(self):
            """Before the owner's yes: the preview shows the supplied photo and nothing has been saved or published."""
            digest = self.approved_photo_digest()
            self.assertEqual(digest, wanted, "the preview photo is not the supplied photo")
            self.assert_commit_delta(0)
            self.assertEqual((self.repo.head(), self.site()), (self.base_head, self.base_site))
            facts["commits_before_yes"] = self.commits() - self.base_count
            steps.add("preview", True, "the card was made from the supplied photo; nothing is saved or public yet",
                      photo_sha12=digest[:12], draft_price=journey.PRICE)

        def walk(self):
            self.publish()  # preview (gate above), one coded yes, the saved card and its photo bytes
            approved = self.approved_card()
            self.assertEqual(approved["sellingPrice"], journey.PRICE)
            self.assertEqual(approved["photo_sha256"], wanted)
            steps.add("confirm", True, "one coded yes saved one change; the public card is the approved one",
                      commits_after_yes=self.commits() - self.base_count)
            self.assertEqual(served_tests.mismatches(approved, self.served()), [])
            steps.add("served", True, "the loopback site serves the approved name, descriptor, price, photo description and photo",
                      photo_sha12=approved["photo_sha256"][:12])
            self.draft_hide()
            self.assertEqual(served_tests.mismatches(approved, self.served()), [])  # `undo` alone changes nothing a visitor sees
            self.confirm_hide()
            record, _photo, script, problems = self.served()
            self.assertEqual((record, problems), (None, []))
            self.assertEqual(script, self.base_site[0])
            steps.add("takedown", True, "one coded yes removed the card; the served catalog equals the pre-publication one")

    case = Walk("walk")
    result = unittest.TestResult()
    case.run(result)
    problems = result.failures + result.errors
    if problems:
        text = problems[0][1].strip().splitlines()[-1] if problems[0][1].strip() else "unknown"
        done = {row["step"] for row in steps.rows}
        stage = next((s for s in ("preview", "confirm", "served", "takedown") if s not in done), "takedown")
        steps.add(stage, False, text[:300])
    return facts


def write_receipt(out_dir: Path, steps: Steps, ok: bool, photo_sha12) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = out_dir / f"walkthrough-{stamp}.json"
    doc = {"tool": NAME, "result": "PASS" if ok else "FAIL", "total_seconds": steps.total, "photo_sha12": photo_sha12,
           "steps": steps.rows, "service_calls": 0, "network_calls": 0, "local_only": True}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(doc, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return path


def private_out(raw) -> Path | None:
    """The receipt folder: an existing real directory, mode 0700, outside this checkout."""
    path = Path(raw)
    try:
        info = path.lstat()
        real = path.resolve()
    except OSError:
        return None
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
        return None
    if real == ROOT or ROOT in real.parents:
        return None
    return real


def main(argv=None, out=None) -> int:
    out = out or sys.stdout
    parser = Args(prog=NAME, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, required=True, help="the tools checkout to verify")
    parser.add_argument("--sha", required=True, help="reviewed 40-character commit SHA")
    parser.add_argument("--remote-url", required=True, help="expected origin URL")
    parser.add_argument("--photo", required=True, help="a PNG or JPEG file for the fixture listing")
    parser.add_argument("--out", required=True, help="private (0700) receipt folder outside the repo")
    args = parser.parse_args(argv)
    out_dir = private_out(args.out)
    if out_dir is None:
        print("FAIL receipt folder must be an existing 0700 directory outside the repo", file=out)
        return 2
    steps, photo_sha12, ok = Steps(out), None, False
    try:
        passed, detail = check_checkout(args)
        if not steps.add("checkout", passed, detail):
            return 1
        photo, why = read_photo(args.photo)
        if photo is None:
            steps.add("photo", False, why)
            return 1
        photo_sha12 = hashlib.sha256(photo).hexdigest()[:12]
        steps.add("photo", True, "photo file is a usable PNG/JPEG", size_bytes=len(photo), photo_sha12=photo_sha12)
        run_fixture(photo, steps)
        ok = all(row["result"] == "PASS" for row in steps.rows) and [r["step"] for r in steps.rows] == \
            ["checkout", "photo", "preview", "confirm", "served", "takedown"]
        return 0 if ok else 1
    finally:
        receipt = write_receipt(out_dir, steps, ok, photo_sha12)
        print(f"{'PASS' if ok else 'FAIL'} {NAME} total {steps.total}s (receipt {receipt.name}, local only)", file=out)


if __name__ == "__main__":
    sys.exit(main())
