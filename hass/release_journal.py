"""Durable release books and restart decisions. No network or automatic replay."""
import contextlib
import fcntl
import json
import os
import re
import stat
import tempfile
from datetime import date, datetime
from pathlib import Path

CLOSED = frozenset({'live', 'not-applied', 'reverted', 'closed'})
LANDED = frozenset({'pushed', 'live', 'unconfirmed'})
STATES = CLOSED | LANDED | {'intent', 'applied', 'built', 'committed', 'pushing', 'not-published', 'unknown'}
ANCHOR = {'anchor_site_commit', 'anchor_build_today', 'anchor_seq', 'anchor_at'}
REQUIRED = {'change_id', 'code', 'kind', 'orig', 'draft_hash', 'writer_before', 'site_before', 'today',
            'seq', 'push_attempts', 'state', 'notified', 'at'}
OPTIONAL = {'writer_after', 'manifest', 'site_commit', 'step', 'reason', 'observed_before', 'checked_at',
            'pushed_at', 'next_check', 'unchecked', 'alerted', 'summary', 'chat'}
SHA = re.compile(r'[0-9a-f]{40}')
CID = re.compile(r'chg-[0-9a-f]{12}')
MAX_BYTES = 1048576  # one ceiling: the reader refuses more, so the writer must never install more


class BooksError(ValueError):
    """Never include source bytes or paths in this error."""


def instant(value):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None: raise BooksError('release-books')
    return dt


def private_dir(path):
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    st = path.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
        raise BooksError('release-books')
    return path


def atomic(path, data):
    """Durable before returning; a failed write must prevent the next side effect.

    Serialized bytes (escaping and LF included) above MAX_BYTES are refused before any filesystem effect."""
    path = Path(path)
    raw = (json.dumps(data, sort_keys=True, allow_nan=False) + '\n').encode()
    if len(raw) > MAX_BYTES: raise BooksError('release-books') from None
    private_dir(path.parent)
    fd, name = tempfile.mkstemp(prefix='.release-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_DIRECTORY | os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(name): os.unlink(name)


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out: raise BooksError('release-books')
        out[key] = value
    return out


def _reject_constant(_token):
    raise BooksError('release-books')


def _admitted(st):
    return stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and stat.S_IMODE(st.st_mode) == 0o600 and st.st_size <= MAX_BYTES


def read(path):
    try:
        pre = path.lstat()
        if not _admitted(pre): raise BooksError('release-books')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            st = os.fstat(fd)
            if not _admitted(st) or (st.st_dev, st.st_ino) != (pre.st_dev, pre.st_ino): raise BooksError('release-books')
            stream = os.fdopen(fd, 'rb')
        except BaseException:
            os.close(fd)
            raise
        with stream: raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES: raise BooksError('release-books')
        data = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_reject_constant)
        if not isinstance(data, dict): raise BooksError('release-books')
        return data
    except (OSError, ValueError, RecursionError): raise BooksError('release-books; run adopt if missing') from None


def validate(j):
    try:
        if not REQUIRED <= j.keys() or j.keys() - REQUIRED - OPTIONAL: raise ValueError
        if not CID.fullmatch(j['change_id']) or j['state'] not in STATES: raise ValueError
        if not re.fullmatch(r'[a-z0-9]{4,12}', j['code']): raise ValueError
        if j['kind'] not in {'change', 'undo', 'baseline'}: raise ValueError
        if j['orig'] is not None and not CID.fullmatch(j['orig']): raise ValueError
        if not isinstance(j['draft_hash'], str): raise ValueError
        if 'chat' in j and (not isinstance(j['chat'], str) or not j['chat']): raise ValueError
        for key in ('writer_before', 'site_before'):
            if not SHA.fullmatch(j[key]): raise ValueError
        for key in ('writer_after', 'site_commit'):
            if key in j and not SHA.fullmatch(j[key]): raise ValueError
        if type(j['seq']) is not int or j['seq'] < 1: raise ValueError
        date.fromisoformat(j['today'])
        instant(j['at'])
        if not isinstance(j['push_attempts'], list): raise ValueError
        for value in j['push_attempts']: instant(value)
        if not isinstance(j['notified'], list) or any(s not in STATES for s in j['notified']): raise ValueError
        if j['state'] in LANDED | {'pushing', 'unknown'} and ('site_commit' not in j or not j['push_attempts']): raise ValueError
        if j['state'] in {'built', 'committed'} | LANDED | {'pushing', 'unknown'} and 'manifest' not in j: raise ValueError
        for key in ('pushed_at', 'checked_at', 'next_check', 'observed_before'):
            if j.get(key) is not None: instant(j[key])
        if j['state'] in {'applied', 'built', 'committed'} | LANDED | {'pushing', 'unknown'} and 'writer_after' not in j: raise ValueError
        if 'manifest' in j:
            if not isinstance(j['manifest'], dict): raise ValueError
            for path, digest in j['manifest'].items():
                if not path or path.startswith('/') or any(p in ('..', '.', '.git') for p in path.split('/')): raise ValueError
                if not re.fullmatch(r'[0-9a-f]{64}', digest): raise ValueError
        return j
    except (ValueError, TypeError, KeyError, AttributeError): raise BooksError('release-books') from None


def derive(anchor, journals):
    """Single source of publication head/date and conservative cap accounting."""
    try:
        if set(anchor) != ANCHOR or not SHA.fullmatch(anchor['anchor_site_commit']): raise ValueError
        if type(anchor['anchor_seq']) is not int or anchor['anchor_seq'] < 0: raise ValueError
        instant(anchor['anchor_at'])
        if anchor['anchor_build_today'] is not None: date.fromisoformat(anchor['anchor_build_today'])
        for j in journals: validate(j)
        seqs = sorted(j['seq'] for j in journals if j['seq'] > anchor['anchor_seq'])
        # O(journal count): never materialise the numeric span of a sparse sequence
        if any(s != anchor['anchor_seq'] + i for i, s in enumerate(seqs, 1)): raise ValueError
        if len({j['seq'] for j in journals}) != len(journals): raise ValueError
        head, today = anchor['anchor_site_commit'], anchor['anchor_build_today']
        pending = [j for j in journals if j['seq'] > anchor['anchor_seq'] and j['state'] in LANDED]
        while pending:
            matches = [j for j in pending if j['site_before'] == head]
            if len(matches) != 1: raise ValueError
            j = matches[0]
            if j['site_commit'] == head: raise ValueError
            head, today = j['site_commit'], j['today']
            pending.remove(j)
        pushes = [{'change_id': j['change_id'], 'at': j['push_attempts'][0]} for j in journals
                  if j['seq'] > anchor['anchor_seq'] and j['push_attempts']]
        latest = max((t for j in journals if j['seq'] > anchor['anchor_seq'] for t in j['push_attempts']),
                     key=instant, default=None)
        return {'last_site_commit': head, 'last_build_today': today, 'pushes': pushes, 'latest_attempt': latest}
    except (ValueError, TypeError, KeyError, AttributeError): raise BooksError('release-books') from None


def decide(state, facts):
    """Pure restart table. Observation persistence and effects belong to the caller."""
    if state == 'intent':
        return ('not-published', 'interrupted') if facts.get('applied') else ('not-applied', None)
    if state in {'applied', 'built', 'committed'}: return 'not-published', 'reset'
    if state in {'pushing', 'unknown'}:
        if facts.get('landed'): return 'pushed', None
        if facts.get('before_twice'): return 'not-published', 'reset'
        return 'unknown', None
    if state in {'pushed', 'unconfirmed'}:
        if facts.get('matches'): return 'live', None
        if state == 'pushed' and facts.get('expired'): return 'unconfirmed', None
    return state, None


DEMO_MARKER = 'demo-lock'  # DEMO-LOCK-1: written and removed only by `host.py demo-lock`, under publish_lock


@contextlib.contextmanager
def publish_lock(root):
    """The bare release interlock (non-blocking). Books.lock adds the demo marker check; host.py demo-lock uses this one."""
    fd = os.open(Path(root) / 'publish.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode): raise BooksError('release-books')
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally: os.close(fd)


def demo_marked(root):
    """True unless the demo marker is confirmed absent: any lookup error counts as present."""
    try: os.lstat(Path(root) / DEMO_MARKER)
    except FileNotFoundError: return False
    except OSError: return True
    return True


class Books:
    def __init__(self, root):
        self.root = Path(root)
        self.directory = private_dir(self.root / 'releases')

    @contextlib.contextmanager
    def lock(self):
        """Every release step (apply, reconcile, operator commands) runs under this lock. While the demo lock marker is
        present (or its absence cannot be confirmed) the lock is never granted, so no release work touches the site checkout."""
        with publish_lock(self.root) as held:
            yield held and not demo_marked(self.root)

    def journals(self):
        result = []
        try: paths = sorted(self.directory.iterdir())
        except OSError: raise BooksError('release-books') from None
        for path in paths:
            if path.name.startswith('.release-'): continue  # never-installed atomic temp
            j = validate(read(path))
            if path.name != j['change_id'] + '.json': raise BooksError('release-books')
            result.append(j)
        return sorted(result, key=lambda j: j['seq'])

    def next_seq(self):
        return max([read(self.root / 'publish.json')['anchor_seq']] + [j['seq'] for j in self.journals()]) + 1

    def load(self):
        journals = self.journals()
        return derive(read(self.root / 'publish.json'), journals), journals

    def write(self, journal, state=None, **fields):
        j = {**journal, **fields, **({'state': state} if state else {})}
        validate(j)
        atomic(self.directory / (j['change_id'] + '.json'), j)
        journal.clear()
        journal.update(j)
        return j
