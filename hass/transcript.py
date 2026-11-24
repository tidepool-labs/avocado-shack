"""Private append-only conversation events; export/stats never create or modify a store."""
import argparse
import contextlib
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time
from datetime import date, datetime, timezone

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hass import editor, memory  # noqa: E402

NAME = "transcript.sqlite3"
SCHEMA = """CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY, utc TEXT NOT NULL, chat TEXT NOT NULL, sender TEXT NOT NULL,
 direction TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL, attachments TEXT NOT NULL,
 provider_id TEXT, reply_to TEXT, disposition TEXT NOT NULL, draft_code TEXT,
 backend TEXT, model TEXT, latency_ms INTEGER);
 CREATE UNIQUE INDEX IF NOT EXISTS inbound_id ON events(provider_id) WHERE direction='in';"""


def append(state, **event):
    path = memory.private_db(editor.open_state(state), NAME)
    with contextlib.closing(sqlite3.connect(path, timeout=0.1)) as db, db:
        db.executescript(SCHEMA)
        fields = ','.join(event)
        db.execute(f"INSERT OR IGNORE INTO events({fields}) VALUES ({','.join('?' for _ in event)})", tuple(event.values()))


def safe(state, **event):
    try:
        append(state, **event)
    except Exception:  # Never print exception text: it can contain private data.
        logging.getLogger(__name__).error("ALERT transcript-write-failed")


def event(chat, sender, direction, kind, text, provider_id=None, reply_to=None, disposition="queued", attachments=(), **extra):
    return dict(utc=datetime.now(timezone.utc).isoformat(), chat=chat, sender=sender, direction=direction,
                kind=kind, text=text, attachments=json.dumps(list(attachments)), provider_id=provider_id,
                reply_to=reply_to, disposition=disposition, draft_code=None, backend=None, model=None, latency_ms=None) | extra


def npp_job(db, provider_id):
    """HRM-21 C1: the listing (job id) whose accepted NPP turn this inbound message is, else None. Never raises."""
    try:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='npp_turns'").fetchone():
            row = db.execute("SELECT job_id FROM npp_turns WHERE provider_id=?", (provider_id,)).fetchone()
            return row[0] if row else None
    except Exception:  # A failed link must never cost the row itself.
        pass
    return None


@contextlib.contextmanager
def linked(outbox, code):
    """HRM-21 C2: an NPP reply queued inside names its own listing (`<job>`) or card version (`<job>-<n>`)."""
    before = getattr(outbox, 'transcript_link', None)
    outbox.transcript_link = code
    try:
        yield
    finally:
        outbox.transcript_link = before


class Capture:
    """Entered at handle's entry; finally appends even ignored/error paths, before returning.

    Only observes bytes already fetched by the photo path; no extra fetch or retained copy.
    """
    def __init__(self, conv, msg):
        self.conv, self.msg, self.photos = conv, msg, conv.photos
        self.shas, self.result, self.started = [], "error", time.monotonic()

    def __enter__(self):
        self.conv.outbox.transcript_context = self
        if self.photos is not None:
            self.conv.photos = self
        return self

    def __getattr__(self, name):
        return getattr(self.photos, name)

    def fetch(self, *args, **kw):
        data = self.photos.fetch(*args, **kw)
        try:
            self.shas = [hashlib.sha256(b).hexdigest() for b in data if isinstance(b, (bytes, bytearray))]
        except Exception:
            pass  # Observation must not change the photo path.
        return data

    def metadata(self):
        c, m = self.conv, self.msg
        out: dict = dict(latency_ms=round((time.monotonic() - self.started) * 1000))
        if c.db.execute("SELECT 1 FROM sqlite_master WHERE name='interpreter_audit'").fetchone():
            row = c.db.execute("SELECT backend FROM interpreter_audit WHERE provider_id=?", (m.provider_id,)).fetchone()
            if row:
                itp = c.interpreter
                chosen = getattr(itp, 'fallback' if getattr(itp, 'last_fallback', False) else 'primary', itp)
                out.update(backend=row[0], model=getattr(chosen, 'model', None))
        # Only a code explicitly typed in this message is bound here; never guess from another draft.
        from hass.conversation import parse_keyword
        match = parse_keyword(m.text)
        if match and match[1] and match[1] != 'all':  # AV1052-08: `no all` names no draft
            out['draft_code'] = match[1]
        elif (job := npp_job(c.db, m.provider_id)) is not None:  # HRM-21 C1: an accepted NPP turn names its listing
            out['draft_code'] = job
        return out

    def __exit__(self, *_):
        self.conv.photos = self.photos
        self.conv.outbox.transcript_context = None
        try:
            from hass.conversation import sender_key
            kind = 'tapback' if self.msg.kind == 'reaction' else self.msg.kind if self.msg.kind in ('edited', 'tapback', 'voice', 'file', 'photo') else 'photo' if self.msg.attachments else 'text'
            safe(self.conv.sdir, **event(self.msg.chat, sender_key(self.msg.sender), 'in', kind, self.msg.text,
                 self.msg.provider_id, disposition=self.result, attachments=self.shas, **self.metadata()))
        except Exception:
            logging.getLogger(__name__).error("ALERT transcript-write-failed")


def outgoing(outbox, chat, text, attachments, reply_to):
    try:
        ctx = getattr(outbox, 'transcript_context', None)
        state = Path(outbox.db.execute('PRAGMA database_list').fetchone()[2]).parent
        shas = []
        for p in attachments:
            try: shas.append(hashlib.sha256(Path(p).read_bytes()).hexdigest())
            except OSError: pass  # An unavailable picture must not erase the reply text.
        meta = ctx.metadata() if ctx else {}
        link = getattr(outbox, 'transcript_link', None)
        if link is not None:
            # An NPP reply names its own card: an inherited inbound code (e.g. during an early flush) may be another draft's.
            meta['draft_code'] = link
        safe(state, **event(chat, 'hass', 'out', 'photo' if attachments else 'text', text,
             reply_to=reply_to or outbox.msg_id, attachments=shas, **meta))
    except Exception:
        logging.getLogger(__name__).error("ALERT transcript-write-failed")


def read(state):
    # Unlike open_state/private_db, this path must not mkdir, chmod, create a DB or follow a file link.
    root = Path(state).resolve()
    for path, mode in ((root, 0o700), (root / NAME, 0o600)):
        st = path.lstat()
        if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != mode or (not stat.S_ISDIR(st.st_mode) if path == root else not stat.S_ISREG(st.st_mode)):
            raise ValueError('unsafe transcript store')
    return sqlite3.connect(f'{(root / NAME).as_uri()}?mode=ro', uri=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('export', 'stats'))
    p.add_argument('--state', required=True)
    p.add_argument('--since', type=date.fromisoformat)
    p.add_argument('--chat')
    a = p.parse_args(argv)
    if a.command == 'export' and a.since is None:
        p.error('export requires --since YYYY-MM-DD')
    try:
        with contextlib.closing(read(a.state)) as db:
            db.row_factory = sqlite3.Row
            where, params = ' WHERE utc >= ?', [str(a.since or date.min)]
            if a.chat is not None:
                where += ' AND chat = ?'
                params.append(a.chat)
            query = 'SELECT * FROM events' + where + ' ORDER BY id' if a.command == 'export' else 'SELECT substr(utc,1,10) AS day, disposition, count(*) AS count FROM events' + where + ' GROUP BY day, disposition ORDER BY day, disposition'
            for row in db.execute(query, params):
                doc = dict(row)
                if 'attachments' in doc:
                    doc['attachments'] = json.loads(doc['attachments'])
                    if not isinstance(doc['attachments'], list):
                        raise ValueError('attachments must be an array')
                print(json.dumps(doc, ensure_ascii=True))
    except (OSError, TypeError, ValueError, sqlite3.Error):
        print('transcript-unavailable', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
