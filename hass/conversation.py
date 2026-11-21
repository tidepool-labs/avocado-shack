"""Hass conversation core (H05): owner messages -> A2 drafts -> bound approval -> one apply.

The interpreter only turns text into typed ops (it never sees approvals or calls the editor); deterministic code
does every write. handle() stores each result (message id, draft state, reply) before any reply is sent; flush()
sends. Approval is bound to sender, chat, change id, draft hash, base revision and expiry. Fixture adapter only.
"""
import contextlib, copy, hashlib, json, os, re, sqlite3, stat, sys, time  # noqa: E401
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import editor as editor_mod, memory as memory_mod, migration_check, preview as preview_mod, sitegen  # noqa: E402
from hass import claims, interpret_check, label_reader, margins, media, morning_report, morning_report as shelf, owner_answers as answers, social_draft  # noqa: E402
from hass.content_model import HOME_IMAGE_RE, MAX_NOTICE, SHELF_LABELS, ContentError, _read_json, _text as checked_text, checked_on, load_and_validate, load_content, notice_days, shop_today, validate  # noqa: E402
from hass.ops import catalog, hikes, load_registry  # noqa: E402
from hass.interpreter_prompt import DESIGN_UNSUPPORTED  # noqa: E402
from hass.social_message import classify_social  # noqa: E402
from hass import audit as audit_mod, corrlog, hike_chat, hike_lookup, live_policy, nl_prep, voice  # noqa: E402
from hass import capabilities, photo_polish, stagelog, transcript  # noqa: E402
from hass.stagelog import short as _short  # noqa: E402
from hass.skills import dispatch as dispatch_mod, intake_simple, item_intake, openreq  # noqa: E402
from hass.clover import approvals as till_approvals  # noqa: E402
from hass import npp as npp_package  # noqa: E402
from hass.npp import job as listing_jobs, reply as npp_reply  # noqa: E402
from hass.npp.receipt import instant as npp_instant  # noqa: E402
# AVB-12: the pack commands (hass/chat/*_pack.py) and the words they share moved to hass/chat/; every moved name is
# imported back here, so hass.conversation.<name> still works for every caller and test.
from hass.chat.shared import (  # noqa: E402,F401
    LOCAL_TZ, q, FIND_TEXT_MAX, ALIAS_NAME_MAX, STATUS_PLAIN, COST_USAGE, CONTROL, NOTHING, CANT_READ, SHELF_ASK,
    _iso, _is_undo)
from hass.chat.commands import (  # noqa: E402,F401
    APPROVE, REJECT, UNDO_PHRASES, CANCEL_PHRASES, KEYWORD_RE, NEAR_RE, COMMAND_RE, HELP_TEXT, help_detail, MEMORY_RE, parse_keyword, COURTESY, parse_phone,
    parse_unknown_code, parse_near, parse_command, _note_key, parse_memory, READ_ONLY, _asked, read_command, read_memory)
from hass.chat.wording import (  # noqa: E402,F401
    PHOTO_PATH_RE, VALUE_CUT, _value, _full, _changes, COLLECTION_WORDS, WHOLE_WORDS, _name, _subject, _summary,
    _when, _shown, UNREADABLE_TIME, EVENT_ORDER, _shown_in, _added, _change_line, _removed, _removal, _record_lines,
    proposal_text)
from hass.chat.core_pack import (  # noqa: E402,F401
    MEMORY_LIST_MAX, HISTORY_MAX, ALIAS_LIST_MAX, COSTS_LIST_MAX, HISTORY_STATES, HISTORY_SEARCH_MAX, HISTORY_TEXT_MAX,
    HISTORY_USAGE, AGAIN_WINDOW_DAYS, AGAIN_USAGE, AGAIN_DRIFT, CorePack)
from hass.chat.site_pack import (  # noqa: E402,F401
    PHOTOS_TO_TAKE_MAX, HIDDEN_MAX, LISTING_DESC_MAX, LISTING_USAGE, LISTING_NONE, LISTING_MANY, FIND_MAX,
    FIND_USAGE, SitePack)
from hass.chat.reports_pack import (  # noqa: E402,F401
    POST_USAGE, HIKE_USAGE, HIKE_REFUSALS, POST_REFUSALS, POST_CANT, _NUM, MARGIN_RE, MARGIN_ID_RE, COST_RE,
    MARGIN_USAGE, ReportsPack)

PRIVATE_PREFIXES = ("alias.", "cost.", "design.")  # AV1222-10: memory keys the interpreter never sees
PAUSED_LINE = "Changes are paused, so nothing will be saved yet. Say " + q("resume changes") + " first, then yes."
ATTACHMENT_REPLY = ("I can't read photos, voice notes or files yet, so nothing changed. "
                    "Could you type the change instead?")
NOT_READ_REPLY = ("I only notice new messages, so I missed that tap or edit and nothing changed. "
                  "Please send yes, no or the change as a new message.")  # AV1737-03 (H08/H17): owner reaction or edit
PHOTO_QUESTION = ("Is this photo for a product in the shop, a new product, or the home page? "
                  "And what does it show, for people who cannot see it? A few words is fine.")  # NB-AV-09 (H12): asked by every new photo draft
NONE_SAVED = "Nothing from this message was saved."  # AV2152-04: voice rules ban "None" and "drafted"
PHOTO_OPS = ("product.set_photo", "product.add", "store.set_home_image")  # AV0022-04, AV1937-01: ops in a photo-draft answer that get the draft's photo
FETCH_FAILED = "I couldn't get that photo after trying three times, so nothing changed. Could you send it again?"
USAGE = "CREATE TABLE IF NOT EXISTS usage(day TEXT PRIMARY KEY, calls INTEGER NOT NULL)"  # H22; lazy like CONTROL
# HASS-INTERP-OPENAI-1: which backend answered each message. Lazy like CONTROL; written only for an interpreter that names its
# backend. Short codes and seconds only: never the owner's text, the prompt, a URL or a model reply.
AUDIT = """CREATE TABLE IF NOT EXISTS interpreter_audit(provider_id TEXT PRIMARY KEY, at TEXT NOT NULL, backend TEXT NOT NULL,
  fallback INTEGER NOT NULL, primary_error TEXT, error TEXT, seconds REAL)"""
# AVB-10: which audit action (hass/audit.py) a draft row belongs to, the skill that planned it and the action it undoes.
# Lazy like CONTROL. Ids only. A re-written draft (stale, failed) keeps its request's action.
AUDIT_DRAFTS = "CREATE TABLE IF NOT EXISTS audit_drafts(row_id INTEGER PRIMARY KEY, action TEXT NOT NULL, skill TEXT, undo_of TEXT)"
DAILY_LIMIT = ("I've read as many new requests as I can for today, so I couldn't read that one and nothing changed. "
               "Yes, no, undo and status still work. Please send it again tomorrow.")
MAX_OWNER_TEXT = 4000  # AV1737-04 (H05/H22): twice the longest field limit (recap 2000); test_owner_text_cap checks it
MAX_INTERPRETER_ALIASES = 50  # AV0007-06: live owner aliases the interpreter sees (newest first)
MAX_NOTES = 20  # AV1102-09: saved notes the interpreter sees (newest first)
TOO_LONG = "That message is too long for me to read, so nothing changed. Could you send a shorter one?"
OPS_PENDING_MAX = 4096  # AV0022-03: bytes of a draft's ops_json sent in `pending`; larger -> "opsOmitted": true
TRANSITIONS = {"needs-details": {"proposed", "rejected", "expired"}, "proposed": {"approved", "rejected", "expired"},
               "approved": {"applied", "failed", "rejected"}, "applied": {"verified", "reverted"},
               "verified": {"reverted"}}
INTERRUPTED = "interrupted; not applied; approve a new draft"
SOCIAL_REPLY = "Nothing changed. Tell me what you'd like to change, or say " + q("help") + "."  # AV0007-07
UNREADABLE = {"unsupported": "Sorry, I didn't understand that. Could you say it another way?"}
LOOKUP_PREFIX = "You asked, so nothing was drafted.\n"  # AV1104-06: in front of the one reply a lookup gets
HOSTILE_RE = re.compile(r"\b(?:ignore|disregard|forget|override|bypass)\b[^.!?]{0,40}\b(?:rules|instructions|guidelines|approval|safeguards?|previous|above)\b"
                        r"|\b(?:publish|approve|apply|post)\s+(?:everything|all\s+(?:of\s+)?(?:it|changes|drafts))\b|\bskip\s+(?:the\s+)?approvals?\b"
                        r"|\b(?:system|developer)\s+prompt\b|\bjailbreak\b|\bact\s+as\b[^.!?]{0,30}\b(?:admin|root|developer)\b", re.I)
NEAR_STOP_REPLY = "To stop changes, send exactly: " + q("stop changes")  # AV2007-05 (QA1-12): the real words, never model-invented ones
NEAR_RESUME_REPLY = "To resume changes, send exactly: " + q("resume changes")
NEAR_CONTROL_RE = re.compile(r"(?:(?:please|now|thanks) )*(?:(pause|stop)|(resume))(?: changes)?(?: (?:please|now|thanks))*")


def near_control(text):
    """AV2007-05: whole-message pause/stop/resume [changes] with only please/now/thanks around it -> "stop" or "resume"; else None."""
    m = NEAR_CONTROL_RE.fullmatch(re.sub(r"[.!]+$", "", text.strip().lower())) if isinstance(text, str) and len(text) < 100 else None
    return None if m is None else "stop" if m.group(1) else "resume"


# AV1052-09 (H17): a whole one-word message one edit from a command word gets a guess, never a run. The words are frozen here
# (never scraped from the parsers); `photos to take` has several words and is not a candidate.
TYPO_WORDS = tuple(sorted("history undo status pause stop resume help commands find show report post remember forget memory alias approve"
                          " approved cancel reject listing shelf margin cost hidden again".split()))
TYPO_SKIP = frozenset("yes no fine shop past most hold thanks thankyou cheers thx ok okay yep yeah sure".split())  # real words, thanks and casual yeses


def _one_edit(a, b):
    """True when a and b differ by exactly one inserted, deleted or substituted letter, or one adjacent swap."""
    if a == b or abs(len(a) - len(b)) > 1: return False
    i = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), min(len(a), len(b)))
    if len(a) == len(b): return a[i + 1:] == b[i + 1:] or (a[i] == b[i + 1] and a[i + 1] == b[i] and a[i + 2:] == b[i + 2:])
    short, long = sorted((a, b), key=len)
    return short[i:] == long[i + 1:]


def command_typo(text, words=TYPO_WORDS):
    """AV1052-09: the sorted command words one edit from a whole one-word message of 4+ ASCII letters, else []."""
    if not isinstance(text, str) or not text.isascii(): return []
    norm = re.sub(r"[.!]+$", "", text.strip().lower())
    if len(norm) < 4 or not norm.isalpha() or norm in TYPO_SKIP or norm in words: return []
    return sorted({w for w in words if _one_edit(norm, w)})


HOSTILE_REPLY = "I can only publish changes you approve one at a time. Nothing was changed."  # HASS-VOICE-1: no model call, no draft
CORRECTION_RE = re.compile(r"(?:no[,.!]|nope|that'?s (?:wrong|not right|not what)|not what i (?:meant|said|asked)|wrong\b|i didn'?t (?:mean|ask|say)|you got (?:it|that) wrong)", re.I)
RECENT_MINUTES, RECENT_MAX = 30, 500  # HASS-NL-1: how long our last question stays open for a short answer; longest kept
# HASS-HIKE-FLOW-1: the open request. While a question of ours is open, the owner's texts of that request are kept (this
# private store only) so the short answer is read with the request it answers. Gone after RECENT_MINUTES, when a draft or
# a new question outcome closes it, or on `no`; never more than the last ASK_TURNS texts and ASK_CHARS characters.
# SKILLS-FW-3: that store is hass/skills/openreq.py (table open_requests); a pre-FW-3 table open_asks is migrated into it.
# HASS-SHELFCHECK-FLOW-1: the same open request also carries the change Hass could not draft yet (pending_json), when the
# only thing missing was today's shelf check. Plain words only: no "selection", no "not drafted", no ids.
SHELF_QUESTION = "Before I change that, " + SHELF_ASK[0].lower() + SHELF_ASK[1:]
SHELF_CODE_REASON = "shelf-check"  # AV2007-15: drafts.reason of a plain shelf-check draft: its yes must name the code
SHELF_CHECK_LIMIT = "I can take up to 5 sold-out products in one shelf check. Nothing changed."  # AV2007-16
SHELF_NO = "Okay, nothing was changed. Tell me what is different on the shelf list and I will draft that."
QUESTION_DROPPED = "Okay, I've dropped that question"  # AV2007-13
SEPARATE_RE = re.compile(r"(?:what'?s|what is|whats) on special(?:s)?\??")  # AV2007-13: a lookup that is never the answer to a question
SHELF_FAILED = "Sorry, I could not set that up, so nothing was changed. Please send the change again."
SHELF_CLOCK = "The last shelf check is dated in the future, so the date on this phone or computer looks wrong. Nothing was changed."
MEET_NO = "Okay. Where should people meet? Tell me the spot, like a trailhead or a parking lot."  # HASS-CHAT-1
# HASS-CHAT-1 (C): a proposal whose picture could not be drawn is never silent; the picture is tried once more a bit later
PREVIEW_FAILED_HEAD = "I could not draw the picture right now; here is exactly what will change:"
PREVIEW_RETRY_LINE = "I'll try the picture again in a moment."
PREVIEW_RETRY_SECONDS = 30
PREVIEW_LATER = "Here is the picture of how {what} will look."
PREVIEW_STILL_FAILED = "I still couldn't draw the picture for {what}. The change I listed is exactly what will happen."
ASK_TURNS, ASK_CHARS, ASK_TEXT_CUT = 4, 2000, 1000
LATE_AFTER = timedelta(minutes=15)  # AV0022-10 (H16): a reply sent this much after the message it answers says so
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DELAYED_AFTER_S = 600  # AVB-07 (H16): an outbox reply older than this at send time is marked delayed
# HASS-SEC-2 (L5): a yes counts only when it reached the inbox within approvalTtlSeconds plus this of when it was sent (the
# envelope clock window is 300 s, so a yes forwarded at once is always inside it).
LATE_FORWARD_S = 300
LATE_YES_REPLY = ("Your yes reached me long after you sent it, so I haven't saved anything. "
                  "If you still want that change, tell me again.")
VERIFY_MAX = 5  # AV1737-08 (H06): result check captures at most this many distinct touched records
SCHEMA = """
CREATE TABLE IF NOT EXISTS messages(provider_id TEXT PRIMARY KEY, disposition TEXT NOT NULL, received_at TEXT);
CREATE TABLE IF NOT EXISTS message_chats(provider_id TEXT PRIMARY KEY, chat TEXT NOT NULL);  -- HASS-LIVE-PLAN-1: which owner chat a message came from
CREATE TABLE IF NOT EXISTS drafts(row_id INTEGER PRIMARY KEY, change_id TEXT, code TEXT NOT NULL, state TEXT NOT NULL,
  reason TEXT, replaced_by TEXT, draft_hash TEXT, base TEXT, ops_json TEXT NOT NULL, summary TEXT NOT NULL,
  sender TEXT NOT NULL, chat TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT, "commit" TEXT,
  screenshot TEXT, checked_at TEXT, proposed_at TEXT, missing_json TEXT);
CREATE TABLE IF NOT EXISTS approvals(id INTEGER PRIMARY KEY, sender TEXT NOT NULL, chat TEXT NOT NULL,
  provider_id TEXT NOT NULL, change_id TEXT NOT NULL, draft_hash TEXT NOT NULL, base TEXT NOT NULL,
  expires_at TEXT NOT NULL, approved_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY, chat TEXT NOT NULL, text TEXT NOT NULL,
  attachments TEXT NOT NULL, created_at TEXT NOT NULL, sent_at TEXT, reply_to TEXT);
"""


class ConfigError(Exception): """ownerSenders, ownerChat or approvalTtlSeconds is missing or invalid; nothing starts."""


class TransitionError(Exception): """A draft state change outside the allowed transitions."""


class AttachmentPending(Exception): """NB-AV-11 (H16): the photo could not be fetched yet; nothing was recorded."""


class _Held(Exception):
    """handle(apply=False): an owner approval that must roll back unapplied."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


HELD_REPLY = "I can't save changes yet, because I'm not fully connected. Your change is still waiting for you."  # {code} is not shown


@dataclass(frozen=True)
class Inbound:
    provider_id: str
    chat: str
    sender: str
    text: str
    from_me: bool = False
    kind: str = "new"  # new | edited
    received_at: str = ""
    attachments: int = 0  # H12: count only; nothing about the files is kept or downloaded


class Editor:
    """The A2 editor bound to one state dir (production op registry unless a test registry is given)."""

    def __init__(self, state, registry=None):
        self.state, self.registry = str(state), registry

    def prepare(self, ops):
        return editor_mod.prepare({"ops": ops}, state=self.state, registry=self.registry)

    routes_chat = False  # True on an editor that records which owner chat approved (LiveEditor); fixtures keep two arguments

    def apply(self, change_id, draft_hash):
        guard = getattr(self, 'environment_guard', None)
        return editor_mod.apply(change_id, draft_hash, state=self.state, registry=self.registry,
                                **({'guard': lambda: guard(change_id), 'recovery_guard': lambda cid: guard(cid, recorded=True)} if guard else {}))

    def show(self, change_id):
        return editor_mod.show(change_id, state=self.state)

    def recover(self):
        guard = getattr(self, 'environment_guard', None)
        return editor_mod.recover(state=self.state, **({'guard': lambda cid: guard(cid, recorded=True)} if guard else {}))

    def render_draft(self, change_id):
        return editor_mod.render_draft(change_id, state=self.state, registry=self.registry)


class FixtureInterpreter:
    """Maps exact message text to an interpreter result; anything else is unsupported. No model, no network. A result is any
    of the four shapes: ops + revises, question, unsupported, or (AV1104-06) {"lookup": "<read-only command>"}."""

    def __init__(self, mapping):
        self.mapping = dict(mapping)

    def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None):
        return copy.deepcopy(self.mapping.get(text, {"unsupported": "Sorry, I can't do that yet."}))


class Outbox:
    """Replies stored in the same transaction as the result; flush() sends them in order and marks each sent."""

    log = None  # HASS-VOICE-1: a corrlog.CorrLog (set by Conversation); None logs nothing
    strict = os.environ.get("HASS_VOICE_STRICT") == "1"  # tests and CI: a message that breaks a voice rule raises
    msg_id = None  # provider id of the owner message being answered (for the correspondence log)
    emoji_ok = False  # the owner used an emoji first
    private_chat = None  # HASS-VOICE-1: G's own chat (set by Conversation); a reply there that cannot be sent never blocks the owner's
    job_dispatch: Callable | None = None  # NPP cards never go through the legacy text-first send path

    def __init__(self, db, now):
        self.db, self._now = db, now

    def clean(self, text, long_ok=False, ids_ok=False, why="reply") -> str:
        """HASS-VOICE-1: the text to store: a message that breaks a voice rule becomes voice.SAFE_LINE and is logged."""
        broken = voice.check(text, emoji_ok=self.emoji_ok, long_ok=long_ok, ids_ok=ids_ok)
        if not broken: return voice.plain(text)
        if self.strict: raise voice.VoiceError(f"{'; '.join(broken)}: {voice.plain(text)!r}")
        if self.log: self.log.record("voice-fallback", "breaks-" + re.sub(r"[^a-z0-9]+", "-", broken[0].lower()).strip("-")[:30],
                                     msg=self.msg_id)
        return voice.SAFE_LINE

    def add(self, chat, text, attachments=(), reply_to=None, *, long_ok=False, ids_ok=False):
        text = self.clean(text, long_ok, ids_ok)
        attachments = list(attachments)
        row = self.db.execute("INSERT INTO outbox(chat, text, attachments, created_at, reply_to) VALUES (?, ?, ?, ?, ?)",
                              (chat, text, json.dumps(attachments), _iso(self._now()), reply_to)).lastrowid
        transcript.outgoing(self, chat, text, attachments, reply_to)
        return row

    def unsent(self):
        # A switch-off or pin refusal must not release a previously queued NPP card through ordinary send().
        hidden = ""
        if self.job_dispatch is None and self.db.execute("SELECT 1 FROM sqlite_master WHERE name='npp_versions'").fetchone():
            hidden = " AND NOT EXISTS (SELECT 1 FROM npp_versions v WHERE v.outbox_id=outbox.id)"
        return self.db.execute("SELECT * FROM outbox WHERE sent_at IS NULL" + hidden + " ORDER BY id").fetchall()

    def flush(self, adapter) -> int:
        """A raised send error propagates and leaves that row and every later row unsent, except a private row (G's chat):
        if that cannot be sent it is dropped and logged, so it never holds up an owner reply."""
        sent = 0
        for row in self.unsent():
            head = self._late(row["reply_to"]) or self._delayed(row["created_at"])  # the longer wait is the one named
            try:
                if self.job_dispatch is None:
                    adapter.send(row["chat"], head + row["text"], json.loads(row["attachments"]))
                elif not self.job_dispatch(adapter, row, head + row["text"]):
                    continue
            except Exception:
                if row["chat"] != self.private_chat or self.private_chat is None: raise
                self.db.execute("DELETE FROM outbox WHERE id = ?", (row["id"],))
                if self.log: self.log.record("error", "g-reply-not-sent")
                continue
            self.db.execute("UPDATE outbox SET sent_at = ? WHERE id = ?", (_iso(self._now()), row["id"]))
            self._slow(row)
            sent += 1
        return sent

    def _slow(self, row):
        """HASS-VOICE-1: a reply that left more than corrlog.SLOW_SECONDS after the message it answers is a problem moment."""
        if not self.log: return
        try: seconds = (self._now() - datetime.fromisoformat(row["reply_to"])).total_seconds()
        except (TypeError, ValueError): return
        if seconds > corrlog.SLOW_SECONDS: self.log.record("slow", "reply-over-20s", reply=row["id"], seconds=seconds)

    def _late(self, reply_to) -> str:
        """AV0022-10 (H16): send-time heading naming the owner message a reply answers, when sent over LATE_AFTER
        after it (older than 6 days: its date); empty, naive, bad or future -> ''. The stored text never changes."""
        try: sent, now = datetime.fromisoformat(reply_to), self._now()
        except (TypeError, ValueError): return ""
        if sent.tzinfo is None or now - sent <= LATE_AFTER: return ""
        return f"Sorry for the wait. This answers your message from {voice.natural(sent, now)}:\n"

    def _delayed(self, created_at) -> str:
        """AVB-07 (H16): send-time prefix for a reply held over DELAYED_AFTER_S; bad, naive or future -> ''."""
        try: age = (self._now() - datetime.fromisoformat(created_at)).total_seconds()
        except (TypeError, ValueError): return ""
        return "Sorry for the wait. " if age > DELAYED_AFTER_S else ""


def _row_chat(row):
    """The owner chat a draft row belongs to; None (the owner chat) for a row that does not say."""
    try: return row["chat"]
    except (KeyError, IndexError, TypeError): return None


def _pending_ops(ops_json) -> dict:  # AV0022-03 (H05): a waiting draft's ops; too large or unreadable -> opsOmitted
    try: ops = json.loads(ops_json) if len(ops_json.encode()) <= OPS_PENDING_MAX else None
    except (TypeError, ValueError, AttributeError, RecursionError): ops = None
    return {"ops": ops} if isinstance(ops, list) else {"opsOmitted": True}


def _missing_ids(missing_json) -> list:  # AV0007-03: stored argument ids of a question; anything unreadable -> []
    try: ids = json.loads(missing_json) if missing_json else []
    except (TypeError, ValueError, RecursionError): return []
    out = []
    for i in ids if isinstance(ids, list) else []:
        if not isinstance(i, str): return []
        if i and i not in out: out.append(i)
    return out


def _answered_at(msg, now: datetime) -> datetime:
    """AV0022-06 (H16): when the owner sent the reply (received_at); empty, naive, bad or future -> now."""
    try: sent = datetime.fromisoformat(msg.received_at or "")
    except (TypeError, ValueError): return now
    return sent if sent.tzinfo is not None and sent <= now else now


def _local(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M %Z")


def _hike_time(iso):  # AV1737-07 (H04/H05): `Sat 2026-11-07 09:00 PST`; a bad or naive value is shown raw, never raised
    try: start = datetime.fromisoformat(iso)
    except (ValueError, TypeError): return iso
    return iso if start.tzinfo is None else start.astimezone(LOCAL_TZ).strftime("%a %Y-%m-%d %H:%M %Z")


def sender_key(value):
    """AV2022-08 (H08): an email (casefolded) or `+` and 8-15 digits (spaces, dashes, dots, brackets dropped); else None."""
    if not isinstance(value, str): return None
    value = value.strip()
    if re.fullmatch(r"\+[0-9 .()-]+", value):
        digits = re.sub(r"[^0-9]", "", value)
        return "+" + digits if 8 <= len(digits) <= 15 else None
    local, at, domain = value.partition("@")
    ok = at and local and "@" not in domain and "." in domain and not re.search(r"\s", value)
    return value.casefold() if ok else None


MAX_CONFIG = 1024 * 1024  # RF1910-2 (H08/H20)
MAX_OWNER_CHATS = 8  # HASS-OWNERS-2: the most owner chats one config may name


def _config_bytes(sdir):
    """RF1910-2: config.json bytes from a regular, non-link file <= 1 MiB; None when missing; else ConfigError."""
    path, bad = Path(sdir) / "config.json", ConfigError("config.json must be a regular file up to 1 MiB")
    try: st = os.lstat(path)
    except FileNotFoundError: return None
    if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_CONFIG: raise bad  # link, FIFO, folder, too big: never opened
    with open(path, "rb") as fh: data = fh.read(MAX_CONFIG + 1)
    if len(data) > MAX_CONFIG: raise bad  # grew past the cap after lstat; the reason names no path or content
    return data


def load_settings(sdir, photos=False) -> dict:
    try:
        data = _config_bytes(sdir)
        settings = None if data is None else json.loads(data.decode("utf-8")).get("settings")
    except (OSError, ValueError, AttributeError, RecursionError, UnicodeDecodeError):
        settings = None
    if not isinstance(settings, dict): raise ConfigError("config.json settings are missing")
    senders, chat, ttl = (settings.get(k) for k in ("ownerSenders", "ownerChat", "approvalTtlSeconds"))
    problems = []
    chats_in = settings.get("ownerChats")  # HASS-OWNERS-2: optional list; with it, ownerChat (if also set) is one of its entries
    keys = [sender_key(s) for s in senders] if isinstance(senders, list) else []
    if not keys: problems.append("ownerSenders must be a non-empty list of sender addresses")
    problems += [f"ownerSenders entry {n} is not an email address or a +country phone number"  # value never echoed
                 for n, key in enumerate(keys, 1) if key is None]
    if chats_in is not None: pass  # HASS-OWNERS-2: every entry is checked below, and ownerChat must be one of them
    elif not isinstance(chat, str) or not chat.strip(): problems.append("ownerChat must be a chat id")
    elif ";+;" in chat:  # AVB-02 (H08): the owner channel is the owner's one-to-one chat, never a group; ids never echoed
        problems.append("ownerChat is a group chat; it must be the owner's one-to-one chat")
    elif (direct := re.fullmatch(r"[^;]+;-;([^;]+)", chat)) and sender_key(direct[1]) not in keys:
        problems.append("ownerChat is a one-to-one chat with an address that is not in ownerSenders")
    chats, chat_keys, names, before = None, {}, {}, len(problems)
    if chats_in is not None:  # HASS-OWNERS-2: several owners, each in their own one-to-one chat; ids and addresses never echoed
        if not isinstance(chats_in, list) or not 1 <= len(chats_in) <= MAX_OWNER_CHATS:
            problems.append(f"ownerChats must be a list of 1 to {MAX_OWNER_CHATS} chat ids")
        else:
            for n, c in enumerate(chats_in, 1):
                direct = re.fullmatch(r"[^;]+;-;([^;]+)", c) if isinstance(c, str) else None
                if not isinstance(c, str) or not c.strip(): problems.append(f"ownerChats entry {n} must be a chat id")
                elif ";+;" in c: problems.append(f"ownerChats entry {n} is a group chat; it must be an owner's one-to-one chat")
                elif not direct: problems.append(f"ownerChats entry {n} must be a one-to-one chat id like iMessage;-;<address>")
                elif sender_key(direct[1]) not in keys: problems.append(f"ownerChats entry {n} is a one-to-one chat with an address that is not in ownerSenders")
                else: chat_keys[c] = frozenset({sender_key(direct[1])})
            strs = [c for c in chats_in if isinstance(c, str)]  # a {} or [] entry is already reported above and is never hashed
            if len(set(strs)) != len(strs): problems.append("ownerChats has the same chat twice")
            if chat is not None and chat not in chats_in: problems.append("ownerChat must be one of ownerChats")
            if len(problems) == before: chats, chat = tuple(chats_in), chat or chats_in[0]  # no ownerChat: the first owner chat is the main one
    n_in = settings.get("ownerNames")  # HASS-OWNERS-2: optional {chat id: short first name}, used only to say whose change it was
    if n_in is not None:
        if not isinstance(n_in, dict) or chats is None or any(k not in chats for k in n_in) or not all(
                isinstance(v, str) and re.fullmatch(r"[^\W\d_][^\W\d_ '.-]{0,19}", v) for v in n_in.values()):
            problems.append("ownerNames must map an ownerChats chat id to a short first name (letters only, up to 20)")
        else: names = dict(n_in)
    if type(ttl) is not int or ttl < 60: problems.append("approvalTtlSeconds must be an integer >= 60")
    root = settings.get("mediaRoot")  # NB-AV-09: required only with a photo source
    if photos and (not isinstance(root, str) or not root.strip()): problems.append("mediaRoot must be set to use photos")
    cap = settings.get("interpreterDailyCap")  # H22: optional; absent or null means no cap (no default enables it)
    if cap is not None and (type(cap) is not int or not 1 <= cap <= 10000):
        problems.append("interpreterDailyCap must be an integer 1-10000")
    g_senders = settings.get("gSenders")  # HASS-VOICE-1: optional; only these numbers may ask for `problems` (never an owner number)
    g_keys = [sender_key(g) for g in g_senders] if isinstance(g_senders, list) else []
    if g_senders is not None and (not isinstance(g_senders, list) or None in g_keys or set(g_keys) & set(keys)):
        problems.append("gSenders must be a list of sender addresses that are not owner senders")
    g_chat = settings.get("gChat")  # HASS-VOICE-1: G's own one-to-one chat; the only place `problems` and `weekly` are answered
    if g_keys and g_senders is not None:
        if not isinstance(g_chat, str) or not g_chat.strip(): problems.append("gChat must be set to G's own chat when gSenders is set")
        elif g_chat == chat or chats is not None and g_chat in chats: problems.append("gChat must not be the owner chat")
        elif ";+;" in g_chat: problems.append("gChat is a group chat; it must be G's one-to-one chat")
        elif (direct := re.fullmatch(r"[^;]+;-;([^;]+)", g_chat)) and sender_key(direct[1]) not in g_keys:
            problems.append("gChat is a one-to-one chat with an address that is not in gSenders")
    elif g_chat is not None: problems.append("gChat needs gSenders")
    g_owner = settings.get("gIsOwner", False)  # HASS-LIVE-PLAN-1: G's own chat is a second owner chat (text only)
    if type(g_owner) is not bool or g_owner and not (g_keys and isinstance(g_chat, str)): problems.append("gIsOwner must be true or false, and true needs gSenders and gChat")
    site, needs_code = settings.get("liveSite"), settings.get("approvalNeedsCode", False)
    if site is not None and (not isinstance(site, str) or not re.fullmatch(r"[a-z0-9.-]{3,253}", site) or "." not in site):
        problems.append("liveSite must be a hostname")
    if type(needs_code) is not bool or site is not None and needs_code is not True:
        problems.append("approvalNeedsCode must be a bool and true with liveSite")
    skills = settings.get("skills")  # SKILLS-FW-3: {"mode": ops-only | both | skills-first} (or the flat key "skills.mode"); absent = ops-only
    mode = settings.get("skills.mode", dispatch_mod.DEFAULT_MODE) if skills is None else skills.get("mode", dispatch_mod.DEFAULT_MODE) if isinstance(skills, dict) else None
    if mode not in dispatch_mod.MODES: problems.append("skills.mode must be ops-only, both or skills-first")
    house = settings.get("houseRender", False)  # SKILLS-FW-3: read here, used by the picture card (SKILLS-PIC-1); default off
    if type(house) is not bool: problems.append("houseRender must be true or false")
    polish = settings.get("photo_polish", False)  # HASS-IMAGE-1: background photo clean-up via Hermes; default off
    if type(polish) is not bool or polish and house is not True: problems.append("photo_polish must be true or false, and true needs houseRender")
    intake = settings.get("itemIntake", False)  # HASS-INTAKE-2: the full intake interview for a new item; default off, like houseRender
    if type(intake) is not bool: problems.append("itemIntake must be true or false")
    npp = settings.get("npp", False)
    if type(npp) is not bool or npp and not (isinstance(root, str) and root.strip()):
        problems.append("npp must be true or false, and true needs mediaRoot")
    lookup = settings.get("hikeLookup")  # HIKE-LOOKUP-2: {"contact": address} (or the flat key "hikeLookup.contact"); absent = no map lookup, the plain hike flow
    contact = settings.get("hikeLookup.contact") if lookup is None else lookup.get("contact") if isinstance(lookup, dict) else False
    if contact is not None and hike_lookup.valid_contact(contact) is None: problems.append("hikeLookup.contact must be an e-mail address or an https link")
    if problems: raise ConfigError("; ".join(problems))
    return {"ownerSenders": tuple(senders), "ownerKeys": frozenset(keys), "ownerChat": chat, "approvalTtlSeconds": ttl,
            "mediaRoot": root, "guestCountsDb": settings.get("guestCountsDb"),  # guestCountsDb: H17, unchecked
            "interpreterDailyCap": cap, "skillsMode": mode, "houseRender": house,  # SKILLS-FW-3
            **({"photo_polish": True} if polish is True else {}),  # HASS-IMAGE-1: only when on
            **({"hikeLookupContact": contact} if contact is not None else {}),  # HIKE-LOOKUP-2: only when set
            **({"itemIntake": True} if intake is True else {}),  # HASS-INTAKE-2: only when on
            **({"npp": True} if npp is True else {}),
            **({k: settings[k] for k in ("liveSite", "approvalNeedsCode") if k in settings}),
            **({"gKeys": frozenset(g_keys), "gChat": g_chat, "gSenders": tuple(g_senders)} if g_keys and isinstance(g_chat, str) else {}),
            **({"gOwner": True} if g_owner is True else {}),
            **({"ownerChats": chats, "chatKeys": chat_keys, "ownerNames": names} if chats is not None else {})}  # HASS-OWNERS-2: only when set


def _checked(result) -> dict:
    if isinstance(result, dict):
        if set(result) == {"ops", "revises"} and isinstance(result["ops"], list) \
                and (result["revises"] is None or isinstance(result["revises"], str)):
            return result
        for key in ("question", "unsupported"):
            if set(result) == {key} and isinstance(result[key], str) and result[key].strip(): return result
        if set(result) == {"lookup"} and isinstance(result["lookup"], str): return result  # AV1104-06: even "" (interpret_check refuses it)
    return dict(UNREADABLE)


def _reason(out: dict) -> str:
    return out.get("reason") or "; ".join(out.get("problems") or []) or out.get("question") or str(out.get("result"))


def _photo_sentence(technical):
    """The sentence the house picture step wrote for Mike (hass.ops.photos: retake asks, a photo it cannot open, the picture it
    cannot make), when ``technical`` is exactly one of them; None for any other reason."""
    from hass.ops import photos  # lazy: the picture step is only read when a photo refused
    text = str(technical or "").strip()
    known = {*photos.RETAKE.values(), *photos.RENDER_REPLY.values(), photos.MAKE_FAILED, photos.ALREADY_RAW}
    return text if text in known else None


class Conversation(CorePack, SitePack, ReportsPack):  # AVB-12: the pack commands are in hass/chat/
    stage = staticmethod(stagelog.off)

    def __init__(self, state_dir, editor, interpreter, clock, previewer=None, photos=None, labels=None, skills=None,
                 *, npp_stages=None, npp_executor=None, npp_receipt_for=None):
        """previewer (H06, e.g. preview.Previewer(worktree)): proposal screenshots and checked results; None keeps
        the H05 behaviour (no screenshot, an applied draft stays `applied`). skills (SKILLS-FW-3): a skills Registry; only read
        when the setting skills.mode is not ops-only, and then loaded with load_skills() when None."""
        sdir = editor_mod.open_state(state_dir)
        self.settings, self.photos = load_settings(sdir, photos is not None), photos  # fetch(provider_id, n) -> [bytes]
        self.editor, self.interpreter, self.clock, self.labels, self._label_jobs = editor, interpreter, clock, labels, []
        self._polish_jobs, self.polish_transport = [], None  # HASS-IMAGE-1: None = the real Hermes route (tests inject a stub)
        self.sdir, self.previewer = sdir, previewer
        path = memory_mod.private_db(sdir, "conversation.sqlite3")
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        columns = {r["name"] for r in self.db.execute("PRAGMA table_info(drafts)")}
        for column in ("screenshot", "checked_at", "proposed_at", "missing_json"):  # an H05 database gains the H06 + AVB-03 + AV0007-03 columns
            if column not in columns: self.db.execute(f"ALTER TABLE drafts ADD COLUMN {column} TEXT")
        if "reply_to" not in {r["name"] for r in self.db.execute("PRAGMA table_info(outbox)")}:  # AV0022-10 (H16)
            self.db.execute("ALTER TABLE outbox ADD COLUMN reply_to TEXT")
        # AVB-03 (H05): an open draft from before proposed_at has no recoverable proposal instant (a filled question
        # keeps its question's created_at), so it counts as proposed when this store is opened: a yes sent earlier is
        # refused and the owner re-sends it; it is never judged from created_at or from the current ttl.
        if self.db.execute("SELECT 1 FROM drafts WHERE proposed_at IS NULL AND state = 'proposed' LIMIT 1").fetchone():
            self.db.execute("UPDATE drafts SET proposed_at = ? WHERE proposed_at IS NULL AND state = 'proposed'",
                            (_iso(self._now()),))  # the clock is read only when such a draft exists
        self.outbox = Outbox(self.db, self._now)
        self.outbox.private_chat = self.settings.get("gChat")
        self.log = self.outbox.log = corrlog.CorrLog(self.sdir, self._now)  # HASS-VOICE-1: the correspondence log (state folder only)
        self.audit = audit_mod.AuditLog(self.sdir, self._now)  # AVB-10: one line per step of every action (ids only)
        self.memory = None  # H15 store on this same connection, opened by the first memory command
        self.requests = openreq.OpenRequests(self.db)  # SKILLS-FW-3: the one open-request store (lazy table)
        self.skills_mode = self.settings["skillsMode"]
        self.dispatch = None
        if self.skills_mode != dispatch_mod.DEFAULT_MODE:
            from hass.skills import load_skills
            self.dispatch = dispatch_mod.Dispatcher(self, skills if skills is not None else load_skills())
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'open_asks'").fetchone():
            self.requests.adopt_legacy(self.settings["ownerChat"])  # a store made before FW-3 keeps its open request
        self.npp = None
        if self.settings.get("npp"):
            try:
                pinned = npp_package.assets()
            except (OSError, ValueError, KeyError, TypeError):
                self._problem("error", "npp-pins-refused")  # the reviewed fallback is today's item.add
            else:
                stages = npp_stages if npp_stages is not None else npp_package.stages_for(self, pinned)
                self.npp = listing_jobs.Jobs(self, stages, pinned, npp_executor, npp_receipt_for)
                self.outbox.job_dispatch = self.npp.dispatch
        self.recover()

    def _now(self) -> datetime:
        return self.clock()

    _audit_lines = None  # AVB-10: audit lines of the open transaction; written only after it commits, dropped on rollback

    @contextlib.contextmanager
    def _tx(self):
        self.db.execute("BEGIN IMMEDIATE")
        self._audit_lines = []
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            self._audit_lines = None
            raise
        self.db.execute("COMMIT")
        lines, self._audit_lines = self._audit_lines, None
        for step, line in lines: self.audit.record(step, **line)

    # -- AVB-10: the audit log ------------------------------------------------------------------------------------
    _skill_ref = None  # the skill(s) planning the draft being made (`item.add@3`), set by the skills dispatcher

    def _audit_role(self, chat) -> str:
        """The audit role of an owner chat: `owner:g` for G's own chat, `owner:<first name>` (ownerNames, ASCII letters), else `owner`."""
        if chat is not None and chat == self.settings.get("gChat"): return "owner:g"
        name = self.settings.get("ownerNames", {}).get(chat)
        return f"owner:{name.lower()}" if isinstance(name, str) and re.fullmatch(r"[A-Za-z]{1,20}", name) else "owner"

    def _audit_of(self, row):
        """(action, skill, undo_of) of a draft row; a row from before the audit log gets its action now."""
        self.db.execute(AUDIT_DRAFTS)
        link = self.db.execute("SELECT action, skill, undo_of FROM audit_drafts WHERE row_id = ?", (row["row_id"],)).fetchone()
        if link is not None: return tuple(link)
        action = audit_mod.new_action("draft", row["row_id"], row["code"], row["created_at"])
        self.db.execute("INSERT INTO audit_drafts(row_id, action) VALUES (?, ?)", (row["row_id"], action))
        return action, None, None

    def _audit_link(self, row, like=None, undo_of=None):
        """Bind a freshly proposed row to its action: the action of `like` (a re-written draft of the same request), the
        action it already has (a filled question), or a new one; the skill is the dispatcher's, or `like`'s."""
        self.db.execute(AUDIT_DRAFTS)
        old = self._audit_of(like) if like is not None else None
        mine = self.db.execute("SELECT action FROM audit_drafts WHERE row_id = ?", (row["row_id"],)).fetchone()
        action = old[0] if old else mine[0] if mine else audit_mod.new_action("draft", row["row_id"], row["code"], row["created_at"])
        skill = self._skill_ref if isinstance(self._skill_ref, str) and audit_mod.SKILL_RE.fullmatch(self._skill_ref) else old[1] if old else None
        self.db.execute("INSERT OR REPLACE INTO audit_drafts(row_id, action, skill, undo_of) VALUES (?, ?, ?, ?)",
                        (row["row_id"], action, skill, undo_of if undo_of is not None else old[2] if old else None))

    def _audit(self, step, row, result="ok", records=None, **extra):
        """AVB-10: one audit line for a step of this draft row's action: ids, codes and fixed words only (never the owner's
        text or a value). Inside a transaction it is written when the transaction commits. Never raises past the log."""
        try:
            action, skill, undo_of = self._audit_of(row)
            change, msg = row["change_id"], self.outbox.msg_id
            refs = {"change": change} if isinstance(change, str) and audit_mod.REFS["change"].fullmatch(change) else {}
            commit = extra.pop("commit", None)
            if isinstance(commit, str) and audit_mod.REFS["commit"].fullmatch(commit): refs["commit"] = commit
            line = dict(action=action, who=self._audit_role(row["chat"]), pack="site", target="site",
                        env="live" if self.settings.get("liveSite") else "sandbox", result=result, draft=row["code"],
                        skill=skill, undo_of=undo_of, msg=_short(msg) if msg else None, refs=refs,
                        subjects=audit_mod.subjects_of(records), fields=audit_mod.fields_of(records), **extra)
        except Exception:  # noqa: BLE001 - an audit line is never worth a lost reply
            return
        if self._audit_lines is not None: self._audit_lines.append((step, line))
        else: self.audit.record(step, **line)

    def _audit_ask(self, msg, step, result, skills=(), n=0):
        """AVB-10: one audit line for a skill request that makes no draft: a read-only answer (`answered`, A0) or a refusal
        before any draft (`refused`). The action is one id per (message, skill call); the line holds the skill names, the
        pack, the one-way message id and a fixed result word only: never the request, the answer, a price or a count."""
        try:
            names = [s.name if hasattr(s, "name") else s for s in skills if s is not None]
            refs = [f"{s.name}@{s.version}" if hasattr(s, "name") else s for s in skills if s is not None]
            skill = "+".join(dict.fromkeys(r for r in refs if isinstance(r, str))) or None
            line = dict(action=audit_mod.new_action("ask", msg.provider_id, skill or "-", n), who=self._audit_role(msg.chat),
                        pack=audit_mod.pack_of(names), target="local", env="live" if self.settings.get("liveSite") else "sandbox",
                        result=result, skill=skill if skill and audit_mod.SKILL_RE.fullmatch(skill) else None,
                        msg=_short(msg.provider_id), approval="A0" if step == "answered" else None)
        except Exception:  # noqa: BLE001 - an audit line is never worth a lost reply
            return
        if self._audit_lines is not None: self._audit_lines.append((step, line))
        else: self.audit.record(step, **line)

    def flush(self, adapter) -> int:
        if self.npp is not None:
            self.npp.pump()
        sent = self.outbox.flush(adapter)
        if self.npp is not None:
            self.npp.refresh_receipts()
            self.npp.write_receipts()
        return sent

    # -- store helpers -------------------------------------------------------------------------------------------
    def _row(self, row_id):
        return self.db.execute("SELECT * FROM drafts WHERE row_id = ?", (row_id,)).fetchone()

    def _drafts(self, where: str, *args):
        return self.db.execute(f"SELECT * FROM drafts WHERE {where} ORDER BY row_id", args).fetchall()

    def _by_code(self, code, states=None):
        rows = [r for r in self._drafts("code = ?", code) if self._mine(r) and (states is None or r["state"] in states)]
        return rows[-1] if rows else None

    def _expiry(self, row) -> datetime:
        """H16: a needs-details row stored before expiry existed (expires_at NULL) lapses at created_at + ttl."""
        if row["expires_at"]: return datetime.fromisoformat(row["expires_at"])
        return datetime.fromisoformat(row["created_at"]) + timedelta(seconds=self.settings["approvalTtlSeconds"])

    def _proposed_at(self, row) -> datetime:
        """AVB-03 (H05): the stored instant the draft was proposed (_propose sets it on insert and on a needs-details
        fill), so a later approvalTtlSeconds change never moves it. Opening the store stamps an open draft from before
        the column with the open instant; a proposed row still without one fails closed (now: only a yes sent now)."""
        return datetime.fromisoformat(row["proposed_at"]) if row["proposed_at"] else self._now()

    def _move(self, row, state, **fields):
        current = self._row(row["row_id"])["state"]
        if state not in TRANSITIONS.get(current, ()) or \
                (current, state) == ("approved", "rejected") and fields.get("reason") != "stale":
            raise TransitionError(f"draft {row['code']}: {current} -> {state} is not allowed")
        cols = {"state": state, **fields}  # column names are fixed identifiers from this module, quoted ("commit")
        assignments = ", ".join('"%s" = ?' % k for k in cols)
        self.db.execute(f"UPDATE drafts SET {assignments} WHERE row_id = ?", (*cols.values(), row["row_id"]))

    def _code(self, hexdigest: str) -> str:
        """A code is never reissued, not even a cancelled/expired draft's: a late `yes <old code>` names only that draft.
        A repeat of the same hash has no unused prefix left, so it takes the next code from a derived digest."""
        taken = {r["code"] for r in self._drafts("1")}
        while True:
            for size in range(4, 13, 2):
                if hexdigest[:size] not in taken and (self.npp is None or not self.npp.taken(hexdigest[:size])):
                    return hexdigest[:size]
            hexdigest = hashlib.sha256(f"{hexdigest}:repeat".encode()).hexdigest()

    def _repeat(self, row) -> bool:
        """True when an earlier draft had this exact hash (it was cancelled, expired, replaced or failed)."""
        if not row["draft_hash"]: return False
        return bool(self._drafts("draft_hash = ? AND row_id < ?", row["draft_hash"], row["row_id"]))

    def _earlier_outcome(self, row) -> str:
        """AV2007-06: what became of the newest earlier draft with this row's hash: timed out, cancelled, couldn't save,
        replaced, or (anything else) a neutral description. Only words the repeat warning uses; never changes admission."""
        if not row["draft_hash"]: return "was written up"
        earlier = self.db.execute("SELECT * FROM drafts WHERE draft_hash = ? AND row_id < ? ORDER BY row_id DESC LIMIT 1",
                                  (row["draft_hash"], row["row_id"])).fetchone()
        if earlier is None: return "was written up"
        state = earlier["state"]
        if state == "expired": return "timed out"
        if state == "failed": return "I couldn't save"
        if state == "rejected":
            return "was replaced" if earlier["reason"] == "revised" or earlier["replaced_by"] else "you cancelled"
        return "I wrote up"

    def _named(self, row) -> bool:
        """AV2152-03: a draft whose yes must name its code: a repeat of a closed hash (_repeat), or one made by `again <code>`
        (reason `again:<old code>`), whose hash can differ from every earlier draft's when the site's base moved."""
        return self._repeat(row) or str(row["reason"] or "").startswith("again:")

    def _carry_again(self, old, new):
        """AV2152-03: a proposal written up again from an `again` draft
        (stale, env-changed, failed) stays an `again` draft. Returns the row as saved: the caller renders the proposal from it,
        and a snapshot from before the reason was written would not say the yes must name its code."""
        if (str(old["reason"] or "").startswith("again:") or old["reason"] == SHELF_CODE_REASON) and new is not None:
            self.db.execute("UPDATE drafts SET reason = ? WHERE row_id = ?", (old["reason"], new["row_id"]))
            return self._row(new["row_id"])
        return new

    _to = None  # HASS-LIVE-PLAN-1: the owner chat being answered (a message's chat, or an old draft's); None means ownerChat

    def _chat(self) -> str:
        return self._to or self.settings["ownerChat"]

    # -- HASS-OWNERS-2: several owners, each in their own one-to-one chat (settings ownerChats); none set = ownerChat alone, as before
    @property
    def _owner_chats(self) -> tuple:
        return self.settings.get("ownerChats") or (self.settings["ownerChat"],)

    @property
    def _shared(self) -> bool:
        """True with two or more ownerChats: one site, so a draft, the open release and `history` are shared and say whose they are."""
        return len(self._owner_chats) > 1

    def _who(self, chat) -> str:
        """The short first name the config gives this owner chat (ownerNames), else `the owner`."""
        return self.settings.get("ownerNames", {}).get(chat) or "the owner"

    def _whose(self, chat, capital=True) -> str:
        """`Your change` for the asking chat, else `Mike's change` (`The owner's change` when no name is set)."""
        if chat == self._chat(): return "Your change" if capital else "your change"
        who = self._who(chat)
        return (who[0].upper() + who[1:] if capital else who) + "'s change"

    def _visible(self, row) -> bool:
        """With several owners a row shown as 'waiting for your yes' must be this chat's own; alone it is every row, as before."""
        return not self._shared or self._mine(row)

    def _writer_busy(self, now):
        """HASS-OWNERS-2 (one site, one writer, one release at a time): with several owners, the other owner chat that holds the
        writer (a draft waiting for a yes or for details, one being saved, or a release still open) as (chat, 'draft' | 'release'),
        else None. Alone this is always None, so a single owner is answered exactly as before."""
        if not self._shared: return None
        mine = self._chat()
        for r in self._drafts("state IN ('proposed', 'needs-details', 'approved')"):
            if r["chat"] != mine and (r["state"] == "approved" or self._expiry(r) > now): return r["chat"], "draft"
        release = getattr(self.editor, "open_release", None)  # a live editor names the chat whose release has not settled
        other = release() if callable(release) else None
        return (other, "release") if other is not None and other != mine else None

    def _busy_reply(self, busy) -> str:
        chat, kind = busy
        who = self._who(chat)
        who = who[0].upper() + who[1:]
        self._reply(f"{who} has a change waiting, so I haven't started yours. Please ask me again once it's saved or cancelled." if kind == "draft"
                    else f"{who}'s change is going on the website right now, so I haven't started yours. Please ask me again in a few minutes.")
        return "writer-busy"

    _asker = None  # HASS-OWNERS-2: the normalized sender key of the message handle() is running; None outside a message

    def _mine(self, row) -> bool:
        """A draft belongs to the owner chat that made it: another owner's yes, no or undo never reaches it. With several owners a
        draft that is still open (proposed, waiting for details, approved) is also bound to the sender who made it, so a draft kept
        from before a second owner was added (one shared chat) is never approved or cancelled by the other person."""
        if row["chat"] != self._chat(): return False
        if self._shared and self._asker is not None and row["state"] in ("proposed", "needs-details", "approved"):
            return sender_key(row["sender"]) == self._asker
        return True

    @contextlib.contextmanager
    def _answer_to(self, chat):
        before, self._to = self._to, chat
        try: yield
        finally: self._to = before

    _lookup_prefix = None  # AV1104-06: text put before the next reply only (set and restored by _lookup)
    _lapsed = ()  # AV1104-06: lapsed drafts whose move to `expired` waits for the interpreter's answer (a lookup never moves them)
    _said = None  # SKILLS-FW-3: the text of the newest reply queued while handling a message (a question kept on the open request)
    _last_draft_code = None  # SKILLS-FW-3: the code of the draft row the last _draft call proposed or asked about

    def _reply(self, text, attachments=(), **flags):
        chat = self._chat()
        if chat not in self._owner_chats: attachments = ()  # G's chat is text only (the Mac sends no pictures there); every owner chat gets pictures
        if self._lookup_prefix is not None:  # AV1104-06: the first reply of a lookup says nothing was drafted; consumed once
            text, self._lookup_prefix, flags = self._lookup_prefix + text, None, {**flags, "long_ok": True}
        self._said = text
        self.outbox.add(chat, text, attachments, self._answering or None, **flags)

    def _problem(self, kind, reason, **extra):
        """HASS-VOICE-1: one row in the correspondence log (state folder only) for the message being answered."""
        self.log.record(kind, reason, msg=self.outbox.msg_id, **extra)

    def _plain(self, technical, doing="make that change") -> str:
        """The refusal text in everyday words; a reason we have no words for gets the generic line. Always logged."""
        said = _photo_sentence(technical)  # the picture's own plain sentence (retake, too big, ...) is already for Mike: said as it is
        if said:
            self._problem("could-not-do", "photo-retake")
            return said
        sentence, code = voice.explain(technical)
        self._problem("could-not-do", code)
        return sentence if code != "unmapped" else f"I couldn't {doing}, so nothing changed. Could you say it another way?"

    def _when(self, iso) -> str:
        return voice.natural_iso(iso, self._now())

    def _save_private(self, row, reasons):
        """HASS-LIVE-PLAN-1: a change chat may not put on the website is kept once as a private proposal (one `policy` row in
        the private backlog: what was asked, why it is refused, the exact steps), so Graham can do it by hand. It never changes
        the website or the writer worktree. Read it with `python3 hass/skills/backlog.py list --state DIR --text`."""
        from hass.skills.backlog import Backlog  # lazy: the skills package is not needed to read a conversation
        marker = f"[{row['code']}]"
        backlog = Backlog(self.db, self._now)
        if self.db.execute("SELECT 1 FROM backlog WHERE reason = 'policy' AND summary LIKE ?", (marker + "%",)).fetchone(): return
        backlog.record("policy", f"{marker} {row['summary']}", f"Live change refused ({'; '.join(reasons)}). Proposed change {row['code']}: "
                       f"{row['summary']}. Steps: {row['ops_json']}")
        self._problem("could-not-do", "live-policy")

    def _live_reasons(self, draft) -> list:
        """live_policy.check, and HASS-SEC-2 (M1): an undo of a change the release engine never put on the website (saved in
        private mode before live) is refused too. Only a live editor (publish_live.LiveEditor.went_live) can tell; its apply()
        refuses the same undo again."""
        if draft and draft.get("environment", {}).get("env") == "sandbox": return []
        reasons = live_policy.check(draft)
        went_live = getattr(self.editor, "went_live", None)
        if callable(went_live) and live_policy.is_undo(draft) and not all(went_live(cid) for cid in live_policy.undone(draft)):
            reasons = sorted({*reasons, live_policy.UNDO_NOT_LIVE})
        return reasons

    def _capture(self, draft, *, candidate=False):
        """The proposal screenshot of ``draft`` (H06): {"ok", "png", "error"}; never raises past the previewer's own guard."""
        rendered = self.editor.render_candidate(draft) if candidate else self.editor.render_draft(draft["change_id"])
        for path, digest in draft.get("assets", {}).items():
            data = rendered.get("assets", {}).get("storefront-mockup/" + path)
            if data is None or "sha256:" + hashlib.sha256(data).hexdigest() != digest:
                return {"ok": False, "png": None, "error": "draft picture changed"}
        extra = {"assets": rendered["assets"]} if rendered.get("assets") else {}  # a new photo the draft would add
        record = preview_mod.proposal_record(draft["records"])
        if record.get("collection") == "products":
            record = next((r for r in reversed(draft["records"]) if r.get("collection") == "products" and r.get("key") == record.get("key")), record)
        target = preview_mod.target_for(record, shop_today(), store=rendered.get("store"))
        if ((candidate or self.settings.get("itemIntake") is True) and target.get("kind") == "product"
                and any(call.get("op") == "product.add" for call in draft.get("ops", []))):
            target.update(cardOnly=True, image=record["after"].get("image"))
            if price := record["after"].get("sellingPrice"):
                target["price"] = "$" + price
        if rendered.get("result") != "ok":
            return {"ok": False, "png": None, "error": _reason(rendered)}
        shot = self.previewer.capture(rendered["files"], target,
                                      self.sdir / "screenshots" / f"{draft['change_id']}-proposal.png", **extra)
        if candidate and shot.get("ok"):
            shot = {**shot, "picture": rendered.get("assets", {}).get("storefront-mockup/" + target["image"])}
        return shot

    def _proposal_reply(self, row, draft, prefix="", notes=()):
        """The proposal text plus, with a previewer, a private screenshot of the rendered draft (H06). HASS-CHAT-1: a picture
        that could not be drawn is never silent: the text says so first, the proposal is complete without it, and the picture
        is tried once more later for ordinary proposals. Simple listings answer once; '?' can ask for a new card."""
        reasons = self._live_reasons(draft) if self.settings.get("liveSite") else []
        if reasons: self._save_private(row, reasons)
        listing = getattr(self, "_intake_listing", None)
        if listing is None and not _is_undo(row) and self.dispatch is not None and self.dispatch.simple_intake():
            req = self.requests.get(self._chat(), self._now())
            if req and req["draft_code"] == row["code"] and req["slots"].get("intake", {}).get("simple"):
                listing = req["slots"]
        shot, shots, head, tail = None, [], "", ""
        if self.previewer is not None:
            if listing: self.stage("card-start", self.outbox.msg_id)
            try: shot = self._capture(draft)
            finally:
                if listing: self.stage("card-end", self.outbox.msg_id)
            shots = [shot["png"]] if shot.get("png") else []
            if not shot["ok"]:
                self._problem("error", "preview-failed", excerpt=preview_mod.failure_kind(shot.get("error")))
                if shots: tail = "\nThe picture may not show every part of this change; the list above is exactly what will change."
                else:
                    head = PREVIEW_FAILED_HEAD
                    if not listing:
                        tail = "\n" + PREVIEW_RETRY_LINE
                        self._queue_preview_retry(row)
        undo = _is_undo(row)
        coded = self._named(row) or row["reason"] == SHELF_CODE_REASON or (undo and self.settings.get("approvalNeedsCode", False))
        text = prefix + proposal_text(row["code"], draft, row["expires_at"], coded, head=head, undo=undo,
                                      live_site=self.settings.get("liveSite") if draft.get("environment", {}).get("env") != "sandbox" else None,
                                      now=self._now(), notes=notes, routes=self._routes(), reasons=reasons) + tail
        if listing:
            from hass.skills import intake_simple
            if shot is not None and not shot.get("ok"):
                shots = []  # failed semantic checks are not a live-look card
            product = next((r["after"] for r in reversed(draft["records"]) if r.get("collection") == "products" and r.get("after")), {})
            # Public copy comes from the frozen draft, not the unsanitized input slots.
            listing = {**listing, "name": product.get("name", listing.get("name")),
                       "maker": product.get("brand", listing.get("maker")),
                       "description": product.get("description", listing.get("description"))}
            picture = self._listing_picture(draft, product) if not shots else None
            if not shots and picture:
                shots = [picture]
                head = "I couldn't render the website card. The product picture is attached; the text below is the listing."
                tail = ""
            can_approve = not reasons and bool(shots)
            text = (head + "\n" if head else "") + intake_simple.preview(listing, row["code"] if can_approve else None)
            text += self._listing_public_notes(listing, product)
            if shot and shot.get("ok") and shot.get("cardText"):
                text += "\nAll website card text:\n" + q(shot["cardText"])
            if reasons:
                text += "\n" + live_policy.refusal(reasons)
            elif can_approve:
                text += "\nNothing changes until your yes."
            else:
                text += "\nI couldn't attach a picture. Please send the photo again before confirming."
            text += tail
        if self._paused(): text += "\n" + PAUSED_LINE
        self._reply(text, shots, long_ok=True)
        if listing:
            self.db.execute(self.LISTING_PREVIEW)
            outbox_id = self.db.execute("SELECT MAX(id) FROM outbox").fetchone()[0] if shots else None
            self.db.execute("INSERT OR REPLACE INTO listing_preview(row_id, draft_hash, outbox_id) VALUES (?, ?, ?)",
                            (row["row_id"], draft["draft_hash"], outbox_id))

    LISTING_PREVIEW = ("CREATE TABLE IF NOT EXISTS listing_preview (row_id INTEGER PRIMARY KEY,"
                       " draft_hash TEXT NOT NULL, outbox_id INTEGER)")

    def _listing_picture(self, draft, product):
        """Attach only the product pixels bound into this frozen draft, never reselect the original."""
        image = product.get("image")
        digest = draft.get("assets", {}).get(image)
        if not isinstance(digest, str): return None
        try:
            rendered = self.editor.render_draft(draft["change_id"])
            data = rendered.get("assets", {}).get("storefront-mockup/" + image)
            if rendered.get("result") != "ok" or data is None or "sha256:" + hashlib.sha256(data).hexdigest() != digest:
                return None
            folder = self.sdir / "screenshots"
            media._private_dir(folder)
            path = folder / (digest[7:] + Path(image).suffix)
            have = media._existing(path)
            if have is None: media._write_new(path, data)
            elif have != data: return None
            return str(path)
        except (OSError, KeyError, media.Refused, editor_mod.UnsafeState):
            return None

    def _listing_public_notes(self, listing, product):
        """Include fixed/generated card text and any expandable maker story, not just slots."""
        maker = self._makers().get(product.get("producerKey")) or {}
        source = ("From " + product["supplier"] if product.get("supplier") else
                  "Based in " + maker["place"] if maker.get("place") else "Ask us about the source in store.")
        lines = ["Website description: " + q(product.get("description") or ""),
                 "Source line: " + q(source),
                 "Picture description: " + q(product.get("imageAlt") or product.get("name") or "")]
        if product.get("addedOn"): lines.append("Badge: New (for the first two weeks).")
        if maker.get("story"): lines.append("Meet the maker: " + q(maker["story"]))
        if maker.get("url"): lines.append("Maker website: " + q(maker["url"]))
        got = listing.get("intake") or {}
        if got.get('generated_picture'):
            lines.append('Picture: generated illustration from your details.')
        if got.get("dropped_claims"):
            lines.append("Dropped from the listing: " + q("; ".join(got["dropped_claims"])))
        sha, root = listing.get("photo"), self.settings.get("mediaRoot")
        if sha and root and not got.get('generated_picture'):
            try:
                decision = photo_polish.decision(root, sha) if photo_polish.enabled(self.settings) else None
                if photo_polish.enabled(self.settings):
                    if decision and decision.get("use") == "polished" and photo_polish.polished(root, sha) is not None:
                        lines.append("Picture: styled from your photo.")
                    else:
                        lines.append("Picture: your photo (styled picture failed: " + photo_polish.plain_reason((decision or {}).get("code")) + ")")
                else:
                    lines.append("Picture: your photo.")
            except (OSError, media.Refused, editor_mod.UnsafeState):
                lines.append("Picture: your photo (styled picture failed: image tool unavailable)")
        return "\n" + "\n".join(lines)

    PREVIEW_RETRY = ("CREATE TABLE IF NOT EXISTS preview_retry (row_id INTEGER PRIMARY KEY, change_id TEXT NOT NULL, chat TEXT NOT NULL,"
                     " due_at TEXT NOT NULL)")

    def _queue_preview_retry(self, row):
        """HASS-CHAT-1: one later try at the picture for this proposal (a second failure of the same row is not queued again)."""
        self.db.execute(self.PREVIEW_RETRY)
        due = _iso(self._now() + timedelta(seconds=PREVIEW_RETRY_SECONDS))
        self.db.execute("INSERT OR IGNORE INTO preview_retry(row_id, change_id, chat, due_at) VALUES (?, ?, ?, ?)",
                        (row["row_id"], row["change_id"], self._chat(), due))

    def retry_previews(self) -> int:
        """HASS-CHAT-1: draw the pictures that failed at least PREVIEW_RETRY_SECONDS ago, once each, and send them (or say once
        that it still failed). A proposal that is no longer waiting gets nothing. The slow capture runs outside any transaction;
        each row is taken off the list before its try, so a crash never tries it twice. Returns the number of rows taken."""
        if self.previewer is None or not self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'preview_retry'").fetchone(): return 0
        now, taken = self._now(), 0
        for due in self.db.execute("SELECT * FROM preview_retry ORDER BY row_id").fetchall():
            if datetime.fromisoformat(due["due_at"]) > now: continue
            with self._tx():
                if not self.db.execute("DELETE FROM preview_retry WHERE row_id = ?", (due["row_id"],)).rowcount: continue
            taken += 1
            row = self._row(due["row_id"])
            if row is None or row["state"] != "proposed" or row["change_id"] != due["change_id"] or self._expiry(row) <= now: continue
            req = self.requests.get(due["chat"], now) if self.requests else None
            if req and req.get("draft_code") == row["code"] and req["slots"].get("intake", {}).get("simple"):
                continue  # discard a listing retry queued by an older worker version
            draft = self.editor.show(row["change_id"]).get("draft")
            shot = self._capture(draft) if isinstance(draft, dict) else {"ok": False, "png": None}
            with self._tx(), self._answer_to(due["chat"]):
                what = q(row["summary"])
                allowed = not (self._live_reasons(draft) if self.settings.get("liveSite") else [])
                confirm = f" To go ahead, reply {q('yes ' + row['code'])}." if allowed else ""
                if shot.get("png") and shot.get("ok"):
                    self._reply(PREVIEW_LATER.format(what=what) + confirm, [shot["png"]])
                else:
                    self._problem("error", "preview-failed", excerpt=preview_mod.failure_kind(shot.get("error")))
                    self._reply(PREVIEW_STILL_FAILED.format(what=what) + confirm)
        return taken

    def _record(self, msg, disposition, owner=True):
        self.db.execute("INSERT INTO messages(provider_id, disposition, received_at) VALUES (?, ?, ?)",
                        (msg.provider_id, disposition, msg.received_at if owner else None))
        if owner: self.db.execute("INSERT OR IGNORE INTO message_chats(provider_id, chat) VALUES (?, ?)", (msg.provider_id, msg.chat))

    def _propose(self, draft, sender, now, row=None, like=None, undo_of=None):
        """Insert a proposed draft (or fill a needs-details row) bound to the A2 hash, base and expiry. AVB-10: `like` is the
        draft this one re-writes (same request, same audit action); `undo_of` the audit action an undo takes back."""
        expires = _iso(now + timedelta(seconds=self.settings["approvalTtlSeconds"]))
        fields = dict(change_id=draft["change_id"], draft_hash=draft["draft_hash"], base=draft["base"],
                      ops_json=json.dumps(draft["ops"], sort_keys=True), summary=_summary(draft), expires_at=expires,
                      proposed_at=_iso(now), missing_json=None)  # AVB-03: the proposal instant itself; a filled question has nothing missing
        if row is not None:
            if row["state"] == "proposed" and getattr(self, "_intake_listing", None):
                # A preview edit refreshes the hash/base/expiry atomically under the
                # same owner code. It is not an approval or a lifecycle transition.
                self.db.execute("UPDATE drafts SET " + ", ".join(k + " = ?" for k in fields) + " WHERE row_id = ? AND state = 'proposed'",
                                (*fields.values(), row["row_id"]))
            else:
                self._move(row, "proposed", **fields)
            new = self._row(row["row_id"])
        else:
            cur = self.db.execute(
                "INSERT INTO drafts(change_id, code, state, draft_hash, base, ops_json, summary, sender, chat, created_at,"
                " expires_at, proposed_at) VALUES (?, ?, 'proposed', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (fields["change_id"], self._code(draft["draft_hash"][7:]), fields["draft_hash"], fields["base"],
                 fields["ops_json"], fields["summary"], sender, self._chat(), _iso(now), expires,
                 fields["proposed_at"]))
            new = self._row(cur.lastrowid)
        try: self._audit_link(new, like, undo_of)
        except Exception: pass  # noqa: BLE001,E701 - AVB-10: the link is ids only; a draft is never lost for it
        self._audit("drafted", new, records=draft.get("records"))
        return new

    # -- message handling ----------------------------------------------------------------------------------------
    _answering = None  # AV0022-10 (H16): received_at of the message handle() is running; replies are tagged with it
    _till = None

    @property
    def till(self):
        return self._till

    @till.setter
    def till(self, desk):
        self._till = desk  # engine attachment is still separately gated; read-only desks never gain one here
        till_approvals.recover(self)
    _forwarded = None  # HASS-SEC-2 (L5): when the message reached the inbox (inbox.Inbox.forwarded_at); None when not known

    def handle(self, msg: Inbound, last_try=False, apply=True, forwarded_at=None) -> str:
        self._answering, self._forwarded = msg.received_at, forwarded_at
        self._to = msg.chat if self._is_owner(msg) else None
        self._asker = sender_key(msg.sender)
        self.outbox.msg_id, self.outbox.emoji_ok = msg.provider_id, voice.has_emoji(msg.text)
        try:
            with transcript.Capture(self, msg) as record:
                record.result = self._handle_message(msg, last_try, apply)
                return record.result
        finally:
            self._answering, self._forwarded, self._to, self._asker, self.outbox.msg_id, self.outbox.emoji_ok = None, None, None, None, None, False
            self._pages = {}

    _pages: dict = {}  # HASS-SEC-3 (M2): the maker websites read for the message being handled, BEFORE its write transaction
    early_flush = None  # HASS-INTAKE-2: fn() that sends the queued replies now (host.Worker sets it); None = they go out after the message
    answer_reader = None  # HASS-INTAKE-2: an answer_reader.AnswerReader for an intake answer fixed code cannot read; None = ask again

    def _intake_receipt(self, msg) -> None:
        """HASS-INTAKE-2 (G, 2026-11-16): the moment the owner's bare photo arrives, with the interview on, his first question goes out
        from fixed words: no model call, no preview, and BEFORE the photo is fetched, checked or stored (the slow part). The photo
        is then handled as always; a photo that cannot be fetched is tried again without a second question. Nothing else is
        decided here: the same checks as the photo path (owner, one photo, no caption, skills on, writer free, nothing else open)
        keep an ordinary photo exactly as it was."""
        try:
            if (self.dispatch is None or self.photos is None or self.settings.get("itemIntake") is not True or msg.attachments != 1
                    or msg.from_me or msg.kind != "new" or self.skills_mode == dispatch_mod.DEFAULT_MODE
                    or msg.chat not in self._owner_chats or not self._is_owner(msg)
                    or msg.text.replace("\ufffc", "").strip() or not self.dispatch.intake_ready()):
                return
            now = self._now()
            if (self.db.execute("SELECT 1 FROM messages WHERE provider_id = ?", (msg.provider_id,)).fetchone()
                    or item_intake.acknowledged(self.db, msg.provider_id) or self.requests.get(msg.chat, now) is not None
                    or self._writer_busy(now) is not None):
                return
            with self._tx():
                if item_intake.acknowledge(self.db, msg.provider_id, now):
                    self._reply(item_intake.START)
        except Exception:  # noqa: BLE001 - a quick first question is a convenience: the photo path asks it as before
            return
        if self.early_flush is not None:
            try: self.early_flush()
            except Exception: pass  # noqa: BLE001,S110 - cycle() flushes again and raises as before

    def _read_sites(self, msg) -> dict:
        """HASS-SEC-3 (M2): a maker's web address the owner typed (in this text or earlier in his open request) is read HERE,
        before BEGIN IMMEDIATE, the whole read within maker_site.DEADLINE; inside the transaction the item.add plan only sees
        this result (Dispatcher._ctx), so a slow site never holds the write lock and never hangs the reply. Only for the
        owner's own new text with skills on; anything that goes wrong is the plain "could not read their site" reply later."""
        if self.dispatch is None or msg.from_me or msg.kind != "new" or not self._is_owner(msg): return {}
        if self.npp is not None and (msg.attachments or self.npp.active(msg.chat, sender_key(msg.sender))): return {}
        text = (msg.text or "").replace("\ufffc", "")
        if not text.strip() or len(text) > MAX_OWNER_TEXT: return {}
        from hass import maker_site  # lazy: only a text that names a website needs it
        try:
            if self.db.execute("SELECT 1 FROM messages WHERE provider_id = ?", (msg.provider_id,)).fetchone(): return {}
            req = self.requests.get(msg.chat, self._now())
            texts = [*(req["texts"] if req else []), text]
        except (sqlite3.Error, KeyError, TypeError):
            texts = [text]
        if not maker_site.addresses_in(texts): return {}
        return maker_site.prefetch(texts, today=shop_today(self._now()))

    def _forwarded_late(self, msg) -> bool:
        """HASS-SEC-2 (L5): a yes is judged at the time it was sent (AV0022-06), so one the Mac held back and forwarded long
        after must not approve anything: it counts only when it reached the inbox within the approval time plus LATE_FORWARD_S of
        its send time. A message whose forwarding time is not known (called directly, not through the inbox) is not late."""
        try:
            sent, forwarded = datetime.fromisoformat(msg.received_at), self._forwarded
            if isinstance(forwarded, str): forwarded = datetime.fromisoformat(forwarded)
            return forwarded is not None and (forwarded - sent).total_seconds() > self.settings["approvalTtlSeconds"] + LATE_FORWARD_S
        except (TypeError, ValueError):
            return False

    def _read_intake(self, msg):
        """Bounded owner-text read before the write lock, never on photo output or approval commands."""
        photo = msg.attachments > 0
        empty = {"photo_fields": None} if photo else {}
        if (not self.dispatch or not getattr(self.dispatch, "simple_intake", lambda: False)() or not self.answer_reader
                or msg.from_me or msg.kind != "new" or not self._is_owner(msg)
                or not msg.text or len(msg.text) > MAX_OWNER_TEXT): return empty
        if re.match(r"\s*(?:(?:add|description)\s*:|(?:remove|delete|yes|no|cancel|stop)\b)", msg.text, re.I): return empty
        if not re.search(r"\b(?:bought|paid|cost|sell|selling|price|retail|have|stock|qty|quantity|purchased|dollars?|items?)\b|\$", msg.text, re.I): return empty
        if self.db.execute("SELECT 1 FROM messages WHERE provider_id = ?", (msg.provider_id,)).fetchone(): return empty
        req = self.requests.get(msg.chat, self._now())
        if req and not self.dispatch.simple_intake(req): return empty
        if not photo or msg.attachments == 1:
            public, facts = item_intake.caption_answers(msg.text.replace("\ufffc", ""), empty)
            if photo:
                if not public and "price" in facts and "cost" in facts: return empty
            elif {"price", "cost", "qty"} & facts.keys() and not item_intake.unresolved_finance(public):
                return empty  # only skip the local reader when no finance remains unresolved
        self.stage("finance-start", msg.provider_id)
        try:
            fields = self.answer_reader.fields(msg.text)
            return {"photo_fields": fields} if photo else fields
        except Exception: return empty  # a failed reader leaves the deterministic parser, never an inferred value
        finally: self.stage("finance-end", msg.provider_id)

    def _handle_message(self, msg: Inbound, last_try=False, apply=True) -> str:
        """Process one inbound message; returns its disposition. Replies are only enqueued (see flush).
        apply=False (SHOP-3 fixture receiver): an owner approval is rolled back before anything is written (no approval
        row, the draft stays proposed) and the message is recorded as `approval-held`; editor.apply is never called."""
        if hasattr(self.editor, "sync_settings"): self.editor.sync_settings(self.settings)
        self._label_jobs = []  # AV2152-04: one job per new photo draft, in the order sent; reset on every message
        self._polish_jobs = []  # HASS-IMAGE-1: stored photos to clean up in the background, after the commit
        if self.npp is not None:
            self.npp.refresh_receipts()  # receipt ordering is filtered at inbox acceptance, not at this pickup
        self._intake_fields = self._read_intake(msg)
        self._pages = self._read_sites(msg)  # HASS-SEC-3 (M2): any website read happens now, never inside the transaction
        # Intake waits for the label read, then sends one complete preview, not an early interview question.
        self._till_job = None  # HASS-CLOVER-4: the till code an owner's yes approved; the till is called only after this message is saved
        try:
            with self._tx():
                disposition, approved = self._handle(msg, last_try)
                self._expire_lapsed()  # AV1104-06: whatever _request left unmoved (it never reached the interpreter) is moved now
                if approved is not None and not apply: raise _Held(approved["code"])
                till_approvals.save(self, msg, self._till_job, apply)
        except _Held as held:
            with self._tx():
                self._reply(HELD_REPLY.format(code=held.code))
                self._record(msg, "approval-held")
            return "approval-held"
        till_approvals.recover(self)  # also reconciles a redelivered provider id
        for job in self._label_jobs:  # AV1537-15: after the commit, never holding the lock; AV2152-04: a failed one never stops the next
            try:
                final = self._read_label(*job)
                if final is not None:
                    disposition = final
                    with self._tx(): self.db.execute("UPDATE messages SET disposition = ? WHERE provider_id = ?", (final, msg.provider_id))
            except Exception: continue  # noqa: BLE001 - no label is today's reply exactly
        for sha in self._polish_jobs:  # HASS-IMAGE-1: a daemon thread each; never waited for, never a reply
            photo_polish.start(self.settings["mediaRoot"], sha, log=self.log, transport=self.polish_transport)
        if approved is None: return disposition
        out = self.editor.apply(approved["change_id"], approved["draft_hash"], chat=approved["chat"]) \
            if getattr(self.editor, "routes_chat", False) else self.editor.apply(approved["change_id"], approved["draft_hash"])
        with self._tx():
            self._outcome(self._row(approved["row_id"]), out, self._now())
        self._verify_pending()
        return disposition

    def _till_apply(self, msg, job, apply) -> None:
        """HASS-CLOVER-4: an owner's till yes, after its message is saved (never inside the write transaction). The till part first; only
        when it is read back does a website word riding on it go through the normal draft, approval, editor.apply and outcome.
        FIX-1: the website must still show the word the draft (or undo) was made against, or nothing at all changes (a newer word
        wins); ``job`` = (code, True) after the owner's yes to the shelf question, whose check then goes in the same site change."""
        code, shelf = job if isinstance(job, tuple) else (job, False)
        ops, base = self.till.bundle(code, self._asker, msg.chat) if apply else ((), None)
        site = lambda: editor_mod._load(str(self.sdir))[2]  # noqa: E731
        if ops and self.till.site_moved(base, site):
            self.till.drop(code, self._asker, msg.chat)
            with self._tx():
                self._reply(self.till.SITE_MOVED)
                till_approvals.finish(self, msg)
            return
        text, ops = (HELD_REPLY, ()) if not apply else self.till.approve(code, sender=self._asker, chat=msg.chat)
        with self._tx():
            self._reply(text, long_ok=True)
            till_approvals.finish(self, msg)
        if not ops: return
        try:
            if self.till.site_moved(base, site): raise ValueError("site")  # changed while the till was written: keep the newer word
            out, now = self.editor.prepare([*([{"op": "store.confirm_selection", "args": {}}] if shelf else []), *ops]), self._now()
            if out.get("result") != "ok" or self.till.site_moved(base, site, out["draft"]): raise ValueError("site")  # FIX-2: the draft's own base
            with self._tx():
                row = self._propose(out["draft"], msg.sender, now)
                self.db.execute("INSERT INTO approvals(sender, chat, provider_id, change_id, draft_hash, base, expires_at, approved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                (msg.sender, msg.chat, msg.provider_id, row["change_id"], row["draft_hash"], row["base"], row["expires_at"], _iso(now)))
                self._move(row, "approved")
                self._audit("approved", row, approval="A1", approved_by=self._audit_role(msg.chat))
            res = self.editor.apply(row["change_id"], row["draft_hash"], **({"chat": msg.chat} if getattr(self.editor, "routes_chat", False) else {}))
            done = res.get("result") in ("applied", "already-applied")
            with self._tx():  # FIX-2: stale or any other result: the site is left as it is, never re-prepared
                if done: self._outcome(self._row(row["row_id"]), res, now)
                else: self._audit("failed", row, "stale" if res.get("result") == "stale" else "failed"); self._move(row, "failed", reason=_reason(res))  # noqa: E701,E702
            if not done: raise ValueError("site")
        except Exception:  # noqa: BLE001 - the till part stands; the owner is told the website is not done
            with self._tx(): self._reply(self.till.SITE_NOT_YET)
        self._verify_pending()

    def _is_owner(self, msg) -> bool:
        """The owner chat with an owner sender, or (gIsOwner) G's own one-to-one chat with a G sender. Nobody else."""
        key, st = sender_key(msg.sender), self.settings
        if msg.chat in self._owner_chats: return key in st.get("chatKeys", {}).get(msg.chat, st["ownerKeys"])  # HASS-OWNERS-2: that chat's own owner
        return bool(st.get("gOwner")) and msg.chat == st.get("gChat") and key in st.get("gKeys", ())

    def _handle(self, msg, last_try=False):
        if self.db.execute("SELECT 1 FROM messages WHERE provider_id = ?", (msg.provider_id,)).fetchone():
            return "duplicate", None
        if (g := self._for_g(msg)) is not None: return g, None
        owner = self._is_owner(msg)
        if owner and not msg.from_me and msg.kind in ("edited", "reaction"):  # AV1737-03: never read, never approves
            self._reply(NOT_READ_REPLY)
            self._record(msg, "not-read")
            return "not-read", None
        ignored = "echo" if msg.from_me else "edited-ignored" if msg.kind != "new" else None if owner else "ignored"
        if ignored:
            self._record(msg, ignored, owner=False)
            return ignored, None
        if msg.attachments > 0 and self.photos is None:  # H12 part 1: the caption is never interpreted
            self._reply(ATTACHMENT_REPLY)
            self._record(msg, "attachment-unsupported")
            return "attachment-unsupported", None
        now, command = self._now(), None if msg.attachments > 0 else read_command(msg.text, listing_names=True)
        if self.npp is not None and msg.attachments <= 0 and (result := self._npp_turn(self.npp, msg, now, command)) is not None:
            return result
        if msg.text.strip() == "?" and self.dispatch is not None:
            req = self.requests.get(msg.chat, now)
            if req and self.dispatch.simple_intake(req): command = None
        if command and command[0] == "listing" and command[1] and len(command[1].split()) >= 2 and not self._listing_names_something(command[1]):
            command = None  # A sentence is not a listing request unless it names something in the catalog.
        if command and command[0] == "post" and len(command[1].split()) >= 2 and not self._post_names_something(command[1]):
            command = None  # HASS-VOICE-1: "post a sale on social media" is a sentence for the interpreter, not a product or hike name
        if command is None and msg.attachments <= 0 and (near := near_control(msg.text)) is not None:  # AV2007-05: guidance only, no model, nothing paused or resumed
            self._reply(NEAR_STOP_REPLY if near == "stop" else NEAR_RESUME_REPLY)
            self._record(msg, "near-control")
            return "near-control", None
        if not (command and command[0] == "held"): self._close_asks(now)  # AV2137-07: listing held products sweeps nothing
        # HASS-HIKE-FLOW-1: an open request older than RECENT_MINUTES is forgotten (FW-3: and a closed one older than 24 h)
        # AV0022-06 (H16): a yes/no is judged at the time it was sent, so a reply queued while the service was down counts
        phone = None if msg.attachments > 0 else parse_phone(msg.text)  # AV1352-04
        coded = None if phone is None or phone[2] or phone[0] is None else phone[:2]  # decorated answer without a ?
        bulk = None if msg.attachments > 0 else parse_keyword(msg.text)  # AV1052-08: no/cancel all, yes/approve all (never an attachment's caption)
        bulk = bulk[0] if bulk is not None and bulk[1] == "all" else None
        cutoff = _answered_at(msg, now) if msg.attachments <= 0 and bulk is None and (parse_keyword(msg.text) or coded) is not None else now
        late = cutoff != now and self._forwarded_late(msg)  # HASS-SEC-2 (L5): forwarded long after it was sent
        if late: cutoff = now  # ... judged when it arrived, never at its send time
        expired = [r for r in self._drafts("state IN ('proposed', 'needs-details')") if self._expiry(r) <= cutoff]
        if command and (command[0] in ("status", "help", "find", "show", "report", "post", "margin", "hidden", "listing", "photos", "backlog", "shelf", "look", "costs", "held")
                        or command[0] == "history" and command[1] is not None): expired = []  # H17: read-only; AV2152-02: history <words>, not bare history
        if bulk is not None and command is None:  # AV1052-08: before the interpreter, till and memory; works paused and at the daily cap
            if bulk == "reject": self._expire(expired)
            disposition = self._bulk(now, bulk)
            self._record(msg, disposition)
            return disposition, None
        req = self.requests.get(msg.chat, now) if self.dispatch else None
        intake_answer = bool(self.dispatch and getattr(self.dispatch, "simple_intake", lambda req: False)(req) and (
            self.dispatch.takes_answer(msg.text, now) if req else item_intake.caption_answers(msg.text)[1]))
        memory = None if command or msg.attachments > 0 or intake_answer else read_memory(msg.text)
        first = None if msg.attachments > 0 or self.till is None or intake_answer else self.till.first(msg.text, self._asker, msg.chat)  # HASS-CLOVER-4: till code words, before commands
        if first: command = memory = None
        till = first or (None if command or memory or msg.attachments > 0 or self.till is None or intake_answer else self.till.parse(msg.text))  # HASS-CLOVER-2
        if memory and memory[0] == "memory" or till: expired = []  # AV0222-05: the bare `memory` listing is read-only; writes still sweep
        self._lapsed = ()
        if (expired and not (command or memory or till or first or msg.attachments > 0 or intake_answer) and phone is None and coded is None
                and parse_keyword(msg.text) is None and parse_unknown_code(msg.text) is None and parse_near(msg.text) is None
                and classify_social(msg.text) is None):
            self._lapsed, expired = expired, []  # AV1104-06: only _request follows: it moves them once it knows the reply is not a lookup
        self._expire(expired)
        if command or msg.attachments > 0:  # NB-AV-09: a photo caption is never a command, keyword or approval
            disposition = self._photo(msg, now, last_try) if msg.attachments > 0 else self._command(msg, now, *command)
            self._record(msg, disposition)
            return disposition, None
        if memory:  # not a site change: never the interpreter or editor, and pause does not apply
            disposition = self._memory(msg, *memory)
            self._record(msg, disposition)
            return disposition, None
        if till:  # HASS-CLOVER-2/4: a till read, or a till change by fixed words: never the interpreter or a model; a yes runs after the commit
            if till[0] == "yes" and not (paused := self._paused()):
                if (ops := self.till.bundle(till[1], self._asker, msg.chat)[0]) and (out := self.editor.prepare(list(ops))).get("result") == "refused" \
                        and out.get("reason") == catalog.NOT_CHECKED_TODAY:  # FIX-1 (CLOVER.md 5): the editor's own shelf-check rule, as for site changes
                    disposition = self._ask_shelf(msg, now, {"ops": [], "till": till[1]}, [])  # the shelf question first; nothing waits half-done
                    self._record(msg, disposition)
                    return disposition, None
                self._till_job = till[1]
            else: self._reply(self.till.answer(till, now, sender=self._asker, chat=msg.chat, worktree=lambda: editor_mod._load(str(self.sdir))[2]), long_ok=True)
            disposition = "paused" if till[0] == "yes" and paused else {"write": "till-write-refused", "till": "till-draft", "yes": "till-approved", "no": "till-cancelled", "undo": "till-undo"}.get(till[0], "till-read")
            self._record(msg, disposition)
            return disposition, None
        if msg.attachments <= 0 and (unknown := parse_unknown_code(msg.text)) is not None and not any(
                unknown.startswith(r["code"]) for r in self._drafts("state = 'proposed'") if self._mine(r)):  # AV2007-13: refused, nothing mutated, the open question stays (a waiting code with a stray character still goes to the reader)
            held = self._open_question(now)
            self._reply(self._no_target(unknown, [], []), long_ok=True)
            self._record(msg, "no-target")
            if held is not None: self._hold(msg, held)
            return "no-target", None
        if msg.attachments <= 0 and self.skills_mode != dispatch_mod.DEFAULT_MODE and self.dispatch.takes_answer(msg.text, now):
            disposition = self._request(msg, now)  # HIKE-LOOKUP-2: a bare yes / no / number that answers the map's "Did you mean ...?" is that answer, never an approval
            self._record(msg, disposition)
            return disposition, None
        keyword = parse_keyword(msg.text) or coded
        social = classify_social(msg.text) if keyword is None and parse_near(msg.text) is None else None  # AV0007-07
        if social == "social":  # thanks, a greeting or emoji only: no interpreter call, draft or usage count
            self._reply(self._waiting_note(now) or SOCIAL_REPLY, long_ok=True)  # AV2007-02: a thanks never reads as the end of a change still waiting
            self._record(msg, "social")
            return "social", None
        if keyword is None and (near := "" if social == "near" else parse_near(msg.text)) is not None:  # AV2022-07: no approval, call or count
            codes = [r["code"] for r in self._drafts("state = 'proposed'")
                     if self._mine(r) and self._expiry(r) > now and near in ("", r["code"])]
            self._reply(f"I haven't changed anything yet. To go ahead with {q(self._by_code(codes[0], ('proposed',))['summary'])}, reply {q('yes ' + codes[0])}." if len(codes) == 1 else
                        "I haven't changed anything yet. Which one do you want?\n" + self._choices(codes) if codes else NOTHING, long_ok=True)
            self._record(msg, "near-approval")
            return "near-approval", None
        if keyword is None and phone is not None:  # AV1352-04: a question or a lone code is never an answer
            live = [r["code"] for r in self._drafts("state = 'proposed'") if self._mine(r) and self._expiry(r) > now]
            if phone[0] is not None or phone[1] in live:
                one = phone[1] if phone[1] in live else live[0] if len(live) == 1 else None
                self._reply(f"I haven't changed anything yet. To go ahead, reply {q('yes ' + one)}, or {q('no ' + one)} to cancel." if one else
                            "I haven't changed anything yet. Which one do you mean?\n" + self._choices(live) if live else NOTHING, long_ok=True)
                self._record(msg, "near-approval")
                return "near-approval", None
        if keyword is None and (guess := command_typo(msg.text)):  # AV1052-09 (H17): a guess only: nothing run, no interpreter call or count; works paused and at the cap
            names = " or ".join(guess)
            self._reply(f"Did you mean {names}? Send {names}.")
            self._record(msg, "command-typo")
            return "command-typo", None
        if keyword is None:
            disposition = self._request(msg, now)
            self._record(msg, disposition)
            return disposition, None
        verb, code = keyword
        if late and verb == "approve":  # HASS-SEC-2 (L5): a yes that reached me long after it was sent approves nothing
            self._reply(LATE_YES_REPLY)
            self._record(msg, "no-target")
            return "no-target", None
        if code is None and (ask := self._shelf_ask(now)) is not None:  # HASS-SHELFCHECK-FLOW-1: a bare yes/no answers our question
            disposition = self._shelf_answer(msg, now, verb, ask)  # (never a waiting draft's approval or cancel)
            self._record(msg, disposition)
            return disposition, None
        if verb == "reject" and code is None and (open_q := self._open_question(now)) is not None:  # AV2007-13: a bare no drops the open question, first
            if open_q["legacy"]: self._close_asks()
            else: self.requests.mark(open_q["request_id"], "cancelled", now)
            self._reply(QUESTION_DROPPED)
            self._record(msg, "cancelled")
            return "cancelled", None
        if verb == "approve" and code is None and self.settings.get("approvalNeedsCode"):
            self._reply("To put a change on the website, reply yes and its code, like " + q("yes a1b2") + ".")
            self._record(msg, "no-target")
            return "no-target", None
        # AV1537-02: no/cancel also closes an open (unexpired) question; yes only ever targets a proposal.
        states = "('proposed', 'needs-details')" if verb == "reject" else "('proposed')"
        targets = [r for r in self._drafts(f"state IN {states}") if self._mine(r) and (code is None or r["code"] == code)]
        if verb == "reject" and (code is None or targets): self._close_asks()  # HASS-HIKE-FLOW-1: no/cancel also drops the open request (the reply is unchanged); AV2007-13: an unknown code never does
        asks = [] if verb != "approve" or targets else [self._by_code(code, ("needs-details",))] if code else \
            [r for r in self._drafts("state = 'needs-details'") if self._mine(r) and self._expiry(r) > cutoff]  # AV1737-05: bare yes
        if asks := [a for a in asks if a is not None]:  # a waiting question is never approved; it is repeated
            self._reply("\n".join("I still need an answer from you first. " + q(a["summary"]) for a in asks),
                        long_ok=True)
            self._record(msg, "no-target")
            return "no-target", None
        if len(targets) != 1:
            held = self._open_question(now) if code and not targets else None  # AV2007-13: a code that matches nothing leaves the question usable
            self._reply(self._no_target(code, targets, expired))
            self._record(msg, "no-target")
            if held is not None: self._hold(msg, held)
            return "no-target", None
        target = targets[0]
        if verb == "reject":
            self._move(target, "rejected", reason="owner")
            if target["state"] == "proposed": self._audit("refused", target, "said-no")  # AVB-10
            self._reply("Okay, I've cancelled that. Nothing changed.")
            self._problem("corrected", "said-no")
            self._record(msg, "rejected")
            return "rejected", None
        if self._paused():  # H17: no approval row, no state move; the draft keeps its expiry
            self._reply(f"Changes are paused, so I haven't saved that. Say {q('resume changes')}, then reply {q('yes ' + target['code'])}.")
            self._record(msg, "paused")
            return "paused", None
        if cutoff != now and cutoff < self._proposed_at(target):  # AVB-03 (H05): a yes sent before the draft existed
            self._reply(f"Your yes came before I had written that change up, so I haven't saved it. If you still want it, reply {q('yes ' + target['code'])}.")
            self._record(msg, "no-target")
            return "no-target", None
        if code is None and target["reason"] == SHELF_CODE_REASON:  # AV2007-15: a plain shelf-check sentence is saved only by its own code
            self._reply(f"Reply {q('yes ' + target['code'])} to save the shelf check.")
            self._record(msg, "no-target")
            return "no-target", None
        if code is None and self._named(target):  # a delayed bare `yes` must not approve a repeat of a closed draft, or an `again` draft
            again = str(target["reason"] or "").startswith("again:")
            self._reply((f"That change was written up again from an expired one, so I want to be sure. Reply {q('yes ' + target['code'])} if you still want it." if again else
                         f"That is the same change that {self._earlier_outcome(target)} earlier, so I want to be sure. Reply {q('yes ' + target['code'])} if you still want it."))
            self._record(msg, "no-target")
            return "no-target", None
        if hasattr(self.editor, "check_environment") and (problem := self.editor.check_environment(target["change_id"])):
            self._outcome(target, problem, now)
            self._record(msg, "env-changed")
            return "env-changed", None
        if self.settings.get("liveSite") and (reasons := self._live_reasons(self.editor.show(target["change_id"]).get("draft"))):
            self._save_private(target, reasons)  # HASS-LIVE-PLAN-1: refused for the website, kept for Graham, never lost
            self._audit("refused", target, "policy")  # AVB-10: the draft stays waiting; the live gate said no
            self._reply(live_policy.refusal(reasons, understood=q(target["summary"])))
            self._record(msg, "no-target")
            return "no-target", None
        self.db.execute(self.LISTING_PREVIEW)
        shown = self.db.execute("SELECT * FROM listing_preview WHERE row_id = ?", (target["row_id"],)).fetchone()
        if shown is not None and (shown["draft_hash"] != target["draft_hash"] or not self.db.execute(
                "SELECT 1 FROM outbox WHERE id = ? AND chat = ? AND sent_at IS NOT NULL AND attachments != '[]'",
                (shown["outbox_id"], self._chat())).fetchone()):
            self._reply("I haven't sent the picture for this version yet. Please wait for the picture before confirming.")
            self._record(msg, "no-target")
            return "no-target", None
        self.db.execute(
            "INSERT INTO approvals(sender, chat, provider_id, change_id, draft_hash, base, expires_at, approved_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (msg.sender, msg.chat, msg.provider_id, target["change_id"],
                                                 target["draft_hash"], target["base"], target["expires_at"], _iso(now)))
        self._move(target, "approved")
        self._audit("approved", target, approval="A1", approved_by=self._audit_role(msg.chat))  # AVB-10: msg is the yes
        self.requests.close_drafted(self._chat(), now)  # SKILLS-FW-3: the request that made this draft is finished
        self._record(msg, "approved")
        return "approved", self._row(target["row_id"])

    def _expire(self, rows) -> None:
        for row in rows:
            self._move(row, "expired", expires_at=_iso(self._expiry(row)))
            if row["state"] == "proposed": self._audit("refused", row, "expired")  # AVB-10

    def _bulk(self, now, verb) -> str:
        """AV1052-08 (H05/H17): `no all`, `cancel all` and `cancel everything` close every waiting proposal and question of this
        owner (the unexpired ones, as of now) through the one-draft cancel move; `yes all` and `approve all` approve nothing and
        name the waiting codes. A photo draft's stored photo is never touched. No interpreter, daily count, editor or pause check."""
        live = [r for r in self._drafts("state IN ('proposed', 'needs-details')") if self._mine(r) and self._expiry(r) > now]
        if not live:
            self._reply("Nothing is waiting.")
            return "no-target"
        codes = ", ".join(q(r["code"]) for r in live)  # quoted: a repeat's longer code is not a voice-rule break
        if verb == "approve":  # nothing moves: no approval row, no expiry sweep, even with one draft waiting
            self._reply(f"Nothing was changed. Each draft needs its own yes <code>. Waiting codes: {codes}."  # not "applied": a word the voice rules ban
                        + (" Questions still need details before approval." if any(r["state"] == "needs-details" for r in live) else ""),
                        long_ok=True, ids_ok=True)  # ids_ok: the literal `yes <code>` placeholder
            return "no-target"
        for row in live:  # one transaction: a failed move rolls every row, the reply and the record back together
            self._move(row, "rejected", reason="owner")
            if row["state"] == "proposed": self._audit("refused", row, "said-no")  # AVB-10
        self._close_asks()  # as a single no: the open request goes too
        self._reply(f"Cancelled {codes}; nothing changed.", long_ok=True)
        return "rejected"

    def _npp_turn(self, jobs, msg, now, command):
        text = msg.text.strip()
        accepted = npp_instant(self._forwarded) if self._forwarded is not None else now
        accepted = min(accepted, now) if accepted is not None else None
        active = jobs.active(msg.chat, self._asker)
        if (match := listing_jobs.YES.fullmatch(text)) is not None:
            code, n = match[1].lower(), int(match[2]) if match[2] else None
            job = jobs.one("SELECT * FROM npp_jobs WHERE job_id=? AND sender=? AND chat=?", code, self._asker, msg.chat)
            if job is not None:
                return self._npp_approve(jobs, job, msg, n, accepted, now)
        if active is None:
            return None
        disposition = None
        if command and command[0] == "status":
            jid, state = active["job_id"], active["state"]
            line = f"The listing {jid} is still open."
            if state == "card_out":
                tag = f"{jid}-{active['current_version']}"
                line = f"Card {tag} is waiting for your yes (reply yes {tag}, or tell me what to change)."
            elif state == "asking":
                # Replay the rendered prompt, including any template substitutions.
                prompt = jobs.one("SELECT o.text FROM npp_questions q JOIN outbox o ON o.id=q.asked_outbox_id "
                                  "WHERE q.job_id=? AND q.state='open' AND o.chat=? ORDER BY o.id DESC LIMIT 1",
                                  jid, active["chat"])
                if prompt:
                    line = f"Waiting for your answer: {prompt[0]}"
            elif state in ("working", "editing"):
                line = f"I'm still drawing the card for listing {jid}."
            self._reply(line + "\n" + self._status(now, self._paused()), long_ok=True, ids_ok=True)
            disposition = "status"
        elif (text.casefold() in ("yes", "no") and
              (disposition := jobs.answer(active, msg, text.casefold() == "yes", accepted, now)) is not None):
            pass
        elif (match := listing_jobs.NO.fullmatch(text)) and (match[1] is None or match[1].lower() == active["job_id"]):
            jobs.turn(active["job_id"], msg, "other", accepted or now)
            jobs.close(active, "cancelled", now)
            jobs.reply(active, "Okay, I've cancelled that. Nothing changed.", msg.provider_id)
            disposition = "cancelled"
        elif text.casefold() == "yes":
            self._reply(jobs.replies["guards"]["not_ready"])
            disposition = "no-target"
        elif (jobs.stages is not None and len(text) <= MAX_OWNER_TEXT and not HOSTILE_RE.search(text)
              and (text == "?" and jobs.needs_retry(active) or not command and jobs.stages.takes_turn(text, active["state"]))):
            req = jobs.request(active, accepted or now)
            prior = (req or {}).get("slots", {}).get("intake", {})
            basis = {"item": "each", "pound": "per lb"}.get(prior.get("sold_by")) if prior.get("price_span") else None
            answering_price = jobs.one("SELECT 1 FROM npp_questions WHERE job_id=? AND state='open' AND qid='selling_price'",
                                       active["job_id"]) is not None
            finance, replace_price = self._npp_words(text, basis, answering_price)
            disposition = jobs.input(msg, self._asker, accepted or now, now, finance, replace_price=replace_price)
        if disposition is not None:
            self._record(msg, disposition)
            return disposition, None
        return None

    def _npp_words(self, text, basis=None, answering_price=False, *, photo=False):
        """Parse local provenance; send neither raw finance nor reader-derived prices to the job."""
        from hass.npp import private_numbers

        local = self._intake_fields.get("photo_fields") if photo else self._intake_fields

        # F4 licenses only its exact amount span. Keep offsets in the original turn.
        match = None if photo else intake_simple.PRICE_EDIT.fullmatch(text)
        if match and item_intake._parse_money(match["amount"]) is not None:
            if match["unit"]:
                basis = "per lb" if re.search(r"lb|pound", match["unit"], re.I) else "each"
            result = private_numbers.finance(match["amount"], answer_unit=basis or "each", local_answers=local)
            if result.price_span:
                price = result.selling_price if basis else result.selling_price.split()[0]
                result = replace(result, selling_price=price, price_span=match.span("amount"))
            return result, True
        _, parsed = item_intake.caption_answers(text)
        result = private_numbers.finance(text, answer_unit=basis if not photo and ("price" in parsed or answering_price) else None,
                                         local_answers=local)
        if not result.price_span and not basis and ("price" in parsed or answering_price):
            # Same amount under either hypothetical basis proves only an amount,
            # never a unit. S3 resolves packaged vs. fresh from checked identity.
            each = private_numbers.finance(text, answer_unit="each", local_answers=local)
            pound = private_numbers.finance(text, answer_unit="per lb", local_answers=local)
            if (each.price_span and each.price_span == pound.price_span and pound.selling_price
                    and (each.selling_price or "").split()[0] == pound.selling_price.split()[0]):
                result = replace(each, selling_price=each.selling_price.split()[0])
        price_attempt = result.price_span is not None or bool(re.search(r"\b(?:sell|selling|price|retail)\b", text, re.I))
        return result, price_attempt

    def npp_posted(self, change_id):
        """S13: the one-line `Posted: <item link>` confirmation for a published listing job's change, or None when the change
        is not one (the live release engine then says its ordinary line). It is only asked once the live check has seen the
        change, never at apply."""
        if self.npp is None:
            return None
        job = self.db.execute("SELECT j.job_id FROM npp_jobs j JOIN drafts d ON d.row_id = j.approval_row "
                              "WHERE d.change_id = ? AND j.state = 'published'", (change_id,)).fetchone()
        if job is None:
            return None
        try:
            records = (self.editor.show(change_id).get("change") or {}).get("records") or []
            keys = [r["key"] for r in records if r.get("collection") == "products"]
            return npp_reply.posted(self.npp.replies, keys[0]) if len(keys) == 1 else None
        except (KeyError, TypeError, ValueError):
            return None

    def _npp_approve(self, jobs, job, msg, n, accepted, now):
        failure, version = jobs.select(job, msg, n, accepted, now)
        queued = npp_instant(version["queued_at"]) if version is not None else None
        expires = queued + timedelta(seconds=self.settings["approvalTtlSeconds"]) if queued else now
        if (job["state"] in ("asking", "working", "editing", "card_out", "retake") and not jobs.request(job, now)
                or version is not None and (self._forwarded_late(msg) or now >= expires)):
            jobs.close(job, "expired", now)
            failure = "expired"
        if version is not None and not failure and not self._paused() and self._writer_busy(now) is None:
            draft = self.editor.show(version["change_id"]).get("draft") or {}
            bound = (draft.get("change_id"), draft.get("draft_hash"), draft.get("base"))
            check = getattr(self.editor, "check_environment", None)
            if (bound != tuple(version[k] for k in ("change_id", "draft_hash", "base"))
                    or callable(check) and check(version["change_id"])
                    or self.settings.get("liveSite") and self._live_reasons(draft)):
                failure = "not_ready"
            else:
                row = self._propose(draft, msg.sender, now)
                cur = self.db.execute(
                    "INSERT INTO approvals(sender,chat,provider_id,change_id,draft_hash,base,expires_at,approved_at) VALUES (?,?,?,?,?,?,?,?)",
                    (msg.sender, msg.chat, msg.provider_id, version["change_id"], version["draft_hash"], version["base"],
                     _iso(expires), _iso(now)))
                jobs.approve(job, version, cur.lastrowid, row["row_id"], now)
                self._move(row, "approved")
                self._audit("approved", row, approval="A1", approved_by=self._audit_role(msg.chat))
                self._record(msg, "approved")
                return "approved", self._row(row["row_id"])
        line = (PAUSED_LINE if version is not None and not failure and self._paused() else
                listing_jobs.EXPIRED if failure == "expired" else "That one is already saved." if failure == "already-done" else
                jobs.replies["guards"][failure or "not_ready"])
        jobs.reply(job, line, msg.provider_id)
        self._record(msg, "no-target")
        return "no-target", None

    def _waiting_note(self, now, exclude=None) -> str:
        """AV2007-02: what still waits on this chat (proposed or needing an answer, unexpired), with each one's own `no <code>`;
        "" when nothing waits. It only reads: nothing is approved, dropped or renewed."""
        rows = [r for r in self._drafts("state IN ('proposed', 'needs-details')")
                if self._mine(r) and self._expiry(r) > now and (exclude is None or r["change_id"] != exclude)]
        def line(r):
            what = q(r["summary"] or "that change")
            return (f"{what} is still waiting for your yes" if r["state"] == "proposed" else f"{what} still needs an answer from you")
        if len(rows) == 1:
            return f"{line(rows[0])}. Reply {q('no ' + rows[0]['code'])} to drop it."
        if rows:
            return "These are still waiting:\n" + "\n".join(f"{line(r)}: {q('no ' + r['code'])} drops it." for r in rows)
        return ""

    def _choices(self, codes) -> str:
        """One line per waiting change: the words to reply with, then what the change is."""
        rows = [self._by_code(c, ("proposed",)) for c in codes]
        return "\n".join(q(f"yes {c}") + ": " + (q(r["summary"]) if r else "") for c, r in zip(codes, rows))

    def _for_g(self, msg):
        """HASS-VOICE-1: `problems` (the last ten problem moments) and `weekly` (the week's three most common) from G's own number
        only (settings gSenders, never an owner sender). They read the correspondence log and nothing else; Mike never sees them."""
        word = msg.text.strip().lower().rstrip(".!")
        if word == "till report":
            allowed = (not msg.from_me and msg.kind == "new" and msg.attachments == 0
                       and sender_key(msg.sender) in self.settings.get("gKeys", ())
                       and msg.chat == self.settings.get("gChat") and msg.chat not in self._owner_chats)
            if not allowed:
                return None
            text = "I haven't been able to read the till yet."
            if self.till is not None:
                try:
                    text = self.till.report(self._now(), editor_mod._load(str(self.sdir))[2])
                except Exception:
                    text = "I couldn't compare the till with the website. Nothing changed."
            self.outbox.add(msg.chat, text, (), self._answering or None, long_ok=True)
            self._record(msg, "g-till-report", owner=False)
            return "g-till-report"
        if msg.from_me or msg.kind != "new" or msg.attachments > 0 or sender_key(msg.sender) not in self.settings.get("gKeys", ()): return None
        if msg.chat != self.settings.get("gChat") or msg.chat in self._owner_chats: return None  # only G's own chat; never an owner's
        if word not in ("problems", "weekly"): return None
        text = corrlog.problems_text(self.log) if word == "problems" else corrlog.weekly_line(self.log)
        self.outbox.add(msg.chat, text, (), self._answering or None, long_ok=True, ids_ok=True)
        self._record(msg, "g-" + word, owner=False)
        return "g-" + word

    def _no_target(self, code, targets, expired) -> str:
        if targets:
            return "\n".join(["Which one do you mean? Reply yes or no and its code."] + [
                (q(f"yes {r['code']}") + ": " + q(r["summary"])) if r["state"] == "proposed" else "I'm waiting for details: " + r["summary"]
                for r in targets])
        if code and self._by_code(code) is None and self._shared and (other := [r for r in self._drafts("code = ?", code) if not self._mine(r)]):
            who = "someone else" if other[-1]["chat"] == self._chat() else self._who(other[-1]["chat"])  # same chat, other sender: a draft kept from before a second owner
            return f"That change belongs to {who}, so I can't save it or cancel it for you. Nothing changed."  # HASS-OWNERS-2: never its words
        if code and self._by_code(code) is None:  # AV2152-01 (H05/H17): a code that matches no draft; never guessed
            waiting = [r for r in self._drafts("state = 'proposed'") if self._mine(r)]
            return "\n".join(["I don't have a change with that code."] + (["These are waiting for you:"] + [
                q(f"yes {r['code']}") + ": " + q(r["summary"]) for r in waiting] if waiting else []))
        named = [self._by_code(code)] if code else [self._row(r["row_id"]) for r in expired if self._visible(r)]
        return "\n".join(self._state_text(r) for r in named if r is not None) or NOTHING

    def _state_text(self, row) -> str:
        state = row["state"]
        if state == "expired": return f"That change timed out {self._when(row['expires_at'])}, so nothing changed. Tell me again if you still want it."
        if state == "rejected" and row["replaced_by"]: return "That one was replaced by a newer one."
        if state == "rejected": return "That one was cancelled, so nothing changed."
        return {"approved": "That one is being saved.", "applied": "That one is already saved.", "verified": "That one is already saved.",
                "failed": "That one couldn't be saved.", "reverted": "That one was undone."}.get(state, "I'm not sure where that one stands.")

    def _registry(self):
        """The editor's ops registry (production: load_registry()), loaded once per conversation."""
        if getattr(self, "_ops", None) is None: self._ops = self.editor.registry or load_registry()
        return self._ops

    def _calls(self, now):
        """H22: (local day, interpreter calls counted for it). No usage table yet means no calls."""
        day = now.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'usage'").fetchone(): return day, 0
        row = self.db.execute("SELECT calls FROM usage WHERE day = ?", (day,)).fetchone()
        return day, row["calls"] if row else 0

    def _makers(self):
        """The worktree's makers (read-only) for the claim check; None when unreadable (every maker change asks)."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            makers = json.loads((wt / "hass" / "content" / "makers.json").read_text("utf-8"))["makers"]
        except (OSError, ValueError, KeyError, TypeError, RecursionError, editor_mod.UnsafeState):
            return None
        return makers if isinstance(makers, dict) else None

    def _routes(self):
        """The worktree's route ideas by id (read-only) for the claim check; None when unreadable (owner text only)."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            ideas = json.loads((wt / "hass" / "content" / "community.json").read_text("utf-8"))["routeIdeas"]
            return {i["id"]: i for i in ideas if isinstance(i, dict) and isinstance(i.get("id"), str)} if isinstance(ideas, list) else None
        except (OSError, ValueError, KeyError, TypeError, RecursionError, editor_mod.UnsafeState):
            return None

    def _sources(self):
        """AV1937-05: the worktree's real hikes by id (read-only) for a hike.repeat copy; None when unreadable (no exemption)."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            events = json.loads((wt / "hass" / "content" / "community.json").read_text("utf-8"))["events"]
            return {e["id"]: e for e in events if isinstance(e, dict) and isinstance(e.get("id"), str)} if isinstance(events, list) else None
        except (OSError, ValueError, KeyError, TypeError, RecursionError, editor_mod.UnsafeState):
            return None

    def _notes(self) -> list:
        """AV1102-09: the newest MAX_NOTES active non-alias memory rows as {"key", "text"}; any problem means none."""
        try:
            if not self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone():
                return []
            private = "".join(f"AND substr(key, 1, {len(p)}) != '{p}' " for p in PRIVATE_PREFIXES)  # constants, not owner text
            rows = self.db.execute(f"SELECT key, value FROM memory WHERE {memory_mod.ACTIVE} {private}"
                                   "ORDER BY created_at DESC, id DESC LIMIT ?", (MAX_NOTES,)).fetchall()
            return [{"key": r[0], "text": r[1]} for r in rows]
        except sqlite3.Error:
            return []

    def _interpreter_aliases(self) -> list:
        """AV0007-06: the newest MAX_INTERPRETER_ALIASES active aliases whose product or maker still exists, as
        {"name", "kind", "id"}; read-only (no table made, no write); any problem means none."""
        try:
            if not self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone():
                return []
            rows = self.db.execute(f"SELECT key, value FROM memory WHERE {memory_mod.ACTIVE} AND substr(key, 1, 6) = 'alias.' "
                                   "ORDER BY created_at DESC, id DESC").fetchall()
            if not rows: return []
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            product_ids = {p["id"] for p in content.products}
            out = []
            for key, value in rows:
                slug, (kind, colon, ident) = key[6:], str(value).partition(":")
                if not slug or not colon or not ident: continue
                if not (ident in product_ids if kind == "product" else ident in content.makers if kind == "maker" else False): continue
                out.append({"name": slug.replace("-", " "), "kind": kind, "id": ident})
                if len(out) >= MAX_INTERPRETER_ALIASES: break
            return out
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            return []

    def _asked_again(self, text, msg):
        """HASS-VOICE-1: the question about to be sent is the one we sent last time to this owner a moment ago: log it."""
        try:
            last = self.db.execute("SELECT text, created_at FROM outbox WHERE id < (SELECT MAX(id) FROM outbox) ORDER BY id DESC LIMIT 1").fetchone()
            if last and last["text"] == voice.plain(text) and self._now() - datetime.fromisoformat(last["created_at"]) <= timedelta(minutes=RECENT_MINUTES):
                self._problem("asked-again", "same-question")
        except (sqlite3.Error, ValueError, TypeError, KeyError): pass

    def _recent_question(self, now):
        """HASS-NL-1: {"question": text} when the newest owner message was answered with a question of ours at most
        RECENT_MINUTES ago (so the next short text is its answer); else None. A needs-details answer also counts when its
        request texts were kept. HASS-HIKE-FLOW-1: plus "earlier", the owner's texts of that request (see _open_ask)."""
        try:
            last = self.db.execute("SELECT provider_id, disposition, received_at FROM messages WHERE received_at IS NOT NULL"
                                   " AND COALESCE((SELECT chat FROM message_chats c WHERE c.provider_id = messages.provider_id), ?) = ?"
                                   " ORDER BY rowid DESC LIMIT 1", (self.settings["ownerChat"], self._chat())).fetchone()
            if last is None: return None
            earlier = self._ask_texts(last["provider_id"], now)
            if last["disposition"] != "question" and not (last["disposition"] == "needs-details" and earlier):  # AV2007-13: a refused code or a lookup in between keeps it
                if (kept := self._asked_before_yes(now)) is not None: return kept  # AV2007-14: a yes that saved a draft leaves the question open
                held = self.db.execute("SELECT value, provider_id FROM control WHERE name = ?", (self._hold_name(),)).fetchone()
                last = self.db.execute("SELECT provider_id, disposition, received_at FROM messages WHERE provider_id = ?",
                                       (held["value"],)).fetchone() if held and held["provider_id"] == last["provider_id"] \
                    else None
                if last is None: return None
                earlier = self._ask_texts(last["provider_id"], now)
            if last["disposition"] != "question" and not (last["disposition"] == "needs-details" and earlier): return None
            row = self.db.execute("SELECT text, created_at FROM outbox WHERE reply_to = ? AND chat = ? ORDER BY id DESC LIMIT 1",
                                  (last["received_at"], self._chat())).fetchone()
            if row is None or not row["text"] or len(row["text"]) > RECENT_MAX: return None
            if now - datetime.fromisoformat(row["created_at"]) > timedelta(minutes=RECENT_MINUTES): return None
            return {"question": row["text"], **({"earlier": earlier} if earlier else {})}
        except (sqlite3.Error, ValueError, TypeError, KeyError): return None

    def _asked_before_yes(self, now):
        """AV2007-14: the open legacy question as `recent` when every owner message since it is an approval (a yes that saved a
        waiting draft), else None."""
        req = self.requests.get(self._chat(), now)
        if req is None or req["state"] != "open" or req["skill"] or req["pending"]: return None
        rows = self.db.execute("SELECT provider_id, disposition, received_at FROM messages WHERE received_at IS NOT NULL"
                               " AND COALESCE((SELECT chat FROM message_chats c WHERE c.provider_id = messages.provider_id), ?) = ?"
                               " AND rowid >= (SELECT rowid FROM messages WHERE provider_id = ?) ORDER BY rowid",
                               (self.settings["ownerChat"], self._chat(), req["provider_id"])).fetchall()
        if len(rows) < 2 or rows[0]["provider_id"] != req["provider_id"] or rows[0]["disposition"] != "question": return None
        if not req["question"] or not req["texts"] or not all(r["disposition"] == "approved" for r in rows[1:]): return None
        return {"question": req["question"], "earlier": req["texts"]}

    def _legacy_question(self, now):
        """AV2007-14: the plain open question of ours (no skill, shelf-check, hike or photo ask) as one line, else None."""
        try:
            req = self.requests.get(self._chat(), now)
            if req is not None and req["state"] == "open" and not req["skill"] and not req["pending"] and not req["attachments"] \
                    and isinstance(req["question"], str) and req["question"].strip() and "hike" not in req["question"].lower():
                return " ".join(req["question"].split())
        except (sqlite3.Error, ValueError, TypeError, KeyError, RecursionError): pass
        return None

    def _still_asking(self, now):
        """AV2007-14: the question of ours the owner has not answered yet (one line), repeated after a saved reply; else None."""
        if (q := self._legacy_question(now)) is not None: return q
        try:
            rows = [r for r in self._drafts("state = 'needs-details'") if self._expiry(r) > now and self._visible(r)]
            return " ".join(rows[-1]["summary"].split()) if rows else None
        except (sqlite3.Error, ValueError, TypeError, KeyError, RecursionError): return None

    def _with_question(self, text):
        q = self._still_asking(self._now())
        return text if q is None else text + "\nI still need your answer to this: " + q

    def _hold_name(self): return "held-question:" + self._chat()

    def _hold(self, msg, question):
        """AV2007-13: this message (a refused code, a separate lookup) leaves the open question usable for the next one."""
        self.db.execute(CONTROL)
        self.db.execute("INSERT INTO control(name, value, set_at, provider_id) VALUES (?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET"
                        " value = excluded.value, set_at = excluded.set_at, provider_id = excluded.provider_id",
                        (self._hold_name(), question["provider_id"], _iso(self._now()), msg.provider_id))

    def _open_question(self, now):
        """AV2007-13: the owner's open non-hike question as {"request_id", "provider_id", "legacy"}, or None. A skill request counts
        when it asked something; a legacy one is the recent question. Never a waiting change, a hike, or an expired request."""
        try:
            req = self.requests.get(self._chat(), now)
            if req is None or req["state"] != "open" or req["pending"] or req["attachments"]: return None
            if req["skill"]: return {**req, "legacy": False} if req["question"] and "hike" not in req["skill"] else None
            recent = self._recent_question(now)
            if recent is None or "hike" in " ".join([recent["question"], *req["texts"]]).lower(): return None
            return {**req, "legacy": True}
        except (sqlite3.Error, ValueError, TypeError, KeyError, RecursionError): return None

    def _ask_texts(self, provider_id, now) -> list:
        """The owner texts kept for the open question that answered message ``provider_id``; any problem or a stale row: []."""
        try:
            req = self.requests.by_provider(self._chat(), provider_id, now)
            return req["texts"] if req and all(isinstance(t, str) and t for t in req["texts"]) else []
        except (sqlite3.Error, ValueError, TypeError, KeyError, RecursionError): return []

    def _open_ask(self, msg, now, earlier, pending=None, question=None):
        """HASS-HIKE-FLOW-1: keep this owner text with the earlier ones of the same open request, newest last, bounded.
        HASS-SHELFCHECK-FLOW-1: ``pending`` = {"ops": [...], "revises": code|None}, the change that waits for today's shelf check.
        SKILLS-FW-3: written to the one open-request store (a request with no skill)."""
        self.requests.put(self._chat(), msg.provider_id, now, texts=[*earlier, msg.text], pending=pending, legacy=True, question=question,
                          turns=ASK_TURNS, per=ASK_TEXT_CUT, total=ASK_CHARS)

    def _shelf_ask(self, now):
        """HASS-SHELFCHECK-FLOW-1: the open shelf-check question as {"ops", "revises", "texts"}, or None. It is open only while
        it is the newest thing the owner and Hass said (any other owner message, a stranger's does not count, closes it) and
        at most RECENT_MINUTES old; a stored change that cannot be read is no question."""
        try:
            row = self.requests.pending_of(self._chat(), now)
            last = self.db.execute("SELECT provider_id FROM messages WHERE received_at IS NOT NULL"
                                   " AND COALESCE((SELECT chat FROM message_chats c WHERE c.provider_id = messages.provider_id), ?) = ?"
                                   " ORDER BY rowid DESC LIMIT 1", (self.settings["ownerChat"], self._chat())).fetchone()
            if row is None or last is None or last["provider_id"] != row["provider_id"]: return None
            pending, texts = row["pending"], row["texts"]
            ops = pending["ops"]
            if not (isinstance(ops, list) and all(isinstance(c, dict) and isinstance(c.get("op"), str) for c in ops)): return None
            calls = row.get("calls") if hasattr(row, "get") else row["calls"]
            return {"ops": ops, "revises": pending.get("revises"), "texts": texts if isinstance(texts, list) else [],
                    "skills": pending.get("skills", []),
                    "calls": calls if isinstance(calls, list) else [], "ask": pending.get("ask"),  # HASS-CHAT-1: "meet" or None (shelf check)
                    "suggest": pending.get("suggest"), "index": pending.get("index"), "notes": [n for n in pending.get("notes") or () if isinstance(n, str)],
                    "till": pending.get("till")}  # HASS-CLOVER-4 FIX-1: the till code (with its website word) waiting for this answer
        except (sqlite3.Error, ValueError, TypeError, KeyError, RecursionError): return None

    def _check_day(self):
        """HASS-SHELFCHECK-FLOW-1: (the stored shelf-check date or None, True when readable) from the writer worktree."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            return checked_on(load_and_validate(wt / "hass" / "content", wt / "storefront-mockup").store), True
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError): return None, False

    def _notice_line(self, now) -> str | None:
        """AV1937-07 (H13/H17): the one saved home-page notice and its last day for `status` and `report`, or None.
        Read-only: the writer worktree's store.json only (never the generated page, the interpreter or a write). Active through
        its last Pacific day, then it says it is no longer shown; the saved notice is never changed. A missing, unreadable or
        invalid notice gives None, and a product-facts failure elsewhere does not matter.
        AV2152-08: a notice with its own first day names both days (before the first day: "not shown yet")."""
        try:
            notice = _read_json(editor_mod._load(str(self.sdir))[2] / "hass" / "content" / "store.json")["notice"]
            problems = []
            days = notice_days(notice)
            if days is None: return None
            checked_text(problems, "text", notice["text"], limit=MAX_NOTICE)
            first, last = days
            if problems or sum(c.isalpha() for c in notice["text"]) < 3: return None
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError): return None
        day, today = sitegen._day_text(last), shop_today(now)
        if first is None:
            return f"Home notice: {notice['text']} - " + (f"through {day}" if last >= today else f"ended {day}; no longer shown")
        span = f"from {sitegen._day_text(first)} through {day}"
        return f"Home notice: {notice['text']} - {span}" + ("; not shown yet" if today < first else "" if today <= last else "; no longer shown")

    def _ask_shelf(self, msg, now, result, earlier, skill_names=()) -> str:
        """HASS-SHELFCHECK-FLOW-1: the change was refused only because today's shelf check is missing (none, or older than
        today): keep it with our question. Nothing is drafted or written until the owner's own yes; a check dated after
        today cannot be fixed by a yes, so that says so."""
        day, readable = self._check_day()
        if readable and day is not None and day > shop_today(now):
            self._reply(SHELF_CLOCK)
            return "not-drafted"
        self._open_ask(msg, now, earlier, {"ops": result["ops"], "revises": result.get("revises"),
                                         "skills": [getattr(s, 'name', s) for s in skill_names], **({"till": result["till"]} if result.get("till") else {})})
        self._reply(SHELF_QUESTION)
        return "question"

    def _shelf_answer(self, msg, now, verb, ask) -> str:
        """SKILLS-FW-3: the shelf-check answer (below), then the owner's other queued asks go on one at a time: the next one
        becomes the open request and its question is asked, whichever way the shelf-check change went."""
        if (busy := self._writer_busy(now)) is not None: return self._busy_reply(busy)  # HASS-OWNERS-2
        if ask.get("ask") in ("meet", "offer"): return self._meet_answer(msg, now, verb, ask)  # HASS-CHAT-1: our hike question
        disposition = self._shelf_decide(msg, now, verb, ask)
        calls = ask.get("calls") or []
        if calls and self.skills_mode != dispatch_mod.DEFAULT_MODE:
            self.dispatch._next_queued(msg, now, None, calls, ask["texts"], [], disposition)
        return disposition

    def _meet_answer(self, msg, now, verb, ask) -> str:
        """HASS-CHAT-1: our hike questions. "meet": a bare yes takes the suggested meeting place and drafts the waiting hike (its
        notes kept); a bare no, or a yes when there was no suggestion, asks where instead and keeps the request open for his
        answer in words. "offer": a bare yes drafts the offered change (the nearest one that can go live); no changes nothing."""
        self._close_asks()
        if ask.get("ask") == "offer":
            if verb != "approve":
                self._reply("Okay, I've left it as it is. Nothing changed.")
                return "offer-no"
            return self._draft(msg, now, {"ops": ask["ops"], "revises": ask["revises"]}, ask["texts"], notes=ask["notes"])
        if verb == "approve" and isinstance(ask.get("suggest"), str) and ask["suggest"]:
            ops = hike_chat.with_meeting(ask["ops"], ask["suggest"], self._routes(), ask.get("index"))
            return self._draft(msg, now, {"ops": ops, "revises": ask["revises"]}, ask["texts"], notes=ask["notes"])
        self._open_ask(msg, now, ask["texts"])  # the request stays open: his next words say where
        self._reply(MEET_NO)
        return "question"

    def _shelf_decide(self, msg, now, verb, ask) -> str:
        """HASS-SHELFCHECK-FLOW-1: the owner's bare yes or no to the open shelf-check question (never a draft's yes/no).
        yes: one draft that marks today's shelf check and then makes the waiting change (none, for the morning report's
        question), with the normal approval; no: nothing is changed and the question is closed."""
        self._close_asks()
        if isinstance(ask.get("till"), str) and self.till is not None and self.till.engine is not None:  # HASS-CLOVER-4 FIX-1
            if verb == "reject": self.till.drop(ask["till"], self._asker, msg.chat)  # noqa: E701
            if verb == "reject" or self._paused():
                self._reply(SHELF_NO if verb == "reject" else self.till.answer(("yes", ask["till"]), now))
                return "shelf-no" if verb == "reject" else "paused"
            self._till_job = (ask["till"], True)  # the whole bundle (till, shelf check, website word) now, after this message is saved
            return "till-approved"
        if verb == "reject":
            self._reply(SHELF_NO)
            return "shelf-no"
        ops = [{"op": "store.confirm_selection", "args": {}}, *ask["ops"]]
        out = self.editor.prepare(ops, skills=ask.get('skills', ())) if hasattr(self.editor, 'gate') else self.editor.prepare(ops)
        draft = out.get("draft") if out["result"] == "ok" else None
        revised = self._by_code(ask["revises"], ("proposed", "needs-details")) if isinstance(ask["revises"], str) else None
        if draft is None or claims.unstated(draft, " ".join(ask["texts"]), self._makers(), self._routes(), self._sources()) or (
                self.settings.get("liveSite") and live_policy.unsaid(draft, "\n".join(ask["texts"]))):  # HASS-LIVE-ADD-1
            self._reply(SHELF_FAILED)
            return "not-drafted"
        same = [r for r in self._drafts("state = 'proposed' AND change_id = ?", draft["change_id"]) if self._mine(r)]
        row = same[0] if same else self._propose(draft, msg.sender, now)
        if revised is not None and not same: self._move(revised, "rejected", reason="revised", replaced_by=row["code"])
        self._proposal_reply(row, draft, "Got it. This draft also records that the shelf list was checked today.\n" if ask["ops"] else "")
        return "proposed"

    def _close_asks(self, now=None, state="closed"):
        """HASS-HIKE-FLOW-1: forget the open request (all of it, or with ``now`` only what is older than RECENT_MINUTES).
        SKILLS-FW-3: one store; a skill request is closed (``state``), and its text erased 24 hours later; a closed one older
        than that, and any backlog row older than its retention, goes at the same sweep."""
        owner = self._chat()  # HASS-LIVE-PLAN-1: per owner chat
        if now is None: self.requests.close_live(owner, self._now(), state)
        else:
            self.requests.sweep(now)
            if self.skills_mode != dispatch_mod.DEFAULT_MODE and self._backlog_table():
                from hass.skills.backlog import Backlog
                Backlog(self.db, self._now).purge()

    def _audit_backend(self, msg, now, failed):
        """HASS-INTERP-OPENAI-1: one audit row per interpreted message when the interpreter names the backend that answered
        (and whether the fallback was asked). No such interpreter, or a call that raised: no row."""
        itp = self.interpreter
        backend = getattr(itp, "last_backend", None)
        if failed is None or not isinstance(backend, str) or not backend: return
        code = lambda v: v if isinstance(v, str) and len(v) <= 40 else None  # noqa: E731 - short reason codes only
        seconds = getattr(itp, "last_seconds", None)
        self.db.execute(AUDIT)
        self.db.execute("INSERT OR REPLACE INTO interpreter_audit VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (msg.provider_id, _iso(now), backend[:20], 1 if getattr(itp, "last_fallback", False) is True else 0,
                         code(getattr(itp, "last_primary_error", None)), code(getattr(itp, "last_error", None)),
                         float(seconds) if isinstance(seconds, (int, float)) else None))

    def _request(self, msg, now) -> str:
        if (busy := self._writer_busy(now)) is not None: return self._busy_reply(busy)  # HASS-OWNERS-2: before any model call or count
        if len(msg.text) > MAX_OWNER_TEXT:  # AV1737-04: code points; never interpreted, drafted or counted
            self._reply(TOO_LONG)
            return "too-long"
        if HOSTILE_RE.search(msg.text):  # a calm no, decided here: the model is never asked and nothing is drafted or counted
            self._reply(HOSTILE_REPLY)
            self._problem("could-not-do", "refused-request")
            return "unsupported"
        cap = self.settings["interpreterDailyCap"]
        skills_on = self.skills_mode != dispatch_mod.DEFAULT_MODE
        req = self.requests.get(self._chat(), now) if skills_on else None  # SKILLS-FW-3: the owner's own open request
        if skills_on: msg, req = self.dispatch.intake_text(msg, now, req)
        if (held := self._open_question(now)) is not None and SEPARATE_RE.fullmatch(msg.text.strip().lower()):  # AV2007-13: its own message
            disposition = self._request_now(msg, now, None, True)  # no old context; the question stays open
            if self.requests.by_provider(self._chat(), held["provider_id"], now) is not None: self._hold(msg, held)
            return disposition
        return self._request_now(msg, now, req, False)

    def _expire_lapsed(self) -> None:
        """AV1104-06: the move to `expired` (and its audit line) for the drafts _handle found lapsed and held back, exactly as the
        old up-front sweep did. Nothing is held back unless the message can only reach the interpreter."""
        lapsed, self._lapsed = self._lapsed, ()
        for held in lapsed:
            row = self._row(held["row_id"])
            if row["state"] not in ("proposed", "needs-details"): continue
            self._move(row, "expired", expires_at=_iso(self._expiry(row)))
            if row["state"] == "proposed": self._audit("refused", row, "expired")  # AVB-10

    def _lookup(self, msg, now, result) -> str:
        """AV1104-06: a question that only asks what the site, shop or hikes show. ``result`` is {"lookup": text}. An allowed
        read-only command (interpret_check.lookup_command) is answered by its own handler with one line in front; anything else
        gets the fixed refusal. Nothing is drafted, approved, saved or expired; the interpreter call was already counted."""
        self._lapsed = ()  # never moved: a lapsed draft is only filtered out by time
        checked = interpret_check.check(result, self._registry(), ())
        if "unsupported" in checked:
            self._reply(voice.quote(checked["unsupported"]), long_ok=True)  # quoted: the voice check bans "drafted" and "<id>", the owner sees the fixed words as they are
            return "lookup"
        verb, argument = interpret_check.lookup_command(checked["lookup"])
        self._lookup_prefix = voice.quote(LOOKUP_PREFIX)
        try: self._command(msg, now, verb, argument)
        finally: self._lookup_prefix = None
        return "lookup"

    def _request_now(self, msg, now, req, separate) -> str:
        cap, skills_on = self.settings["interpreterDailyCap"], self.skills_mode != dispatch_mod.DEFAULT_MODE
        if skills_on and not separate and req is not None: self._expire_lapsed()  # the open skill request may read a lapsed draft: not a lookup, it is a short answer
        if skills_on and not separate and (done := self.dispatch.cheap(msg, now)) is not None: return done  # a short answer read by code: no model call
        from hass.skills import stock as stock_skill  # AV2007-15: a plain "shelf check done" is drafted by code, never the model
        if stock_skill.plain_shelf_check(msg.text):
            self._expire_lapsed()
            return self._draft_shelf_check(msg, now, {})
        if (names := stock_skill.shelf_check_except(msg.text)) is not None:  # AV2007-16
            self._expire_lapsed()
            return self._shelf_check_except(msg, now, names)
        if cap is not None:  # H22: counted before the call in this transaction, so a failed call still counts
            day, calls = self._calls(now)
            if calls >= cap:
                self._reply(DAILY_LIMIT)
                return "daily-limit"
            self.db.execute(USAGE)
            self.db.execute("INSERT INTO usage VALUES (?, 1) ON CONFLICT(day) DO UPDATE SET calls = calls + 1", (day,))
        if CORRECTION_RE.match(msg.text.strip()): self._problem("corrected", "owner-corrected")
        pending = [{"code": r["code"], "state": r["state"], ("question" if r["state"] == "needs-details" else "summary"):
                    r["summary"], **_pending_ops(r["ops_json"]),  # AV0022-03: + "ops" or "opsOmitted"
                    **({"missing": _missing_ids(r["missing_json"])} if r["state"] == "needs-details" else {})}  # AV0007-03
                   for r in self._drafts("state IN ('proposed', 'needs-details')") if self._mine(r) and self._expiry(r) > now]
        notes = self._notes()  # AV1102-09: preferences only; no notes means no notes keyword
        kept = req is not None and bool(req["skill"] or req["attachments"])  # SKILLS-FW-3: a skill request replaces `recent`
        recent = None if separate else self.requests.snapshot(req) if kept else self._recent_question(now)  # HASS-NL-1; HASS-HIKE-FLOW-1: with the owner's earlier texts of the same request
        context = {k: v for k, v in (("notes", notes), ("aliases", self._interpreter_aliases()),
                                     ("recent", recent)) if v}  # AV0007-06; HASS-NL-1
        sent_at = _answered_at(msg, now)  # AV1352-06: 'today' is the day it was sent; bad, naive or future means now
        failed = None  # AV1052-10: None until interpret actually returned; then the adapter's last_error (or "")
        skill_result = None
        try:
            raw = self.interpreter.interpret(msg.text, pending, **context, sent_at=sent_at)
            skill_result = dispatch_mod.checked(raw) if skills_on else None  # SKILLS-FW-3: skill / calls / none / cancel
            result = skill_result or _checked(raw)
            failed = getattr(self.interpreter, "last_error", None) or ""
        except Exception if cap is not None else ():  # H22: no cap: unchanged (an error rolls the message back)
            result = dict(UNREADABLE)  # keep the counted call; a failure stops safely with the unreadable reply
        self._audit_backend(msg, now, failed)
        if failed:  # AV1052-10: the reader itself failed: remember it for status (latest only, no error detail kept)
            self.db.execute(CONTROL)
            self.db.execute("INSERT INTO control(name, value, set_at, provider_id) VALUES ('reader-failed', ?, ?, ?)"
                            " ON CONFLICT(name) DO UPDATE SET value = excluded.value, set_at = excluded.set_at,"
                            " provider_id = excluded.provider_id",
                            (getattr(self, "_photo_draft", None) or "1", _iso(now), msg.provider_id))
        elif failed is not None and self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'control'").fetchone():
            self.db.execute("DELETE FROM control WHERE name = 'reader-failed'")  # a request was read again
        if skill_result is None and "lookup" in result: return self._lookup(msg, now, result)  # AV1104-06: the interpreter call is counted; nothing else is touched
        self._expire_lapsed()  # AV1104-06: the sweep _handle held back until the reply was known not to be a lookup
        if skill_result is not None: return self.dispatch.reply(msg, now, skill_result, req)  # SKILLS-FW-3
        if skills_on and self.skills_mode == "skills-first" and "ops" in result and any(
                dispatch_mod.op_is_owned(c["op"], self.dispatch.registry) for c in result["ops"] if isinstance(c, dict) and isinstance(c.get("op"), str)):
            self._reply(UNREADABLE["unsupported"])  # a skill owns this change: raw ops are no longer taken for it (spec 2.4)
            return "unsupported"
        earlier = (recent or {}).get("earlier") or []  # HASS-HIKE-FLOW-1: the open request this text may be answering
        if not skills_on and not failed and "question" in result and not pending and not earlier and not getattr(msg, "attachments", 0):
            result = self._stock_choice(msg.text) or result  # AV2007-12: one product named whole is taken before asking which
        return self._draft(msg, now, result, earlier, failed=failed, req=req)

    def _draft_shelf_check(self, msg, now, slots) -> str:
        """AV2007-15: draft today's shelf-check record (stock.checked's own plan, so the same draft) without a model, in every skills
        mode. The proposal names its code and only `yes <code>` approves it. A later extension fills ``slots``; this one passes none."""
        from hass.skills import stock as stock_skill
        skill = stock_skill.STOCK_CHECKED
        if hasattr(self.editor, "skill_allowed") and not self.editor.skill_allowed(skill):
            self._reply("That's switched off, so nothing changed.")
            return "refused"
        try:
            ctx = (self.dispatch or dispatch_mod.Dispatcher(self, None))._ctx(now, [msg.text])
            ops = skill.plan(dict(slots), ctx)
        except stock_skill.Refusal as exc:
            self._reply(exc.reply)
            return "refused"
        except Exception:  # noqa: BLE001 - a plan or the content read must not raise past the owner's message
            self._reply(dispatch_mod.PLAN_FAILED)
            return "not-drafted"
        self._skill_ref = f"{skill.name}@{skill.version}"
        try: return self._draft(msg, now, {"ops": ops, "revises": None}, [], skill_names=(skill,), code_reason=SHELF_CODE_REASON)
        finally: self._skill_ref = None

    def _shelf_check_except(self, msg, now, names) -> str:
        """AV2007-16: 'all good except X and Y' is today's shelf check plus X and Y sold out in ONE draft, by code. Every name is
        resolved first (kinds.product_ref); the first one that is not exactly one active product is asked about, or refused with the
        resolver's own words, and nothing is drafted. More than five names is refused before any lookup."""
        from hass.skills import kinds, stock as stock_skill
        if len(names) > stock_skill.MAX_SOLD_OUT_WITH_CHECK:
            self._reply(SHELF_CHECK_LIMIT)
            return "not-drafted"
        try:
            ctx = (self.dispatch or dispatch_mod.Dispatcher(self, None))._ctx(now, [msg.text])
            found = [kinds.product_ref(ctx.content, name, ctx.aliases) for name in names]
        except Exception:  # noqa: BLE001 - a content read must not raise past the owner's message
            self._reply(dispatch_mod.PLAN_FAILED)
            return "not-drafted"
        for one in found:
            if one.status != "one":
                self._reply(one.reply)
                return "question" if one.status == "several" else "not-drafted"
        return self._draft_shelf_check(msg, now, {"out": [one.value for one in found]})

    def _keep_design(self, msg, said):
        """AV1052-11 (H24/H15): the fixed design refusal also keeps the owner's words (first 500 characters) as a dated owner note
        design.<n> for the developer: local memory only, nothing sent, nothing on the site changes. Any other reply is unchanged."""
        if said != DESIGN_UNSUPPORTED: return said
        if self.memory is None: self.memory = memory_mod.Memory.on_connection(self.db, self.clock)
        try: key = self.memory.remember_design(msg.text, f"owner-stated:{msg.provider_id}")
        except ValueError:
            return f"{said}. I couldn't keep the note. To keep one yourself, say it like remember parking: Rear lot (1 to 500 plain characters)."
        return f"{said}. I kept it for the developer as {key}." + (" Only the first 500 characters were kept." if len(msg.text) > memory_mod.MAX_VALUE else "")

    def _stock_choice(self, text):
        """AV2007-12: nl_prep.resolve_stock_choice over the current validated content and the owner's aliases; None when the content
        cannot be read or the text is not one product out/back."""
        try:
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            return nl_prep.resolve_stock_choice(text, content, self._interpreter_aliases())
        except (OSError, ValueError, KeyError, TypeError, AttributeError, ContentError, editor_mod.UnsafeState):
            return None

    def _weekday_conflict(self, msg, now, result, earlier):
        """AV2007-10: the code-owned question when a hike date or a notice from/until in ``result["ops"]`` is either reading of a
        weekday that disagrees with the date beside it, in the newest date-bearing text of this request; else None."""
        ops = result.get("ops")
        if not isinstance(ops, list): return None
        today = shop_today(_answered_at(msg, now))
        for text in reversed([*earlier, msg.text]):  # a time or place answer says no day and does not erase an open conflict
            rows, hits = nl_prep.all_date_rows(text, today)
            if rows or hits: break
        else: return None
        used = {str(c["args"][k])[:10] for c in ops if isinstance(c, dict) and isinstance(c.get("args"), dict)
                for k in {"hike.create": ("date",), "hike.update": ("date",), "store.set_notice": ("from", "until")}.get(c.get("op"), ()) if k in c["args"]}
        for row in rows:
            if row.get("weekday_mismatch") and used & {row["date"], *row["weekday_dates"]}: return nl_prep.weekday_mismatch_question(row)
        return None

    def _draft(self, msg, now, result, earlier, prefix="", failed=None, req=None, legacy=True, notes=(), skill_names=(), code_reason=None):
        """Draft ``result["ops"]`` (from the interpreter, or from a skill plan: SKILLS-FW-3), or relay its question / unsupported
        reply: revises, the interpret check, the editor, the claims gate over the owner's JOINED texts, the proposal. The caller
        has already counted the model call, if there was one. Returns the disposition."""
        self._last_draft_code = None
        pending = [r for r in self._drafts("state IN ('proposed', 'needs-details')") if self._expiry(r) > now and self._visible(r)]  # HASS-OWNERS-2
        own = getattr(self, "_photo_draft", None)  # AV2007-01: this message's own photo row, trusted only while its caption is read
        if own and legacy and result.get("ops") and not result.get("revises") and any(r["code"] == own and r["state"] == "needs-details" for r in pending) \
                and sum(1 for c in result["ops"] if isinstance(c, dict) and c.get("op") in PHOTO_OPS) == 1:
            result = {**result, "revises": own}  # a null revision from a photo's own caption is about that photo, never another waiting one
        codes = {p["code"] for p in pending}
        named = self._by_code(result["revises"]) if result.get("revises") and result["revises"] not in codes else None
        cancelled_question = named is not None and named["state"] == "rejected" and named["reason"] == "owner" \
            and named["change_id"] is None  # AV1537-02: a question the owner cancelled is not filled later
        if named is not None and named["state"] == "expired" or cancelled_question:  # H16 vs NB-AV-01 (2026-10-31):
            result = {**result, "revises": None}  # a closed draft has nothing left to revise; an unknown code still asks
        result = interpret_check.check(result, self._registry(), codes,
                                       from_intake=not legacy and bool(getattr(self, "_intake_listing", None)))
        if (said := self._weekday_conflict(msg, now, result, earlier)) is not None:  # AV2007-10: asked before any draft side effect
            result = {"question": said, "revises": result.get("revises")}
        if legacy and "question" in result:
            if req is not None and (req["skill"] or req["attachments"]):  # a question about a skill request stays on that request
                self.requests.put(self._chat(), msg.provider_id, now, texts=[*req["texts"], msg.text], request_id=req["request_id"],
                                  skill=req["skill"], slots=req["slots"], calls=req["calls"], attachments=req["attachments"],
                                  question=result["question"], draft_code=req["draft_code"], asks=req["asks"])
            else: self._open_ask(msg, now, earlier, question=result["question"])  # keep the request with our question, for the answer
        elif legacy and "ops" in result: self._close_asks()  # a draft (or its own question) takes over; nothing stays open
        for key in ("question", "unsupported"):
            if key in result:
                self._reply(self._keep_design(msg, result[key]) if key == "unsupported" and not failed else result[key])
                cant = "can't do that" in result[key].lower()
                if key == "unsupported" or cant:
                    self._problem("error" if failed else "could-not-do" if cant else "did-not-understand",
                                  "reader-failed" if failed else "no-skill" if cant else "unclear")
                else: self._asked_again(result[key], msg)
                return "reader-failed" if failed and key == "unsupported" else key
        revised = self._by_code(result["revises"], ("proposed", "needs-details")) if result["revises"] else None
        photo = next((c["args"]["photo"] for c in json.loads(revised["ops_json"]) if c["op"] in PHOTO_OPS
                      and isinstance(c["args"].get("photo"), str)), None) if revised else None  # NB-AV-09, AV1937-01: a fill keeps the draft's photo, whichever place it was heading for; another one is refused
        calls = [c for c in result["ops"] if c["op"] in PHOTO_OPS] if photo else []  # AV0022-04: a new product too
        if len(calls) > 1:  # AV0022-04: one photo, one product; nothing changes until the owner says which
            return self._reply("One photo can go in one place; say which.") or "photo-many-ops"
        if any(c["args"].setdefault("photo", photo) != photo for c in calls):
            return self._reply("That answer goes with a different photo, so nothing changed. Which product is this photo for?") or "photo-mismatch"
        notes = list(notes)
        if self.settings.get("liveSite") and any(c.get("op") in ("hike.create", "hike.update") for c in result["ops"]):  # HASS-CHAT-1
            shaped = hike_chat.shape(result["ops"], self._routes(), events=self._sources())
            if shaped.ask and shaped.ask["kind"] == "offer":  # sign-up asked for on a posted hike: the nearest live change, as a yes/no
                if shaped.ask["ops"] and legacy:
                    self._open_ask(msg, now, earlier, {"ops": shaped.ask["ops"], "revises": result["revises"], "ask": "offer", "notes": notes})
                self._reply(shaped.ask["question"])
                self._problem("could-not-do", "signup-offered")
                return "question" if shaped.ask["ops"] and legacy else "not-drafted"
            if shaped.ask and legacy:  # a trail name is not a place to meet: ask once, keep the shaped hike for his answer
                self._open_ask(msg, now, earlier, {"ops": shaped.ops, "revises": result["revises"], "ask": "meet",
                                                   "suggest": shaped.ask["suggest"], "index": shaped.ask.get("index"),
                                                   "notes": [*notes, *shaped.notes]})
                self._reply(shaped.ask["question"])
                self._asked_again(shaped.ask["question"], msg)
                return "question"
            result, notes = {**result, "ops": shaped.ops}, [*notes, *shaped.notes]
        out = self.editor.prepare(result["ops"], skills=skill_names) if hasattr(self.editor, "gate") else self.editor.prepare(result["ops"])
        if own and revised is not None and revised["code"] == own and out["result"] == "refused" and out.get("reason") == "imageAlt is required with photo" and calls:
            out = {"result": "needs-details", "missing": ["imageAlt"],  # AV2007-01: the caption named the product but not what the photo shows: ask only that
                   "question": "What does the photo show, for people who cannot see it? A few words is fine."}
        if out["result"] == "needs-details":
            ops_json = json.dumps(result["ops"], sort_keys=True)
            expires = _iso(now + timedelta(seconds=self.settings["approvalTtlSeconds"]))  # H16: questions lapse too
            missing_json = json.dumps(out.get("missing", []))  # AV0007-03: stored with the question, same transaction
            if revised is not None and revised["state"] == "needs-details":  # the owner just answered: refresh
                self.db.execute("UPDATE drafts SET ops_json = ?, summary = ?, expires_at = ?, missing_json = ? WHERE row_id = ?",
                                (ops_json, out["question"], expires, missing_json, revised["row_id"]))
                self._last_draft_code = revised["code"]
            else:
                code = self._code(hashlib.sha256(msg.provider_id.encode()).hexdigest())
                self.db.execute(
                    "INSERT INTO drafts(code, state, ops_json, summary, sender, chat, created_at, expires_at, missing_json)"
                    " VALUES (?, 'needs-details', ?, ?, ?, ?, ?, ?, ?)",
                    (code, ops_json, out["question"], msg.sender, msg.chat, _iso(now), expires, missing_json))
                self._last_draft_code = code
                # An incomplete correction still supersedes the proposal it names: it can no longer be approved.
                if revised is not None:
                    if revised["state"] == "proposed": self._audit("refused", revised, "replaced")  # AVB-10
                    self._move(revised, "rejected", reason="revised", replaced_by=code)
            if legacy and photo and "imageAlt" in out.get("missing", []) and any(c["op"] == "product.add" for c in calls):
                self._open_ask(msg, now, earlier)  # keep the caption/request evidence through the photo-description answer
            self._reply(out["question"])
            self._asked_again(out["question"], msg)
            return "needs-details"
        if out["result"] == "refused" and out.get("reason") == catalog.NOT_CHECKED_TODAY and not ({"store.confirm_selection"} & {c["op"] for c in result["ops"]}):
            return self._ask_shelf(msg, now, result, earlier, skill_names)  # keep skill off-policy through the shelf question
        if out["result"] != "ok":
            ops, reason = result["ops"], _reason(out)
            event = (self._sources() or {}).get(ops[0]["args"].get("id")) if len(ops) == 1 and ops[0].get("op") == "hike.update" else None
            if (isinstance(reason, str) and reason.strip().lower() == "guest count unavailable" and isinstance(event, dict)
                    and "capacity" in ops[0]["args"] and ops[0]["args"].get("rsvpEnabled") is not True  # AV2007-18: the real reason
                    and event.get("rsvpEnabled") is False and event.get("status") == "scheduled"
                    and isinstance(event.get("title"), str) and event["title"].strip()):
                self._reply(f"Sign-up is off for {voice.quote(event['title'])}, so there is no guest limit to change. Nothing changed.")
                self._problem("could-not-do", "signup-off-no-limit")
                return "not-drafted"
            self._reply(self._plain(reason))
            return "not-drafted"
        draft = out["draft"]
        if hits := claims.unstated(draft, " ".join([*earlier, msg.text]), self._makers(), self._routes(), self._sources()):  # NB-AV-05: an unstated claim asks, never drafts; HASS-HIKE-FLOW-1: the owner's earlier texts of this request count as stated
            self._reply(claims.question(hits))  # no row; a waiting draft named by revises is left as it was
            return "claim-question"
        if self.settings.get("liveSite") and (said := live_policy.unsaid(draft, "\n".join([*earlier, msg.text]))):
            self._reply(live_policy.unsaid_question(said))  # HASS-LIVE-ADD-1: a new product's brand, maker and town only in his words
            return "claim-question"
        same = [r for r in self._drafts("state = 'proposed' AND change_id = ?", draft["change_id"]) if self._mine(r)]
        if same and (revised is None or revised["row_id"] == same[0]["row_id"]):
            row = same[0]
        elif revised is not None and (revised["state"] == "needs-details" or getattr(self, "_intake_listing", None)):
            if revised["state"] == "proposed": self._audit("refused", revised, "replaced")
            row = self._propose(draft, msg.sender, now, row=revised)
        else:
            row = self._propose(draft, msg.sender, now, like=revised)  # AVB-10: a correction stays the same request
            if revised is not None:
                if revised["state"] == "proposed": self._audit("refused", revised, "replaced")  # AVB-10
                self._move(revised, "rejected", reason="revised", replaced_by=row["code"])
        self._last_draft_code = row["code"]
        if code_reason and not str(row["reason"] or "").startswith("again:"):  # AV2007-15: this draft's yes must name its code
            self.db.execute("UPDATE drafts SET reason = ? WHERE row_id = ?", (code_reason, row["row_id"]))
            row = self._row(row["row_id"])
        self._proposal_reply(row, draft, prefix, notes)
        return "proposed"

    def _photo(self, msg, now, last_try=False) -> str:  # NB-AV-09: store one photo, then open (or name) its needs-details draft
        count = msg.attachments
        if not 1 <= count <= media.MAX_PHOTOS_PER_MESSAGE: return self._reply(media.REPLIES["many"]) or "attachment-many"
        if (busy := self._writer_busy(now)) is not None: return self._busy_reply(busy)  # HASS-OWNERS-2: nothing fetched or stored
        try:
            fetch = getattr(self.photos, "fetch_for_inbox", self.photos.fetch)
            if count == 1: photos = [fetch(msg.provider_id, 1)[0]]  # NB-AV-11: an empty/short answer is a failure too
            else:  # AV2152-04: exactly count byte entries, in the order sent, or it is a fetch failure
                photos = fetch(msg.provider_id, count)
                if not isinstance(photos, list) or len(photos) != count or not all(isinstance(p, (bytes, bytearray)) for p in photos):
                    raise ValueError("fetch")
        except media.Refused as exc:
            return self._photos_refused([(getattr(exc, "position", 1), exc)], count)
        except Exception:  # never applied or read without the photo: retry via the inbox, or one reply on the last try
            if not last_try: raise AttachmentPending("fetch") from None
            return self._reply(FETCH_FAILED) or "attachment-failed"
        refused = []
        for position, data in enumerate(photos, 1):  # NB-AV-10: every photo is checked before any is written
            try: media.check_photo(data)
            except media.Refused as exc: refused.append((position, exc))
        if refused: return self._photos_refused(refused, count)
        try:
            stored = ([media.store_original(self.settings["mediaRoot"], photos[0], received_at=msg.received_at or _iso(now), source="owner-chat")]
                      if count == 1 else media.store_originals(self.settings["mediaRoot"], photos, received_at=msg.received_at or _iso(now),
                                                               source="owner-chat"))
        except media.BatchRefused as exc:
            return self._photos_refused([(exc.position, exc)], count)
        except media.Refused as exc:
            return self._photos_refused([(1, exc)], count)
        if self.npp is not None and msg.chat in self._owner_chats:
            shas = [s["sha256"] for s in stored]
            if (result := self._npp_photo(self.npp, msg, now, shas)) is not None: return result
        if photo_polish.enabled(self.settings): self._polish_jobs += [s["sha256"] for s in stored]  # HASS-IMAGE-1: started after the commit
        if count > 1: return self._photo_batch(msg, now, [s["sha256"] for s in stored])
        sha = stored[0]["sha256"]
        dup = self._drafts("state IN ('proposed', 'needs-details') AND ops_json LIKE ?", f'%"photo": "{sha}"%')
        if dup: return self._reply("I already have that photo, and I'm waiting on you. " + (
            dup[0]["summary"] if dup[0]["state"] == "needs-details" else "It's in a change waiting for your yes.")) or "photo-duplicate"
        caption = msg.text.replace("\ufffc", "").strip()  # handled as the next text, in this same transaction
        if said := self._photo_on_product(sha):
            self._reply(said)
            return self._request(Inbound(**{**vars(msg), "text": caption}), now) if caption else "photo-on-product"
        if self.skills_mode != dispatch_mod.DEFAULT_MODE and self.dispatch.photo_skills():  # SKILLS-FW-3 (spec 2.7): the photo joins the open request
            prior = self.db.execute("SELECT COALESCE(MAX(id), 0) FROM outbox").fetchone()[0]
            intake_answers = None
            if self.settings.get("itemIntake") is True:
                caption, intake_answers = item_intake.caption_answers(caption, self._intake_fields)
            as_text = Inbound(**{**vars(msg), "text": caption})
            done = self.dispatch.photo(as_text, now, sha, caption, intake_answers=intake_answers)
            done = done if done is not None else self._request(as_text, now)
            req = self.requests.get(msg.chat, now)
            if (req and req["skill"] == "item.add" and req["state"] == "open" and req["attachments"][-1:] == [sha]
                    and req["slots"].get("intake", {}).get("reading_photo")):
                # Do not commit provisional caption replies. Earlier turns' outbox rows are untouched.
                self.db.execute("DELETE FROM outbox WHERE chat = ? AND id > ? AND sent_at IS NULL", (msg.chat, prior))
                self._label_jobs.append((None, sha, (as_text, req["request_id"], now)))
                if sha in self._polish_jobs: self._polish_jobs.remove(sha)
            return done
        code = self._photo_row(sha, msg, now)
        if not caption:
            self._photo_question(code, sha)
            return "photo-draft"
        self._photo_draft = code  # AV1052-10: if the reader fails on this caption, status names this draft; AV2007-01: and it is this message's own photo row
        try: done = self._request(Inbound(**{**vars(msg), "text": caption}), now)
        finally: self._photo_draft = None
        if done not in ("proposed", "needs-details", "question"): self._photo_question(code, sha)  # AV2007-01: asked once, and only if the caption did not already answer
        return done

    def _npp_photo(self, jobs, msg, now, shas):
        # One batch is one intake; the first photo supplies the picture, the others are identification input.
        if jobs.stages is None:
            return self._reply(jobs.replies["guards"]["render_failed"]) or "npp-unavailable"
        finance, replace_price = self._npp_words(msg.text.replace("\ufffc", ""), photo=True)
        accepted = npp_instant(self._forwarded) or now
        return jobs.input(msg, self._asker, min(accepted, now), now, finance, shas, replace_price=replace_price)

    def _photo_question(self, code, sha):
        self._reply(PHOTO_QUESTION)
        if self.labels is not None: self._label_jobs.append((code, sha, self.db.execute("SELECT last_insert_rowid()").fetchone()[0]))

    def _photos_refused(self, refused, count) -> str:  # AV2152-04: one reply naming each refused photo; none of the message was kept
        if count == 1: return self._reply(refused[0][1].reply) or f"photo-refused:{refused[0][1].code}"
        lines = [f"Photo {position} out of {count}: {exc.reply}" for position, exc in refused]  # voice rules forbid "1 of 4"
        self._reply("\n".join([*lines, NONE_SAVED]), long_ok=True)  # four named refusals can pass voice.LONG_AFTER; each must be named
        return f"photo-refused:{refused[0][1].code}"

    def _photo_on_product(self, sha):
        """H12: the sentence naming the active or hidden product whose picture this photo is, else None (unreadable worktree: None)."""
        try:
            image = re.compile(rf"assets/products/photo-{sha[:16]}\.(jpg|png)")
            on = next((p for p in sorted((p for p in load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
                       .products if isinstance(p, dict)), key=lambda p: str(p.get("id")))
                       if p.get("status") in ("active", "hidden") and isinstance(p.get("image"), str)
                       and image.fullmatch(p["image"])), None)
            if on is not None and "id" not in on: raise KeyError("id")  # a matching record must still be readable
            return on and f"That photo is already on {q(on['name'])}. To change that product, tell me what to change."
        except (OSError, ValueError, KeyError, TypeError, editor_mod.UnsafeState): return None  # no id/name: as unreadable

    def _photo_row(self, sha, msg, now) -> str:
        self.db.execute("INSERT INTO drafts(code, state, ops_json, summary, sender, chat, created_at, missing_json) VALUES"
                        " (?, 'needs-details', ?, ?, ?, ?, ?, ?)", (code := self._code(sha), json.dumps(
                            [{"op": "product.set_photo", "args": {"photo": sha}}]), PHOTO_QUESTION, msg.sender, msg.chat, _iso(now),
                            json.dumps(["id", "imageAlt"])))  # AV0007-03: set_photo's required args besides the photo
        return code

    def _photo_batch(self, msg, now, shas) -> str:
        """AV2152-04 (H12): 2 to 4 stored photos, in the order sent: each new one opens its own coded needs-details draft and
        question (and, after the commit, its own label job); a photo already in a draft or on a product is named and opens
        nothing. The caption is never read, whatever it says."""
        n = len(shas)
        for i, sha in enumerate(shas, 1):
            head = f"Photo {i} out of {n}: "  # voice rules forbid "1 of 4"
            if dup := self._drafts("state IN ('proposed', 'needs-details') AND ops_json LIKE ?", f'%"photo": "{sha}"%'):
                self._reply(head + "I already have that photo, and I'm waiting on you. " + (
                    dup[0]["summary"] if dup[0]["state"] == "needs-details" else "It's in a change waiting for your yes."))
            elif said := self._photo_on_product(sha): self._reply(head + said)
            else:
                code = self._photo_row(sha, msg, now)
                self._reply(f"{head}{PHOTO_QUESTION} Reply with the code {q(code)}.")
                if self.labels is not None: self._label_jobs.append((code, sha, self.db.execute("SELECT last_insert_rowid()").fetchone()[0]))
        skipped = "I did not read the caption because there is more than one photo. " if msg.text.replace("\ufffc", "").strip() else ""
        self._reply(skipped + "Reply to each draft with its code, place and description.")
        return "photo-drafts"

    def _read_label(self, code, sha, reply_id):  # AV1537-15: a read label joins the waiting question; never ops
        from hass.content_model import CATEGORIES
        job = reply_id if code is None else None
        worker, deadline = None, 0.0
        if job:
            msg, _, _ = job
            if photo_polish.enabled(self.settings):
                self.stage("style-start", msg.provider_id)
                deadline = time.monotonic() + photo_polish.TIMEOUT_S
                worker = photo_polish.start(self.settings["mediaRoot"], sha, log=self.log, transport=self.polish_transport)
            self.stage("label-start", msg.provider_id)
        try:
            web = Path(media.web_copy(self.settings["mediaRoot"], sha)["path"]).read_bytes()  # metadata-free copy only
            products = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content").products
            context = ""
            if job:
                msg, _, now = job
                req = self.requests.get(msg.chat, now)
                context = " ".join(req["texts"]) if req else ""
            found = (self.labels.read(web, CATEGORIES, owner_text=context)
                     if context and isinstance(self.labels, label_reader.LabelReader) else self.labels.read(web, CATEGORIES))
            if found:
                from hass import product_claims
                product_claims.remember(self.settings["mediaRoot"], sha, found)
        except Exception: found, products = {}, []  # noqa: BLE001 - one honest missing-detail preview, not a silent reading state
        category = found.get("category")
        if job:
            msg, request_id, now = job
            self.stage("label-end", msg.provider_id, fallback=getattr(self.labels, "last_fallback", False) is True,
                       error=getattr(self.labels, "last_primary_error", None) or getattr(self.labels, "last_error", None))
            if worker is not None:
                # Label and styling run in parallel outside the write lock.
                worker.join(max(0, deadline - time.monotonic()))
            if photo_polish.enabled(self.settings):
                self.stage("style-ready", msg.provider_id)
            if category == "pantry" and re.search(r"\b(?:glue|adhesive|hardware|screws?|nails?)\b", found.get("product_type", "") + " " + found.get("name", ""), re.I):
                category = "general"
            with self._answer_to(msg.chat), self._tx():
                req = self.requests.get(msg.chat, now)
                if (req is None or req["request_id"] != request_id or req["state"] != "open"
                        or req["skill"] != "item.add" or req["attachments"][-1:] != [sha]): return
                slots = {**req["slots"], "intake": {**req["slots"].get("intake", {}), "photo_details": found,
                                                   "category_choice": category or "general",
                                                   "reading_photo": False, "simple": True}}
                return self.dispatch._advance(Inbound(**{**vars(msg), "text": ""}), now, req,
                                              self.dispatch.registry.get("item.add"), {"intake": slots["intake"]}, None, resolved=True)
            return
        line = label_reader.question(found, self._makers(), products) if found else None  # AVB-10: matching records
        with self._tx():
            if line and self.db.execute("UPDATE drafts SET summary = summary || ? WHERE code = ? AND state = "
                                        "'needs-details'", (" " + line, code)).rowcount:
                self.db.execute("UPDATE outbox SET text = text || ? WHERE id = ? AND sent_at IS NULL", (" " + line, reply_id))

    def _outcome(self, row, out, now):
        """Store the apply result and its reply in one transaction (before anything is sent)."""
        with self._answer_to(_row_chat(row)): return self._outcome_to(row, out, now)

    def _reprepare(self, row):
        ops = json.loads(row['ops_json'])
        out = self.editor.reprepare(row['change_id'], ops) if hasattr(self.editor, 'reprepare') else self.editor.prepare(ops)
        if str(row['reason'] or '').startswith('again:') and out.get('result') == 'ok' and not self._again_same(row, out['draft']):
            return {'result': 'refused', 'reason': AGAIN_DRIFT.format(code=row['reason'][6:]), 'again-drift': True}  # AV2152-03: never a changed outcome
        return out

    def _row_live_site(self, row):
        doc = self.editor.show(row['change_id'])
        binding = (doc.get('draft') or doc.get('change') or {}).get('environment', {})
        return None if binding.get('env') == 'sandbox' else self.settings.get('liveSite')

    def _outcome_to(self, row, out, now):
        result = out.get("result")
        if self.npp is not None and self.npp.outcome(row["row_id"], now, result in ("applied", "already-applied")):
            if result not in ("applied", "already-applied"):
                # Do not give a failed/stale NPP draft a legacy approval path or resend its old preview.
                self._move(row, "failed", reason=_reason(out))
                self._audit("failed", row, "stale" if result == "stale" else "failed")
                self._reply("I couldn't save that card. Nothing changed. Please send the photo again for a fresh card.")
                return
        if result in ("applied", "already-applied"):
            self._move(row, "applied", commit=out.get("commit"))
            self._audit("undone" if _is_undo(row) else "applied", row, commit=out.get("commit"))  # AVB-10
            if self.dispatch is not None and not _is_undo(row): self.dispatch.intake_applied(row["code"], now)  # HASS-INTAKE-2: his private intake record is saved now, not before his yes
            for call in json.loads(row["ops_json"]):  # an applied undo closes the draft it reverted
                if call.get("op") == "history.revert":
                    for orig in self._drafts("change_id = ? AND state IN ('applied', 'verified')",
                                             call["args"].get("changeId")):
                        self._move(orig, "reverted", reason=f"undone by {row['code']}")
                        if self.dispatch is not None: self.dispatch.intake_undone(orig["code"], now)  # HASS-INTAKE-2
            if self.previewer is None or self._row_live_site(row):
                self._reply(self._with_question(answers.applied_text(row["code"], row["summary"], live_site=self._row_live_site(row))))
            # with a previewer the reply waits for verify(): nothing says it worked before it is checked
        elif result == "env-changed":
            again = self._reprepare(row)
            new = self._propose(again["draft"], row["sender"], now) if again["result"] == "ok" else None
            new = self._carry_again(row, new)
            self._move(row, "rejected" if row["state"] == "proposed" else "failed", reason="env-changed",
                       **({"replaced_by": new["code"]} if new else {}))
            if new:
                self._proposal_reply(new, again["draft"], "Things changed since that draft, so I've written a fresh one. Please check it:\n")
            else:
                self._reply("Things changed since that draft, so nothing changed. Please ask for a fresh draft when the target is ready.")
        elif result == "stale":
            self._audit("failed", row, "stale")  # AVB-10: a re-written draft below keeps the same action
            again = self._reprepare(row)
            if again["result"] == "ok":
                new = self._propose(again["draft"], row["sender"], now, like=row)
                new = self._carry_again(row, new)
                self._move(row, "rejected", reason="stale", replaced_by=new["code"])
                self._proposal_reply(new, again["draft"], "The website changed while that was waiting, so I've written it up again. "
                                                          "Please look it over:\n")
            else:
                self._move(row, "rejected", reason="stale")
                self._reply("The website changed while that was waiting, and now that change would end differently, so nothing changed. "
                            f"Send the change again (it was written up again from {q(row['reason'][6:])})." if again.get("again-drift") else
                            "The website changed while that was waiting, and now I can't make this change. Nothing changed. "
                            + self._plain(_reason(again)))
        else:
            refused = self.settings.get("liveSite") and answers.live_refused(out.get("reason"))  # HASS-LIVE-PLAN-1: the real reason, in words
            # A failed draft is never approved again (yes only targets `proposed`), so recovery is a fresh proposal with
            # its own code, written up from the same change; the owner's next yes (and code, when needed) approves that one.
            again = None if refused else self._reprepare(row)
            self._audit("failed", row, "policy" if refused else result if result in ("refused", "busy") else "failed")  # AVB-10
            new = self._propose(again["draft"], row["sender"], now, like=row) if again and again["result"] == "ok" else None
            new = self._carry_again(row, new)
            self._move(row, "failed", reason=_reason(out), **({"replaced_by": new["code"]} if new else {}))
            self._problem("error", "save-failed")
            if refused: self._reply(refused)
            elif new:
                self._proposal_reply(new, again["draft"], "I couldn't save that change, so nothing changed. "
                                                          "I've written it up again so you can try once more:\n")
            else:
                self._reply("I couldn't save that change, so nothing changed. Please send me the request again in a minute.")

    def recover(self) -> list:
        """Settle drafts left `approved` by a crash from the editor's change record, then verify (once) any applied
        draft with no verification record. Never calls apply again."""
        rows = self._drafts("state = 'approved'")
        if rows:
            if hasattr(self.editor, "recover"): self.editor.recover()  # settles journals; never re-applies
            with self._tx():
                for row in rows:
                    change = self.editor.show(row["change_id"]).get("change") or {}
                    if change.get("state") == "applied":
                        self._outcome(row, {"result": "applied", "commit": change.get("commit")}, self._now())
                    else:
                        self._move(row, "failed", reason=INTERRUPTED)
                        self._audit("failed", row, "interrupted")  # AVB-10
                        with self._answer_to(_row_chat(row)): self._reply(answers.recovered_text(row["code"], live_site=self._row_live_site(row)))
        self._verify_pending()
        return [self._row(r["row_id"])["state"] for r in rows]

    # -- H06: checked results, history and undo ------------------------------------------------------------------
    def verify(self, row):
        """(screenshot path, None) when the worktree is current, the migration checks pass and the result
        screenshot's checks pass; otherwise (None, error)."""
        wt = editor_mod._load(str(self.sdir))[2]
        try:
            content = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
            stale = sitegen.stale_paths(content, wt)
        except ContentError as exc:
            return None, "; ".join(exc.problems)
        problems = [f"generated file out of date: {p}" for p in stale] + migration_check.run_checks(wt)[0]
        if problems: return None, "; ".join(problems)
        change = self.editor.show(row["change_id"]).get("change") or {}
        if not change.get("records"): return None, "no change record"
        files = {p: (wt / p).read_bytes() for p in editor_mod.GENERATED_PATHS}  # the committed files
        picked, png, unshown = [], None, []  # AV1737-08: each touched record with a distinct target, in order
        for record in change["records"]:
            target = preview_mod.target_for(record, shop_today(), store=content.store)  # the store the committed files were generated from
            if all(target != t for _r, t in picked): picked.append((record, target))
        for i, (record, target) in enumerate(picked[:VERIFY_MAX], 1):
            shot = self.previewer.capture(files, target, self.sdir / "screenshots" /
                                          f"{row['change_id']}-result{'' if i == 1 else f'-{i}'}.png")
            if not shot["ok"]: return None, f"{record['collection']} {record['key']}: {shot['error']}"
            png = shot["png"] if i == 1 else png  # the reply keeps the first record's screenshot
            unshown.append(bool(shot.get("unshown")))  # AV1222-06: a route /hike does not show was not checked
        if picked[VERIFY_MAX:]:
            print(f"verify {row['change_id']}: over {VERIFY_MAX} records, not checked: "
                  + ", ".join(f"{r['collection']} {r['key']}" for r, _t in picked[VERIFY_MAX:]), file=sys.stderr)
        return png, None, unshown

    def _verify_pending(self):
        if self.previewer is None: return
        for row in self._drafts("state = 'applied' AND checked_at IS NULL"):
            png, error, *flags = self.verify(row)  # outside the transaction; the result and reply are stored together
            unshown = flags[0] if flags else []
            with self._tx(), self._answer_to(_row_chat(row)):
                if png:
                    self._move(row, "verified", screenshot=png, checked_at=_iso(self._now()))
                    self._audit("verified", row)  # AVB-10
                    text = answers.applied_text(row["code"], row["summary"], checked=not (unshown and all(unshown)), live_site=self._row_live_site(row))
                    if not self._row_live_site(row): self._reply(self._with_question(text + ("\n" + answers.ROUTE_UNSHOWN if any(unshown) else "")), [png])
                else:  # the raw diagnostic stays on the row; the owner gets plain words (SHOP-4)
                    self.db.execute("UPDATE drafts SET reason = ?, checked_at = ? WHERE row_id = ?",
                                    (f"not verified: {error}", _iso(self._now()), row["row_id"]))
                    self._audit("verified", row, "not-verified")  # AVB-10: the diagnostic stays on the row, never here
                    if not self._row_live_site(row): self._reply(self._with_question(answers.applied_text(row["code"], row["summary"], error=error, live_site=self._row_live_site(row))))

    def screenshot(self, change_id) -> str | None:
        row = self.db.execute("SELECT screenshot FROM drafts WHERE change_id = ? AND state IN ('applied', 'verified') "
                              "AND screenshot IS NOT NULL ORDER BY row_id DESC LIMIT 1", (change_id,)).fetchone()
        return row[0] if row else None

    def _visible_undo(self, r) -> bool:
        """`undo` looks at this chat's own changes; with several owners at the whole site's (one site, one last change)."""
        return self._shared or self._mine(r)

    def _audit_action(self, row):
        """The audit action of a draft row, or None when it cannot be read (an undo is never stopped for it)."""
        try: return self._audit_of(row)[0]
        except Exception: return None  # noqa: BLE001,E701

    def _command(self, msg, now, verb, code) -> str:
        if verb == "help" and code is not None:  # AV1052-12: help <command>: that command's lines; nothing else happens
            self._reply(help_detail(code))
            return "help"
        if verb == "help":
            registry = self.dispatch.registry if self.dispatch else None
            self._reply(HELP_TEXT + "\n\n" + capabilities.help_section(registry) + ("\n\n" + self.till.HELP if self.till is not None and self.till.engine is not None else ""), long_ok=True)  # HASS-CLOVER-4: till words when it can change the till
            return "help"
        if verb in ("status", "pause", "resume"): return self._control(msg, now, verb)
        if verb == "find": return self._find(code) if 1 <= len(code) <= FIND_TEXT_MAX else (self._reply(FIND_USAGE), "find")[1]
        if verb == "show": return self._reply(*self._show(code, now), long_ok=True) or "show"
        if verb == "report": return self._report(msg, now)
        if verb == "post": return self._post(code)
        if verb == "look": return self._look(code)  # AV1922-01
        if verb == "margin": return self._margin(code)
        if verb == "hidden": return self._hidden()
        if verb == "listing": return self._listing(code)
        if verb == "photos": return self._photos_to_take()
        if verb == "shelf": return self._shelf(code, now)  # AV1052-05
        if verb == "backlog": return self._backlog_list()  # SKILLS-FW-3
        if verb == "costs": return self._costs()  # AV2137-06
        if verb == "held": return self._held()  # AV2137-07
        if verb == "history" and code is not None: return self._history_search(code)
        if verb == "again": return self._again(msg, now, code)  # AV2152-03
        if verb == "history":
            lines = self._history_lines(HISTORY_MAX)
            self._reply("\n".join(["Here's what we changed lately:"] + lines) if lines else "We haven't made any changes yet.", long_ok=True)
            return "history"
        if verb == "undo" and code is None and msg.text.strip().lower().rstrip(".!") == "undo":
            # Bare undo refers to this owner's latest waiting listing, not an older saved change.
            for row in reversed(self._drafts("state = 'proposed'")):
                if (self._mine(row) and self._expiry(row) > now
                        and any(op["op"] == "product.add" for op in json.loads(row["ops_json"]))):
                    self._reply(f"Nothing is published. Keep it, change something, or say no {row['code']}.")
                    return "question"
        done = [r for r in self._drafts("change_id IS NOT NULL AND \"commit\" IS NOT NULL")  # AV0022-07: skip undos
                if self._visible_undo(r) and (code is None and r["state"] in ("applied", "verified") and not _is_undo(r) or r["code"] == code)]
        # HASS-LIVE-PLAN-1: only the asking owner's own changes (by chat) can be taken back, with or without a code
        if not done:
            note = self._waiting_note(now)  # AV2007-02: nothing saved, but a change may still be waiting for its yes
            if code: self._reply("I don't have a change with that code to undo." + (" " + note if note else ""), long_ok=True)
            else: self._reply("Nothing has been saved yet. " + note if note else "There's nothing to undo.", long_ok=True)
            return "no-target"
        target = done[-1]
        if _is_undo(target) or self._has_revert(target):  # AV2137-01: an undo of an undo is never drafted; say how to bring the change back
            link = [r for r in self._drafts("state = 'reverted'") if self._mine(r) and r["change_id"] and any(
                c.get("op") == "history.revert" and (c.get("args") or {}).get("changeId") == r["change_id"] for c in json.loads(target["ops_json"]))]
            self._reply("That code is for an undo. To bring the change back, send " + q("again " + link[0]["code"]) + "." if len(link) == 1
                        else "That code is for an undo. To bring the change back, send " + q("again") + " with the original change's code.")
            return "no-target"
        theirs = self._shared and not self._mine(target)  # HASS-OWNERS-2: the site's last change was another owner's
        if theirs and code is None:  # a bare `undo` never reaches another owner's work: it says whose it is, and how to ask for it
            self._reply(f"The last change on the website was {self._whose(target['chat'], False)}: {q(target['summary'])}. I haven't undone anything. "
                        f"If you do want it undone, say {q('undo ' + target['code'])}.", long_ok=True)
            return "undo-other"
        if (busy := self._writer_busy(now)) is not None: return self._busy_reply(busy)
        out = self.editor.prepare([{"op": "history.revert", "args": {"changeId": target["change_id"]}}])
        if out["result"] != "ok":
            self._reply(self._plain(_reason(out), "undo that"))
            return "not-drafted"
        same = [r for r in self._drafts("state = 'proposed' AND change_id = ?", out["draft"]["change_id"]) if self._mine(r)]
        row = same[0] if same else self._propose(out["draft"], msg.sender, now, undo_of=self._audit_action(target))
        note = self._waiting_note(now, exclude=out["draft"]["change_id"])  # AV2007-02: the change waiting before this undo, not the undo itself
        self._proposal_reply(row, out["draft"], (note + "\n\n" if note else "") +
                             (f"To undo {self._whose(target['chat'], False)}, I'd change it back:\n" if theirs else "To undo that, I'd change it back:\n"))
        return "proposed"

    # -- H17: status, pause changes, resume changes ----------------------------------------------------------------
    def _paused(self):
        """When changes were paused (ISO time), or None. No control table yet means never paused."""
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'control'").fetchone():
            return None
        row = self.db.execute("SELECT set_at FROM control WHERE name = 'paused'").fetchone()
        return row["set_at"] if row else None

    def _install(self, row):
        """SHOP-4: the editor change record's SHOP-2 `install` entry for a draft row; None when there is none."""
        try:
            return (self.editor.show(row["change_id"]).get("change") or {}).get("install") if row["change_id"] else None
        except (OSError, ValueError, AttributeError, editor_mod.UnsafeState):
            return None

    def _queue(self, msg) -> dict:
        """SHOP-4: drafts waiting for an OK plus inbox messages not read yet (this one excluded; inbox opened
        read-only as _photo_lines does), and approvals already under way."""
        unread, path = 0, self.sdir / "inbox.sqlite3"
        if path.is_file():
            try:
                with contextlib.closing(sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True, timeout=1)) as db:
                    unread = db.execute("SELECT COUNT(*) FROM inbound WHERE state = 'pending' AND provider_id != ?",
                                        (msg.provider_id,)).fetchone()[0]
            except sqlite3.Error:
                unread = 0
        waiting = [r for r in self._drafts("state = 'proposed'") if self._expiry(r) > self._now() and self._visible(r)]
        return {"waiting": len(waiting) + unread, "applying": [r["code"] for r in self._drafts("state = 'approved'")]}

