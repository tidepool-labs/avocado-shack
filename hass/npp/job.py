"""Durable listing jobs. Only the conversation thread owns SQLite and queues replies.

Stage port (assembled by NPP-G): takes_turn(text, state) is a cheap deterministic routing predicate;
plan(work) returns Plan(questions=...) or a public, JSON-safe Plan(listing=...); render(work, listing)
returns a validated Card or a retake/refusal Plan. cap(work, listing) is the bounded local fallback,
never a wait for an outstanding future. Work.request is private (finance included); stages must
pass only eligible projections to remote readers. Stages do not write job state or send messages.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import re

from hass import photo_polish
from hass.npp.receipt import Artifacts, confirmation, instant, read_artifact
from hass.skills import openreq

SCHEMA = """
CREATE TABLE IF NOT EXISTS npp_jobs(
 job_id TEXT PRIMARY KEY, chat TEXT NOT NULL, sender TEXT NOT NULL, photo_sha TEXT NOT NULL,
 open_request_id INTEGER NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL, closed_at TEXT,
 polish_started_at TEXT, polish_eligible INTEGER NOT NULL DEFAULT 0, current_version INTEGER, approval_row INTEGER UNIQUE);
CREATE INDEX IF NOT EXISTS npp_open_chat ON npp_jobs(chat) WHERE closed_at IS NULL;
CREATE TABLE IF NOT EXISTS npp_turns(
 provider_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, kind TEXT NOT NULL, accepted_at TEXT NOT NULL,
 segment_id INTEGER, reply_outbox_id INTEGER, receipt_refs TEXT, reply_clock TEXT);
CREATE INDEX IF NOT EXISTS npp_segment_turns ON npp_turns(segment_id);
CREATE TABLE IF NOT EXISTS npp_questions(
 job_id TEXT NOT NULL, qid TEXT NOT NULL, asked_outbox_id INTEGER NOT NULL, asked_at TEXT NOT NULL,
 answered_by TEXT, answered_at TEXT, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS npp_answers(
 job_id TEXT NOT NULL, qid TEXT NOT NULL, provider_id TEXT NOT NULL UNIQUE,
 answer INTEGER NOT NULL, accepted_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS npp_segments(
 segment_id INTEGER PRIMARY KEY, job_id TEXT NOT NULL, started_by TEXT NOT NULL, accepted_at TEXT NOT NULL,
 deadline_at TEXT NOT NULL, ended_at TEXT, outcome TEXT, revision INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS npp_one_segment ON npp_segments(job_id) WHERE ended_at IS NULL;
CREATE TABLE IF NOT EXISTS npp_versions(
 job_id TEXT NOT NULL, n INTEGER NOT NULL, parent_n INTEGER, segment_id INTEGER NOT NULL UNIQUE,
 listing_json TEXT NOT NULL, listing_sha TEXT NOT NULL, patch_json TEXT NOT NULL,
 image_variant TEXT, image_path TEXT, image_sha256 TEXT, change_id TEXT, draft_hash TEXT, base TEXT,
 card_png_sha TEXT, outbox_id INTEGER UNIQUE, queued_at TEXT, state TEXT NOT NULL,
 delivered_at TEXT, transport_message_id TEXT, PRIMARY KEY(job_id,n));
CREATE TABLE IF NOT EXISTS npp_approvals(
 approval_id INTEGER PRIMARY KEY, job_id TEXT NOT NULL, n INTEGER NOT NULL, outbox_id INTEGER NOT NULL,
 transport_message_id TEXT, UNIQUE(job_id,n));
CREATE TABLE IF NOT EXISTS npp_polishes(photo_sha TEXT PRIMARY KEY, started_at TEXT NOT NULL);
"""
ACTIVE = "'working','asking','card_out','editing','retake'"
YES = re.compile(r"yes ([0-9a-f]{4,12})(?:-([1-9][0-9]{0,8}))?", re.I)
NO = re.compile(r"(?:no|cancel)(?: ([0-9a-f]{4,12})(?:-[1-9][0-9]{0,8})?)?", re.I)
EXPIRED = "That question expired. Please send the photo again to start over."
ITEM_IDENTITY = re.compile(r"\s*(?:it(?: is|[’']s)|(?:the )?(?:item|product)(?: is|:))\s+([^;\n]+)", re.I)


class CardSendFailed(Exception):
    """A tracked adapter send failed; don't mark the card sent or block later text."""


def owner_item(text):
    match = ITEM_IDENTITY.fullmatch(text)
    return match[1] if match else None


def dump(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def job_photos(db, job):
    """Every original photo sha an open job reads: its photo_sha plus the attachments of its stored request.

    The request is read through OpenRequests, the same accessor Jobs.request uses, so these are the shas Jobs.pump
    hands the stages as Work.request["attachments"]. ``db`` rows must be sqlite3.Row. A request that is missing or
    cannot be read raises ValueError (callers fail closed); expiry is ignored: a restore must keep what the row names.
    """
    sha = job["photo_sha"]
    if not isinstance(sha, str):
        raise ValueError("photo sha unreadable")
    store = openreq.OpenRequests(db)
    row = store._row("request_id = ?", job["open_request_id"])
    if row is None:
        raise ValueError("request missing")
    try:
        if not isinstance(json.loads(row["attachments_json"]), list):  # _view would quietly read a non-list as no photos
            raise ValueError
        shas = store._view(row, datetime(1970, 1, 1, tzinfo=timezone.utc))["attachments"]
    except (TypeError, ValueError, KeyError, RecursionError):
        raise ValueError("request unreadable") from None
    if not all(isinstance(s, str) and openreq.SHA_RE.fullmatch(s) for s in shas):
        raise ValueError("request unreadable")
    return list(dict.fromkeys([sha, *shas]))


@dataclass(frozen=True)
class Plan:
    listing: dict | None = None
    patch: dict | None = None
    questions: tuple = ()  # (question id, rendered sentence), limited by the pinned reply rules
    retake: str | None = None
    identified: bool = False  # allow styling during a price question, never for an unidentified photo


@dataclass(frozen=True)
class Card:
    draft: dict  # exact checked editor draft; publish is never a second lookup of the latest draft
    png: bytes
    variant: str
    image_path: str
    image_sha256: str
    note: str = ""  # text inside the single bounded fallback bracket
    candidate: bool = False  # older injected fixture stages supply a draft they already prepared


@dataclass(frozen=True)
class Work:
    job_id: str
    request: dict
    parent: dict | None
    deadline: object
    answers: dict[str, bool] = field(default_factory=dict)
    ask_counts: dict[str, int] = field(default_factory=dict)
    answered: tuple[str, ...] = ()


class Jobs:
    def __init__(self, conv, stages, pinned, executor=None, receipt_for=None):
        self.c, self.db, self.stages = conv, conv.db, stages
        self.artifacts = Artifacts(conv.settings["mediaRoot"])
        self.pins, _, self.replies = pinned
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="hass-npp")
        self.receipt_for = receipt_for
        self.running = None
        self.polishing = {}  # only this process's starts; never reconstructed after restart
        self.dirty = set()
        self.db.executescript(SCHEMA)

    def one(self, sql, *args):
        return self.db.execute(sql, args).fetchone()

    def version(self, job, n):
        return self.one("SELECT * FROM npp_versions WHERE job_id=? AND n=?", job, n)

    def active(self, chat, sender):
        return self.one(f"SELECT * FROM npp_jobs WHERE chat=? AND sender=? AND state IN ({ACTIVE})", chat, sender)

    def needs_retry(self, job):
        last = self.one("SELECT outcome FROM npp_segments WHERE job_id=? ORDER BY segment_id DESC LIMIT 1", job["job_id"])
        version = self.version(job["job_id"], job["current_version"])
        return bool(last and last[0] == "render-failed" or version and version["state"] == "queued")

    def taken(self, code):
        return self.one("SELECT 1 FROM npp_jobs WHERE job_id=?", code) is not None

    def turn(self, job, msg, kind, accepted, segment=None, refs=None):
        self.db.execute("INSERT INTO npp_turns VALUES (?,?,?,?,?,NULL,?,?)",
                        (msg.provider_id, job, kind, accepted.isoformat(), segment, refs, msg.received_at))

    def reply(self, job, text, pid, attachments=()):
        reply = self.one("SELECT reply_clock FROM npp_turns WHERE provider_id=?", pid)
        row = self.c.outbox.add(job["chat"], text, attachments, reply[0], ids_ok=bool(attachments))
        self.db.execute("UPDATE npp_turns SET reply_outbox_id=? WHERE provider_id=?", (row, pid))
        self.dirty.add(job["job_id"])
        return row

    def request(self, job, now):
        req = self.c.requests.get(job["chat"], now)
        return req if req and req["request_id"] == job["open_request_id"] else None

    def close(self, job, state, now):
        jid = job["job_id"]
        self.db.execute("UPDATE npp_jobs SET state=?,closed_at=? WHERE job_id=?", (state, now.isoformat(), jid))
        self.db.execute("UPDATE npp_segments SET ended_at=?, outcome=? WHERE job_id=? AND ended_at IS NULL",
                        (now.isoformat(), state, jid))
        self.db.execute("UPDATE npp_questions SET state='expired' WHERE job_id=? AND state='open'", (jid,))
        self.db.execute("UPDATE npp_versions SET state='superseded' WHERE job_id=? AND state IN ('building','queued','delivered')", (jid,))
        if self.request(job, now):
            self.c.requests.mark(job["open_request_id"], "closed", now)
        self.dirty.add(jid)

    def input(self, msg, sender, accepted, now, finance, photos=(), *, replace_price=False):
        """Save accepted input and fold before freeze, or supersede a frozen card atomically."""
        job = self.active(msg.chat, sender)
        req = self.request(job, accepted) if job else None
        if job and not req:
            self.close(job, "expired", now)
            if not photos:
                self.turn(job["job_id"], msg, "answer", accepted)
                self.reply(job, EXPIRED, msg.provider_id)
                return "npp-expired"
            job = None
        photos = list(photos)
        if job is None and not photos:
            return None
        if job is None and self.c.requests.get(msg.chat, now):
            return None  # never replace an unrelated waiting request
        jid = job["job_id"] if job else self.c._code(hashlib.sha256(msg.provider_id.encode()).hexdigest())
        req = req or {"request_id": None, "texts": [], "slots": {}, "attachments": []}
        old = req["slots"].get("intake", {})
        price, sold_by, span = None, None, None
        if replace_price and finance.price_span:
            price, _, unit = finance.selling_price.partition(" ")
            sold_by, span = {"each": "item", "per lb": "pound"}.get(unit), finance.price_span
        elif not replace_price and old.get("price_span"):
            price, sold_by, span = (old.get(key) for key in ("price", "sold_by", "price_span"))
        private = {
            "price": price, "sold_by": sold_by, "price_span": span,
            # Keep the accumulated private screen across edits; an edit never declassifies earlier costs/counts.
            "private": sorted(set(old.get("private", ())) | {format(Decimal(n).normalize(), "f") for n in finance.private}),
            "has_cost": bool(old.get("has_cost") or finance.has_cost),
            "has_qty": bool(old.get("has_qty") or finance.has_qty),
        }
        req_id = self.c.requests.put(msg.chat, msg.provider_id, accepted, skill="npp", request_id=req["request_id"],
                                     texts=[*req["texts"], finance.public_words], slots={"intake": private}, turns=8,
                                     attachments=photos or req["attachments"])
        if job is None:
            self.db.execute("INSERT INTO npp_jobs(job_id,chat,sender,photo_sha,open_request_id,state,created_at) "
                            "VALUES (?,?,?,?,?,'working',?)", (jid, msg.chat, sender, photos[0], req_id, accepted.isoformat()))
        elif photos and photos[0] != job["photo_sha"]:
            self.db.execute("UPDATE npp_jobs SET photo_sha=?,polish_started_at=NULL,polish_eligible=0 WHERE job_id=?", (photos[0], jid))
        if job and (photos or owner_item(finance.public_words)):
            # A new identification invalidates both an outstanding duplicate ask
            # and an earlier confirmation; neither belongs to the new item.
            self.db.execute("UPDATE npp_questions SET state='expired' WHERE job_id=? AND qid='duplicate' "
                            "AND state IN ('open','answered')", (jid,))
        if job and job["state"] == "asking" and not photos:
            # The next plan can leave these open (an unrelated/insufficient answer) or mark the resolved ids.
            kind = "answer"
        else:
            kind = "photo" if photos and job else "start" if not job else "edit"
        self._resume(jid, job, msg, kind, accepted, now)
        return "npp-working"

    def answer(self, job, msg, polarity, accepted, now):
        """Bind an exact owner answer inside the caller's conversation transaction."""
        jid = job["job_id"]
        questions = self.db.execute("SELECT * FROM npp_questions WHERE job_id=? AND state='open'", (jid,)).fetchall()
        if len(questions) != 1 or accepted is None:
            return None
        q = questions[0]
        asked_at = instant(q["asked_at"])
        if (q["qid"] not in ("duplicate", "near_maker") or asked_at is None or accepted < asked_at
                or not self.one("SELECT 1 FROM outbox WHERE id=? AND chat=?", q["asked_outbox_id"], job["chat"])
                or not self.request(job, accepted) or not self.request(job, now)):
            return None
        self.db.execute("INSERT INTO npp_answers VALUES (?,?,?,?,?)", (jid, q["qid"], msg.provider_id, int(polarity), accepted.isoformat()))
        self.db.execute("UPDATE npp_questions SET state='answered',answered_by=?,answered_at=? "
                        "WHERE job_id=? AND qid=? AND state='open'", (msg.provider_id, now.isoformat(), jid, q["qid"]))
        if q["qid"] == "duplicate" and not polarity:
            self.turn(jid, msg, "answer", accepted)
            self.close(job, "cancelled", now)
            self.reply(job, "Okay, I've cancelled that. Nothing changed.", msg.provider_id)
            return "cancelled"
        self._resume(jid, job, msg, "answer", accepted, now)
        return "npp-working"

    def _resume(self, jid, job, msg, kind, accepted, now):
        seg = self.one("SELECT * FROM npp_segments WHERE job_id=? AND ended_at IS NULL", jid)
        frozen = seg and self.one("SELECT 1 FROM npp_versions WHERE segment_id=?", seg["segment_id"])
        if frozen:
            self.end(seg, now, "superseded")
            seg = None
        if seg:
            sid = seg["segment_id"]
            self.db.execute("UPDATE npp_segments SET revision=revision+1 WHERE segment_id=?", (sid,))
        else:
            self.db.execute("UPDATE npp_versions SET state='superseded' WHERE job_id=? AND state IN ('queued','delivered','building')", (jid,))
            sid = self.db.execute("INSERT INTO npp_segments(job_id,started_by,accepted_at,deadline_at) VALUES (?,?,?,?)",
                                  (jid, msg.provider_id, accepted.isoformat(),
                                   (accepted + timedelta(seconds=self.pins["segment"]["cap_s"])).isoformat())).lastrowid
        if job:
            self.db.execute("UPDATE npp_jobs SET state=? WHERE job_id=?",
                            ("editing" if job["current_version"] else "working", jid))
        self.turn(jid, msg, kind, accepted, sid)
        self.dirty.add(jid)

    def end(self, segment, now, outcome):
        self.db.execute("UPDATE npp_segments SET ended_at=?,outcome=? WHERE segment_id=?",
                        (now.isoformat(), outcome, segment["segment_id"]))

    def freeze(self, job, segment, plan):
        n = (job["current_version"] or 0) + 1
        listing = dump(plan.listing)
        self.db.execute("INSERT INTO npp_versions(job_id,n,parent_n,segment_id,listing_json,listing_sha,patch_json,state) "
                        "VALUES (?,?,?,?,?,?,?,'building')", (job["job_id"], n, job["current_version"], segment["segment_id"],
                                                               listing, hashlib.sha256(listing.encode()).hexdigest(), dump(plan.patch or {})))
        self.db.execute("UPDATE npp_jobs SET current_version=? WHERE job_id=?", (n, job["job_id"]))
        return self.version(job["job_id"], n)

    def finish(self, job, seg, version, result, now):
        jid = job["job_id"]
        pid = self.one("SELECT provider_id FROM npp_turns WHERE segment_id=? ORDER BY rowid DESC LIMIT 1", seg["segment_id"])[0]
        if isinstance(result, Card) and version:
            draft = result.draft
            prior = self.version(jid, version["parent_n"])
            picture = (result.variant, result.image_path, result.image_sha256)
            card_path, card_sha = None, None
            if (job["chat"] in self.c._owner_chats and result.variant in ("raw", "house", "polished")
                    and draft.get("assets", {}).get(result.image_path) == "sha256:" + result.image_sha256
                    and (prior is None or prior["image_sha256"] is None or self.one(
                        "SELECT 1 FROM npp_turns WHERE segment_id=? AND kind='photo'", seg["segment_id"])
                         or picture == tuple(prior[k] for k in ("image_variant", "image_path", "image_sha256")))
                    and (not self.c.settings.get("liveSite") or not self.c._live_reasons(draft))):
                try:
                    card_path, card_sha = self.artifacts.write_card(jid, result.png)
                except (OSError, ValueError):
                    pass
                if card_path is not None and result.candidate:
                    try:
                        if self.stages.persist(draft).get("result") != "ok":
                            card_path = None
                    except Exception:  # no stage details (including owner words) in logs
                        card_path = None
            if card_path is not None:
                text = self.replies["prompts"]["ready"].format(code=jid, n=version["n"])
                if result.note and len(result.note) + 2 <= self.replies["caps"]["bracket_max_chars"]:
                    text += f" ({result.note})"
                row = self.reply(job, text, pid, [str(card_path)])
                self.db.execute("UPDATE npp_versions SET image_variant=?,image_path=?,image_sha256=?,change_id=?,draft_hash=?,base=?,"
                                "card_png_sha=?,outbox_id=?,queued_at=?,state='queued' WHERE job_id=? AND n=?",
                                (*picture, draft["change_id"], draft["draft_hash"], draft["base"], card_sha, row, now.isoformat(), jid, version["n"]))
                self.end(seg, now, "card")
                self.answer_questions(jid, pid, now, ())
                return
        questions = []
        if isinstance(result, Plan):
            for qid, sentence in result.questions[:self.replies["caps"]["max_questions_per_reply"]]:
                if not self.one("SELECT 1 FROM npp_questions WHERE job_id=? AND qid=? AND state='answered'", jid, qid) and self.one(
                        "SELECT COUNT(*) FROM npp_questions WHERE job_id=? AND qid=? AND state!='expired'", jid, qid)[0] < 2:
                    questions.append((qid, sentence))
        if questions and len(text := " ".join(sentence for _, sentence in questions)) <= self.replies["caps"]["question_max_chars"]:
            outcome, state = "question", "asking"
            ids = [qid for qid, _ in questions]
            self.answer_questions(jid, pid, now, ids)
            row = self.reply(job, text, pid)
            self.db.executemany("INSERT INTO npp_questions VALUES (?,?,?,?,NULL,NULL,'open')", ((jid, qid, row, now.isoformat()) for qid in ids))
        else:
            outcome, state = ("retake", "retake") if isinstance(result, Plan) and result.retake else ("render-failed", "editing")
            text = result.retake if isinstance(result, Plan) and result.retake else self.replies["guards"]["render_failed"]
            self.reply(job, text, pid)
        if version:
            self.db.execute("UPDATE npp_versions SET state='superseded' WHERE job_id=? AND n=?", (jid, version["n"]))
        self.db.execute("UPDATE npp_jobs SET state=? WHERE job_id=?", (state, jid))
        self.end(seg, now, outcome)

    def answer_questions(self, jid, pid, now, still_open):
        for row in self.db.execute("SELECT DISTINCT qid FROM npp_questions WHERE job_id=? AND state='open'", (jid,)).fetchall():
            if row[0] not in still_open and row[0] not in ("duplicate", "near_maker"):
                self.db.execute("UPDATE npp_questions SET state='answered',answered_by=?,answered_at=? WHERE job_id=? AND qid=? AND state='open'",
                                (pid, now.isoformat(), jid, row[0]))

    def _polish(self, job, now):
        if not job["polish_eligible"] or not photo_polish.enabled(self.c.settings):
            return
        root, sha, jid = self.c.settings["mediaRoot"], job["photo_sha"], job["job_id"]
        if job["polish_started_at"] is None:
            with self.c._tx():
                launch = self.db.execute("INSERT OR IGNORE INTO npp_polishes VALUES (?,?)", (sha, now.isoformat())).rowcount
                self.db.execute("UPDATE npp_jobs SET polish_started_at=(SELECT started_at FROM npp_polishes WHERE photo_sha=?) "
                                "WHERE job_id=?", (sha, jid))
            if launch:
                self.polishing[sha] = now + timedelta(seconds=photo_polish.TIMEOUT_S)
                photo_polish.start(root, sha, log=self.c.log, transport=self.c.polish_transport)
                return
        if sha not in self.polishing or now >= self.polishing[sha]:
            if photo_polish.decision(root, sha) is None:
                photo_polish.polished(root, sha)
            self.polishing.pop(sha, None)

    def pump(self):
        """Advance durable work without waiting on the executor. A late result has no live segment/revision to commit to."""
        if self.stages is None:
            return
        now = self.c._now()
        for sha, deadline in list(self.polishing.items()):
            if now >= deadline:
                photo_polish.polished(self.c.settings["mediaRoot"], sha)
                self.polishing.pop(sha)
        jobs = self.db.execute(f"SELECT * FROM npp_jobs WHERE state IN ({ACTIVE}) ORDER BY rowid").fetchall()
        ready = self.running if self.running and self.running[1].done() else None
        if ready:
            self.running = None
        for job in jobs:
            jid = job["job_id"]
            req = self.request(job, now)
            if not req:
                with self.c._tx():
                    self.close(job, "expired", now)
                continue
            self._polish(job, now)
            seg = self.one("SELECT * FROM npp_segments WHERE job_id=? AND ended_at IS NULL", jid)
            if seg is None:
                continue
            version = self.one("SELECT * FROM npp_versions WHERE segment_id=?", seg["segment_id"])
            parent = self.version(jid, version["parent_n"] if version else job["current_version"])
            answers = {qid: bool(answer) for qid, answer in self.db.execute(
                "SELECT a.qid,a.answer FROM npp_answers a JOIN npp_questions q "
                "ON q.job_id=a.job_id AND q.qid=a.qid AND q.answered_by=a.provider_id WHERE a.job_id=? AND q.state='answered'", (jid,))}
            questions = self.db.execute("SELECT qid,state FROM npp_questions WHERE job_id=? AND state!='expired'", (jid,)).fetchall()
            counts = {}
            for qid, _ in questions:
                counts[qid] = counts.get(qid, 0) + 1
            work = Work(jid, req, dict(parent) if parent else None, instant(seg["deadline_at"]), answers,
                        counts, tuple(qid for qid, state in questions if state == 'answered'))
            listing = json.loads(version["listing_json"]) if version else None
            ticket = seg["segment_id"], seg["revision"], version["n"] if version else None
            if now >= work.deadline:
                # Do not consume even a completed future observed after the cap. The local fallback cannot wait for it.
                try:
                    if job["polish_eligible"] and photo_polish.enabled(self.c.settings):
                        photo_polish.polished(self.c.settings["mediaRoot"], job["photo_sha"])
                    result = self.stages.cap(work, listing)
                except Exception:
                    self.c._problem("error", "npp-cap-failed")
                    result = None
                with self.c._tx():
                    if isinstance(result, tuple):
                        plan, result = result
                        if not version and isinstance(plan, Plan) and plan.listing is not None and not plan.questions and not plan.retake:
                            version = self.freeze(job, seg, plan)
                    self.finish(job, seg, version, result, now)
            elif ready and ready[0] == ticket:
                try:
                    result = ready[1].result()
                except Exception:  # never log a stage exception carrying owner words
                    result = None
                    self.c._problem("error", "npp-stage-failed")
                with self.c._tx():
                    if isinstance(result, Plan) and (result.identified or result.listing is not None):
                        self.db.execute("UPDATE npp_jobs SET polish_eligible=1 WHERE job_id=?", (jid,))
                    if not version and isinstance(result, Plan) and result.listing is not None and not result.questions and not result.retake:
                        self.freeze(job, seg, result)
                    else:
                        self.finish(job, seg, version, result, now)
            elif self.running is None:
                fn, args = (self.stages.render, (work, listing)) if version else (self.stages.plan, (work,))
                self.running = ticket, self.executor.submit(fn, *args)
        self.write_receipts()

    def dispatch(self, adapter, row, text):
        """Only an explicit tracked sender may see a card. False means leave the outbox row alone."""
        v = self.one("SELECT v.*,j.state AS job_state,j.current_version,j.chat FROM npp_versions v "
                     "JOIN npp_jobs j USING(job_id) WHERE outbox_id=?", row["id"])
        if v is None:
            adapter.send(row["chat"], text, json.loads(row["attachments"]))
            return True
        if v["state"] != "queued" or v["job_state"] not in ("working", "editing") or v["n"] != v["current_version"]:
            return False
        send = getattr(adapter, "send_card", None)
        if not callable(send) or not callable(self.receipt_for):
            return False
        try:
            path = self.artifacts.card(v["job_id"], v["card_png_sha"])
            read_artifact(path)
        except (OSError, ValueError):
            return False
        try:
            send(row["id"], v["chat"], text, str(path), v["card_png_sha"])
        except Exception as error:
            raise CardSendFailed() from error
        return True

    def refresh_receipts(self):
        if self.receipt_for is None:
            return
        now = self.c._now()
        with self.c._tx():
            for v in self.db.execute("SELECT * FROM npp_versions WHERE outbox_id IS NOT NULL AND delivered_at IS NULL").fetchall():
                found = confirmation(self.receipt_for, v["outbox_id"], v["card_png_sha"], instant(v["queued_at"]), now)
                if not found:
                    continue
                at, guid = found
                jid, n = v["job_id"], v["n"]
                self.db.execute("UPDATE npp_versions SET delivered_at=?,transport_message_id=?,"
                                "state=CASE WHEN state='queued' THEN 'delivered' ELSE state END WHERE job_id=? AND n=?", (at.isoformat(), guid, jid, n))
                if v["state"] == "queued":
                    self.db.execute("UPDATE npp_jobs SET state='card_out' WHERE job_id=? AND current_version=? AND state IN ('working','editing')", (jid, n))
                self.dirty.add(jid)

    def select(self, job, msg, n, accepted, now):
        """Snapshot receipts predating host acceptance; never retarget a yes to a later receipt."""
        jid = job["job_id"]
        delivered = self.db.execute("SELECT * FROM npp_versions WHERE job_id=? AND delivered_at IS NOT NULL ORDER BY n", (jid,)).fetchall()
        before = [v for v in delivered if accepted is not None and (at := instant(v["delivered_at"])) and at < accepted]
        refs = dump([[v["n"], v["outbox_id"], v["delivered_at"]] for v in before])
        self.turn(jid, msg, "yes", accepted or now, refs=refs)
        if n is not None and n != job["current_version"] and self.version(jid, n):
            return "replaced", None
        if job["state"] in ("approved", "published", "publish_failed"):
            return "already-done", None
        sent = instant(msg.received_at)
        if self.receipt_for is None or job["state"] != "card_out" or not self.request(job, now) or not before:
            return "not_ready", None
        ref = msg.reply_to
        if ref not in (None, ""):
            # A reply to a message names its card exactly: the delivered receipt whose transport id it is, never a guess.
            hit = next((v for v in before if isinstance(ref, str) and ref and v["transport_message_id"] == ref), None)
            if hit is None:
                return "not_ready", None
            if hit["n"] != job["current_version"]:
                return "replaced", None
            if n not in (None, hit["n"]):
                return "which_card", None
            target = hit
        elif n is None and len(delivered) != 1:
            return "which_card" if len(before) > 1 else "not_ready", None
        else:
            target = before[-1]
        at = instant(target["delivered_at"])
        if (target["n"] != job["current_version"] or target["state"] != "delivered" or n not in (None, target["n"])
                or sent is None or at is None or sent <= at):
            return "not_ready", None
        return None, target

    def approve(self, job, version, approval, draft_row, now):
        jid, n = job["job_id"], version["n"]
        self.db.execute("INSERT INTO npp_approvals VALUES (?,?,?,?,?)",
                        (approval, jid, n, version["outbox_id"], version["transport_message_id"]))
        self.db.execute("UPDATE npp_versions SET state='approved' WHERE job_id=? AND n=?", (jid, n))
        self.db.execute("UPDATE npp_jobs SET approval_row=? WHERE job_id=?", (draft_row, jid))
        self.close(job, "approved", now)

    def outcome(self, row, now, succeeded):
        job = self.one("SELECT * FROM npp_jobs WHERE approval_row=?", row)
        if not job:
            return False
        self.close(job, "published" if succeeded else "publish_failed", now)
        return True

    def write_receipts(self):
        # Derived, observational records: IDs, times and digests only. Approval never reads a mutable JSON file.
        for jid in sorted(self.dirty):
            job = self.one("SELECT state,photo_sha,created_at,closed_at,polish_started_at FROM npp_jobs WHERE job_id=?", jid)
            attempts = [dict(row) for row in self.db.execute("SELECT accepted_at,ended_at,outcome FROM npp_segments WHERE job_id=? "
                                                              "ORDER BY segment_id DESC LIMIT 100", (jid,))]
            versions = [dict(row) for row in self.db.execute("SELECT n,listing_sha,image_variant,image_sha256,change_id,draft_hash,"
                                                             "card_png_sha,outbox_id,delivered_at,state FROM npp_versions WHERE job_id=? "
                                                             "ORDER BY n DESC LIMIT 100", (jid,))]
            try:
                self.artifacts.write_receipt(jid, {"job_id": jid, **dict(job), "segments": attempts, "versions": versions,
                                                    "asset_pins": self.pins["assets"]})
            except (OSError, ValueError):
                self.c._problem("error", "npp-receipt-write-failed")
        self.dirty.clear()
