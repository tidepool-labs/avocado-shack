#!/usr/bin/env python3
"""HASS-DEMO-REHEARSAL-1 (A4): the owner demo script as a reproducible run.

    python3 -B scripts/hass/demo_rehearsal.py [--fixture FILE] [--only ID[,ID...]] [--show]
    python3 -B scripts/hass/demo_rehearsal.py --live --url http://127.0.0.1:8010 --model NAME [--api openai|ollama] [--timeout 60]

The fixture (hass/tests/fixtures/demo/g-demo.jsonl) is reports/hass-demo-clover/02-DEMO-PLAN.md steps 1-16
(steps 9-10 read the recorded Clover till fixture, read-only) as one JSON row per step: what the owner sends, the interpreter reply a correct
model gives for it, and what must be true afterwards. The first row (`world`) names the scratch shop and its clock.

Offline (default; what CI runs): every row goes through the REAL Conversation, the production Editor and op registry,
sitegen and claims, on a throwaway writer worktree and a private state dir (the H02 repo the tests use), with a
FixtureInterpreter that plays the row's recorded reply. No model, no network, no browser, nothing outside a temp dir.

--live (operator only, refuses under CI): the same rows, the same scratch shop, but the interpreter is the GPU model
(`hass.interpreter_local.LocalInterpreter`, the same prompt builder and hints the service uses, loopback URL only). The
recorded replies are ignored. The model writes its own words, so a row's exact diff VALUES are not compared; its files,
key paths, dispositions and Hass's own wording still are. A table prints: step, disposition, seconds, preview
made/checked, PASS/FAIL (a FAIL names the QA-2 / QA-1 row id from the row's `qa2`). The real preview picture is used when
PLAYWRIGHT_MODULE and CHROMIUM_PATH are in the environment; otherwise the preview is recorded, not rendered, and the table
says so. Exit 0 every row PASS (or a named known gap), 1 a FAIL, 2 unreadable input / refused.

What each row can assert (all optional; unknown fields are refused):
  disposition        how Conversation ended the message (a string or a list of allowed ones)
  replies            how many messages Hass sent (a stranger: 0)
  reply_has/lacks    words in Hass's reply, any case; reply_has_any: one of these words
  model_calls        how many times the interpreter was asked (a stranger, status, undo: 0)
  plain              (default true) no technical word, id or operation name in an owner-facing reply
  commit / files / diff    the row ends in a saved change: the files it touched and the exact content diff (offline)
  preview            {proposal: bool, checked: bool, kind: product|event|store|...}
  draft_state        the state of the newest draft afterwards
  tree               `unchanged` (default for a row without `commit`) - nothing in the worktree moved
  restores/residue   (an undo's yes) the tree equals the state saved under `mark LABEL`, except the declared residue
A message before a yes never changes the worktree (write-before-yes); a row that says `known_gap: ID` is reported as
GAP (not FAIL) while it fails and as PASS once it passes (then drop the field).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import sys
import tempfile
import time
import types
from typing import Any, cast
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from hass import conversation, editor as editor_mod, voice  # noqa: E402
from hass.content_model import REPO_ROOT  # noqa: E402
from hass.skills import testkit as tk  # noqa: E402

FIXTURE = ROOT / "hass" / "tests" / "fixtures" / "demo" / "g-demo.jsonl"
OWNER, STRANGER, CHAT, GROUP = "owner@example.invalid", "stranger@example.invalid", "chat-demo-owner", "chat-demo-group"
LIVE_SITE = "demo.example.invalid"  # a hostname the scratch editor never publishes to (a plain Editor has no publisher)
CODES = ("bad-row", "wrong-disposition", "wrong-reply", "wrong-count", "wrong-calls", "write-before-yes", "wrong-files", "wrong-diff",
         "wrong-preview", "wrong-state", "undo-not-identical", "jargon", "wrong-turn", "no-code", "slow")
ROW_KEYS = {"id", "step", "title", "say", "as", "kind", "from_me", "photo", "caption", "minutes", "reply", "expect", "mark", "keep", "restores",
            "residue", "qa2", "known_gap", "note", "mode", "till"}
EXPECT_KEYS = {"disposition", "replies", "reply_has", "reply_lacks", "reply_has_any", "model_calls", "plain", "allow_words", "commit",
               "files", "diff", "diff_paths", "preview", "draft_state", "tree", "max_seconds"}
WORLD_KEYS = {"world", "about", "start", "ttl_seconds", "skills_mode", "photos", "seed", "setup", "never", "seconds", "till"}
SENDERS = {"owner": (OWNER, CHAT), "stranger": (STRANGER, CHAT), "group": (OWNER, GROUP), "stranger-chat": (STRANGER, GROUP)}
WORDS = re.compile(r"\{code(?::([a-z0-9-]+))?\}")


class RehearsalError(ValueError):
    """The fixture or the command line is unusable (exit 2)."""


# -- the fixture ----------------------------------------------------------------------------------------------
def load_fixture(path=FIXTURE):
    """(world, rows). Every problem names the line and the field, never a value."""
    try: text = Path(path).read_text("utf-8")
    except (OSError, UnicodeDecodeError): raise RehearsalError("--fixture: unreadable") from None
    items = []
    for n, line in enumerate(text.split("\n"), 1):  # LF only: a literal U+2028 inside a JSON string is not a row break
        if not line.strip(): continue
        try: items.append((n, json.loads(line)))
        except (ValueError, RecursionError): raise RehearsalError(f"fixture line {n}: not JSON") from None
    if not items or not isinstance(items[0][1], dict) or "world" not in items[0][1]:
        raise RehearsalError("fixture line 1: the first row must be the `world` row")
    world = items[0][1]["world"]
    if not isinstance(world, dict) or set(world) - WORLD_KEYS: raise RehearsalError("fixture line 1: world has an unknown field")
    for key in ("start", "ttl_seconds"):
        if key not in world: raise RehearsalError(f"fixture line 1: world.{key} is required")
    try:
        start = datetime.fromisoformat(world["start"])
        if start.utcoffset() is None:
            raise ValueError  # astimezone() would otherwise assume the host's time zone.
    except (TypeError, ValueError):
        raise RehearsalError("fixture line 1: world.start must be an ISO time with an offset") from None
    if "till" in world and world["till"] is not True: raise RehearsalError("fixture line 1: till must be true")
    rows, seen = [], set()
    for n, row in items[1:]:
        def bad(what): raise RehearsalError(f"fixture line {n}: {what}")
        if not isinstance(row, dict): bad("row must be a JSON object")
        if set(row) - ROW_KEYS: bad("unknown field " + ", ".join(sorted(set(row) - ROW_KEYS)))
        if not (isinstance(row.get("id"), str) and row["id"]) or row["id"] in seen: bad("id must be a distinct non-empty string")
        seen.add(row["id"])
        if type(row.get("step")) is not int: bad("step must be the demo-plan step number")
        if not isinstance(row.get("say"), str) or not row["say"].strip(): bad("say must be the owner's message")
        if "till" in row and (row["till"] is not True or not world.get("till")):
            bad("till must be true" if row["till"] is not True else "till needs world.till")
        if row.get("as", "owner") not in SENDERS: bad("as must be one of " + ", ".join(SENDERS))
        if not isinstance(row.get("expect"), dict) or "disposition" not in row["expect"]: bad("expect.disposition is required")
        if set(row["expect"]) - EXPECT_KEYS: bad("unknown expect field " + ", ".join(sorted(set(row["expect"]) - EXPECT_KEYS)))
        if "reply" in row and not (isinstance(row["reply"], dict) and set(row["reply"]) & {"ops", "question", "unsupported", "skill", "calls"}):
            bad("reply must be a recorded interpreter reply (ops, question, unsupported, skill or calls)")
        expect = row["expect"]
        if expect.get("commit") and not ("files" in expect and ("diff" in expect or "diff_paths" in expect)):
            bad("a row that saves a change must say expect.files and expect.diff")
        if "restores" in row and not any(r.get("mark") == row["restores"] for _, r in items[1:]): bad("restores names no earlier `mark`")
        rows.append(row)
    return world, rows


# -- the scratch shop -----------------------------------------------------------------------------------------
class PhotoSource:
    """The Conversation's photo source: a row's `photo` file, by the message id."""

    def __init__(self): self.files = {}

    def fetch(self, provider_id, count): return [self.files[provider_id].read_bytes()] * count


class Replay(conversation.FixtureInterpreter):
    """Plays the current row's recorded reply and counts the calls. No model, no network."""

    def __init__(self):
        super().__init__({})
        self.reply, self.calls, self.texts = None, 0, []
        self.last_error = None

    def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None):
        self.calls += 1
        self.texts.append(text)
        if self.reply is None: return {"unsupported": "Sorry, I can't do that yet."}
        return copy.deepcopy(self.reply)


class Timed:
    """The live interpreter, asked the way the service asks it: rebuilt from the shop's content whenever that changed (the
    prompt lists the products, so a product added in step 3 is known by step 5). Counts its calls and keeps their seconds."""

    def __init__(self, build, rev, content_dir):
        self.build, self.rev, self.content_dir = build, rev, content_dir
        self.inner, self.at, self.calls, self.seconds = None, None, 0, 0.0

    def interpret(self, *args, **kwargs):
        head = self.rev()
        if self.inner is None or self.at != head: self.inner, self.at = self.build(self.content_dir()), head
        self.calls += 1
        start = time.monotonic()
        try: return self.inner.interpret(*args, **kwargs)
        finally: self.seconds += time.monotonic() - start

    def __getattr__(self, name):  # last_error and the like, read by the Conversation after a call
        if name in ("inner", "build", "rev", "content_dir", "at", "calls", "seconds"): raise AttributeError(name)
        return getattr(self.inner, name)


class Shop:
    """A throwaway writer worktree + private state + Conversation (production Editor and registry). One clock drives
    everything; each owner message moves it on by its row's minutes. Always close()."""

    def __init__(self, world, live=None, real_preview=False):
        self.world, self.live = world, live
        self.now = datetime.fromisoformat(world["start"]).astimezone(timezone.utc)
        self._clock = lambda: self.now
        self.n, self.photos, self.media_root, self.till_seeded = 0, PhotoSource(), None, False
        from hass.fixture_chat import FixtureAdapter
        from hass.tests.test_editor import WriterRepo
        self.out = FixtureAdapter()
        self.repo = WriterRepo()
        try: self._open(live, real_preview)
        except BaseException:
            self.repo.cleanup()
            raise

    def _open(self, live, real_preview):
        world = self.world
        settings = {"ownerSenders": [OWNER], "ownerChat": CHAT, "approvalTtlSeconds": world["ttl_seconds"],
                    "liveSite": LIVE_SITE, "approvalNeedsCode": True, "skills": {"mode": world.get("skills_mode", "ops-only")}}
        if world.get("photos"):
            self.media_root = tempfile.mkdtemp(prefix="demo-media-")
            settings["mediaRoot"] = self.media_root
            tk.Scratch._real_assets(cast(Any, types.SimpleNamespace(repo=self.repo)))  # a listing image must be a regular file
        cfg = json.loads((self.repo.state / "config.json").read_text("utf-8"))
        editor_mod._write_json(self.repo.state / "config.json", {**cfg, "settings": settings})
        self.wt = self.repo.wt
        if world.get("seed"): self._seed(world["seed"])
        self.editor = tk._clocked_editor(self)(str(self.repo.state))
        if world.get("setup"): self._setup(world["setup"])
        if real_preview:
            from hass.preview import Previewer
            self.previewer, self.preview_kind = Previewer(self.wt), "real"
        else:
            self.previewer, self.preview_kind = tk.RecordingPreviewer(), "recorded"
        self.interp = Timed(live, self.head, lambda: self.wt / "hass" / "content") if live is not None else Replay()
        self.conv = conversation.Conversation(str(self.repo.state), self.editor, self.interp, self._clock, self.previewer,
                                              photos=self.photos if world.get("photos") else None)
        self.Inbound = conversation.Inbound

    def _seed(self, seed):
        with tk._clock_scope(self._clock): tk.Scratch._seed(cast(Any, types.SimpleNamespace(wt=self.wt, _clock=self._clock)), seed)

    def _setup(self, ops):
        out = self.editor.prepare(ops)
        if out.get("result") != "ok": raise RehearsalError("world.setup ops were not accepted")
        if self.editor.apply(out["draft"]["change_id"], out["draft"]["draft_hash"]).get("result") != "applied":
            raise RehearsalError("world.setup ops were not applied")

    # -- reading the world
    def head(self): return tk._git(self.wt, "rev-parse", "HEAD").strip()

    def dirty(self): return tk._git(self.wt, "status", "--porcelain").strip()

    def drafts(self): return [dict(r) for r in self.conv.db.execute("SELECT * FROM drafts ORDER BY row_id")]

    def newest_code(self):
        rows = [d for d in self.drafts() if d["state"] in ("proposed", "needs-details")] or self.drafts()
        return rows[-1]["code"] if rows else None

    @property
    def calls(self): return self.interp.calls

    def say(self, row, text, photo=None):
        """Send one owner message; (disposition, reply texts, attachments, seconds)."""
        sender, chat = SENDERS[row.get("as", "owner")]
        self.n += 1
        self.now += timedelta(minutes=row.get("minutes", 1))
        pid = f"demo-{self.n}"
        if photo is not None: self.photos.files[pid] = photo
        msg = self.Inbound(pid, chat, sender, text, row.get("from_me", False), row.get("kind", "new"), self.now.isoformat(),
                           attachments=1 if photo is not None else 0)
        before = len(self.out.sent)
        if row.get("till"): self._attach_till()
        site = self.conv.settings.pop("liveSite", None) if row.get("mode") == "private" else None  # as the host does in private mode
        start = time.monotonic()
        try:
            with tk._clock_scope(self._clock): disposition = self.conv.handle(msg)
        finally:
            if site is not None: self.conv.settings["liveSite"] = site
            self.conv.till = None  # the desk is only ever there for a `till` row
        seconds = time.monotonic() - start
        self.conv.flush(self.out)
        sent = self.out.sent[before:]
        return disposition, [voice.plain(r["text"]) for r in sent], [a for r in sent for a in r["attachments"]], seconds

    def _attach_till(self):
        """Fill the private till cache once from main's recorded Clover fixture (no network, no token), then give the Conversation a read-only desk."""
        from hass.clover import chat as till_chat
        from hass.tests.test_clover_chat import BLOCK, seed
        if not self.till_seeded: seed(Path(self.repo.state), now=self.now); self.till_seeded = True
        self.conv.till = till_chat.TillDesk(str(self.repo.state), BLOCK)

    def close(self):
        try: self.conv.db.close()
        finally:
            self.repo.cleanup()
            if self.media_root: shutil.rmtree(self.media_root, ignore_errors=True)


# -- running a row --------------------------------------------------------------------------------------------
class Result:
    def __init__(self, row):
        self.row, self.problems, self.disposition, self.seconds = row, [], "", 0.0
        self.made: bool | None = None  # a proposal picture came with the reply
        self.checked: bool | None = None  # after a saved change: the result picture was made and checked
        self.replies, self.gap, self.files, self.diff = [], False, [], []

    def fail(self, code, detail):
        assert code in CODES, code
        self.problems.append((code, " ".join(str(detail).split())[:400]))

    @property
    def ok(self): return not self.problems

    @property
    def status(self):
        if self.ok: return "PASS"
        return "GAP" if self.gap else "FAIL"


def _words_in(text, words): return [w for w in words if w.lower() in text.lower()]


def _subst(text, shop, kept, newest=None):
    """`{code}` is the newest waiting draft's code (as it was before the message), `{code:name}` one kept by an earlier row."""
    def one(m):
        if m.group(1) is None: return (newest if newest is not None else shop.newest_code()) or "none"
        return kept.get(m.group(1), "none")
    return WORDS.sub(one, text)


def _paths(entries): return sorted((e["file"], e["path"]) for e in entries)


def run_row(shop, row, kept, marks, live, world=None):
    res = Result(row)
    expect = row["expect"]
    text, used = _subst(row["say"], shop, kept), shop.newest_code()
    photo = None
    if row.get("photo"):  # a photo message: `say` is only its label; the text that travels is the caption (often none)
        photo = REPO_ROOT / row["photo"]
        if not photo.is_file(): res.fail("bad-row", "photo file is missing"); return res
        text = _subst(row.get("caption", "\ufffc"), shop, kept)
    if not live:  # the recorded reply may name the waiting draft it revises: {code}
        shop.interp.reply = json.loads(_subst(json.dumps(row["reply"]), shop, kept, used)) if "reply" in row else None
    base_head, calls0 = shop.head(), shop.calls
    asked, drafts0 = len(getattr(shop.previewer, "requests", [])) if shop.preview_kind == "recorded" else None, len(shop.drafts())
    try: disposition, replies, attachments, seconds = shop.say(row, text, photo)
    except voice.VoiceError as exc:  # strict voice mode: a reply that breaks the voice rules refuses to send
        res.fail("jargon", f"reply breaks the voice rules: {str(exc)[:160]}"); return res
    except Exception as exc:  # noqa: BLE001 - a crash is a row result
        res.fail("wrong-turn", f"{type(exc).__name__}: {str(exc)[:200]}"); return res
    res.disposition, res.seconds, res.replies = disposition, seconds, replies
    joined = "\n".join(replies)
    expect = {**expect, **{k: [_subst(w, shop, kept) for w in expect[k]] for k in ("reply_has", "reply_lacks", "reply_has_any") if k in expect}}
    want = expect["disposition"] if isinstance(expect["disposition"], list) else [expect["disposition"]]
    if want != ["*"] and disposition not in want:  # "*": a known-gap row whose fixed behaviour does not exist yet
        res.fail("wrong-disposition", f"ended as {disposition!r}, wanted {want}")
    if "replies" in expect and len(replies) != expect["replies"]: res.fail("wrong-count", f"{len(replies)} replies, wanted {expect['replies']}")
    if missing := [w for w in expect.get("reply_has", []) if w.lower() not in joined.lower()]: res.fail("wrong-reply", f"missing {missing}")
    if found := _words_in(joined, expect.get("reply_lacks", [])): res.fail("wrong-reply", f"must not say {found}")
    if expect.get("reply_has_any") and not _words_in(joined, expect["reply_has_any"]): res.fail("wrong-reply", f"none of {expect['reply_has_any']}")
    if found := _words_in(joined, (world or {}).get("never", [])): res.fail("wrong-reply", f"a word Hass never says: {found}")
    limit = expect.get("max_seconds") or ((world or {}).get("seconds") or {}).get("model" if shop.calls > calls0 else "command")
    if limit and seconds > limit: res.fail("slow", f"{seconds:.1f}s, the limit for this message is {limit}s")
    if "model_calls" in expect and shop.calls - calls0 != expect["model_calls"]:
        res.fail("wrong-calls", f"the interpreter was asked {shop.calls - calls0} times, wanted {expect['model_calls']}")
    if expect.get("plain", True) and (jargon := tk.plain_words_problems(joined, expect.get("allow_words", ()))):
        res.fail("jargon", f"technical words in the reply: {sorted(set(jargon))[:6]}")
    drafts = shop.drafts()
    said = set(re.findall(r"[0-9a-f]{4,12}", text))  # the draft the message named, else the newest one
    newest = next((d for d in reversed(drafts) if d["code"] in said), drafts[-1] if drafts else None)
    res.made = bool(attachments)
    if "draft_state" in expect and (newest["state"] if newest else None) != expect["draft_state"]:
        res.fail("wrong-state", f"newest draft is {newest['state'] if newest else None!r}, wanted {expect['draft_state']!r}")
    if expect.get("commit"):
        files, diff = tk.tree_diff(shop.wt, base_head)
        res.files, res.diff = files, diff
        if files != sorted(expect["files"]): res.fail("wrong-files", f"touched {files}, wanted {sorted(expect['files'])}")
        if "diff" in expect and not live:
            want_diff = sorted(expect["diff"], key=lambda e: (e["file"], e["path"]))
            if json.loads(json.dumps(diff, sort_keys=True)) != json.loads(json.dumps(want_diff, sort_keys=True)):
                res.fail("wrong-diff", f"changed {json.dumps(diff, sort_keys=True)[:300]}")
        else:
            paths = _paths(expect.get("diff_paths") or expect["diff"])
            if _paths(diff) != paths: res.fail("wrong-diff", f"changed key paths {_paths(diff)}, wanted {paths}")
        res.checked = bool(newest and newest["state"] == "verified" and newest["checked_at"])
    elif "tree" not in expect or expect["tree"] == "unchanged":
        if shop.head() != base_head or shop.dirty():
            res.fail("write-before-yes", "the worktree changed: " + (tk._git(shop.wt, "diff", "--name-only", base_head).strip().replace("\n", ", ") or shop.dirty())[:200])
    pv = expect.get("preview")
    if pv is not None:
        if "proposal" in pv and pv["proposal"] != res.made: res.fail("wrong-preview", f"proposal picture made={res.made}, wanted {pv['proposal']}")
        if "checked" in pv and pv["checked"] != bool(res.checked): res.fail("wrong-preview", f"result checked={bool(res.checked)}, wanted {pv['checked']}")
        if "kind" in pv and shop.preview_kind == "recorded":
            kinds = [r.get("kind") for r in shop.previewer.requests[asked:]]
            if pv["kind"] not in kinds: res.fail("wrong-preview", f"the preview asked for {kinds}, wanted {pv['kind']!r}")
    if "mark" in row: marks[row["mark"]] = shop.head()
    if "keep" in row:  # the code this row used, or (a row without one) the code it just proposed
        if not (code := used if "{code}" in row["say"] else shop.newest_code()): res.fail("no-code", "no draft to keep a code of")
        else: kept[row["keep"]] = code
    if "restores" in row: _undo_identical(shop, row, marks[row["restores"]], res)
    res.gap = bool(row.get("known_gap"))
    return res


def _undo_identical(shop, row, label_head, res):
    """After an undo's yes: the worktree is clean, the content equals the state saved under `mark` except the row's declared
    residue, every file that is not content or generated is as it was, and every site file equals a fresh render of the
    restored content (the editor re-sorts JSON keys on every write, so site files are judged against that render, not the
    marked state's bytes). The same judgement the skill test kit makes after an undo."""
    declared = sorted((r["file"], r["path"]) for r in row.get("residue", []))
    files, diff = tk.tree_diff(shop.wt, label_head)
    left = sorted(_paths(diff) + [(f, "(file)") for f in files if f.startswith(tk.ASSET_DIR)])  # a picture file stays, unused
    if hard := tk._undo_problems(shop, files, [{"file": f, "path": p} for f, p in left]): res.fail("undo-not-identical", "; ".join(hard))
    elif left != declared: res.fail("undo-not-identical", f"undo left {left} but the row declares residue {declared}")


def run(world, rows, live=None, only=None, real_preview=False, show=False, out=print):
    """Run the rows in order on one scratch shop; the list of Results. Later rows depend on earlier ones (codes, drafts), so
    `only` runs the named rows after silently running their predecessors."""
    shop = Shop(world, live, real_preview)
    results, kept, marks = [], {}, {}
    try:
        last = max((i for i, r in enumerate(rows) if only is None or r["id"] in only), default=-1)
        for row in rows[:last + 1]:  # rows after the last one asked for never matter to it
            res = run_row(shop, row, kept, marks, live is not None, world)
            if only is None or row["id"] in only: results.append(res)
            if show and (only is None or row["id"] in only):
                out(f"--- {row['id']} ({res.status}): {row['say']!r} -> {res.disposition} in {res.seconds:.1f}s")
                for r in res.replies: out("    | " + r.replace("\n", "\n    | "))
                for code, detail in res.problems: out(f"    ! [{code}] {detail}")
                if res.files: out("    files: " + json.dumps(res.files)), out("    diff: " + json.dumps(res.diff, sort_keys=True, ensure_ascii=False))
    finally:
        shop.close()
    return results, shop.preview_kind


def table(results, preview_kind, live):
    head = ["step", "row", "disposition", "seconds", "preview made/checked", "result"]
    lines = []
    for r in results:
        pv = "-" if r.made is None and r.checked is None else f"{'yes' if r.made else 'no'}/{'yes' if r.checked else 'no' if r.checked is not None else '-'}"
        why = ""
        if not r.ok:
            tag = r.row.get("qa2") or r.row.get("known_gap") or "no QA-2 row"
            why = f" ({tag}): " + "; ".join(f"[{c}] {d}" for c, d in r.problems)
        lines.append([str(r.row["step"]), r.row["id"], r.disposition or "-", f"{r.seconds:.1f}", pv, r.status + why])
    widths = [max(len(head[i]), *(len(line[i]) for line in lines)) for i in range(len(head) - 1)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths) + "  {}"
    out = [fmt.format(*head), fmt.format(*("-" * w for w in widths), "-" * 6)] + [fmt.format(*line) for line in lines]
    counts = {s: sum(1 for r in results if r.status == s) for s in ("PASS", "GAP", "FAIL")}
    out.append(f"{len(results)} rows: {counts['PASS']} PASS, {counts['GAP']} known gap, {counts['FAIL']} FAIL; "
               f"mode {'LIVE (GPU interpreter)' if live else 'offline (recorded replies)'}; preview {preview_kind}; "
               f"interpreter seconds are {'wall time per owner message' if live else 'not meaningful offline'}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixture", default=str(FIXTURE))
    ap.add_argument("--only", help="comma-separated row ids to report (earlier rows still run)")
    ap.add_argument("--show", action="store_true", help="print each owner message, Hass's replies and the problems")
    ap.add_argument("--live", action="store_true", help="operator only: ask the real interpreter (refuses under CI)")
    ap.add_argument("--url"), ap.add_argument("--model")
    ap.add_argument("--api", choices=("openai", "ollama"), default="openai")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--skills-mode", choices=("ops-only", "both", "skills-first"), help="live: the Conversation's skills mode (default: the fixture's)")
    args = ap.parse_args(argv)
    try:
        if args.live:
            if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"): raise RehearsalError("--live is for the operator; it refuses to run under CI")
            if not (args.url and args.model): raise RehearsalError("--live needs --url (loopback) and --model")
        world, rows = load_fixture(args.fixture)
        if args.skills_mode: world = {**world, "skills_mode": args.skills_mode}
        only = {i for i in args.only.split(",") if i} if args.only else None
        if only and only - {r["id"] for r in rows}: raise RehearsalError("--only: unknown row id")
        live = _live_interpreter(args, world) if args.live else None
    except RehearsalError as exc:
        print(f"demo_rehearsal: {exc}", file=sys.stderr)
        return 2
    real = bool(args.live and os.environ.get("PLAYWRIGHT_MODULE") and os.environ.get("CHROMIUM_PATH"))
    results, preview_kind = run(world, rows, live, only, real, args.show)
    print(table(results, preview_kind, args.live))
    return 0 if all(r.status != "FAIL" for r in results) else 1


def _live_interpreter(args, world):
    """build(content_dir): the service's own interpreter (the same prompt builder, the same hints) over the scratch shop's content."""
    from hass import interpreter_prompt, nl_prep
    from hass.content_model import load_content
    from hass.interpreter_local import LocalInterpreter, check_url
    from hass.ops import load_registry
    try: check_url(args.url)  # loopback http only, the same rule the service applies
    except ValueError as exc: raise RehearsalError(f"--url: {exc}") from None

    def build(content_dir):
        content = load_content(content_dir)
        return LocalInterpreter(args.url, args.model, interpreter_prompt.build(load_registry(), content), timeout=args.timeout,
                                hinter=nl_prep.make_hinter(content), api=args.api)
    return build


if __name__ == "__main__":
    sys.exit(main())
