"""Fixture-tested live release engine. Installing this module does not enable live use.
Attended operations: python3 -m hass.publish_live COMMAND --host host.json.
"""
import argparse
import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in (None, ''): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # `python3 hass/publish_live.py` (runbook form)

from hass import conversation, design_check, editor, live_policy, migration_check, owner_answers, release_journal as journal, sitegen
from hass.content_model import load_and_validate

REMOTE = 'git@github-avocadoman:Grahammmm/theavocadoman-site.git'
URL = 'https://theavocadoman.com'
# HASS-SITE-LOOK-1b: the published paths a design change may touch (design_check.DESIGN's storefront-mockup files and pages)
DESIGN_SITE = frozenset(p.removeprefix(sitegen.SITE_PREFIX) for p in design_check.DESIGN if p.startswith(sitegen.SITE_PREFIX))
PACIFIC = ZoneInfo('America/Los_Angeles')
LOG = logging.getLogger('hass.release')
BOOK_REASON = 'the website record needs G to check it'
UNDO_NOT_LIVE = 'that undo takes back a change that never went on the website from chat'  # HASS-SEC-2 (M1)
# The publish screen's email shape (stricter than live_policy.EMAIL, which checks typed owner text): a local part of 2 or more
# characters that begins and ends with a letter or digit, a domain whose labels begin and end with one, a final label of 2 or
# more letters, and no letter or digit touching either end. Random image bytes such as 'w@J.Wa' and '.@0y.Ty' do not fit.
SCREEN_EMAIL = re.compile(r'(?<![A-Za-z0-9])[A-Za-z0-9][A-Za-z0-9._%+-]*[A-Za-z0-9]'
                          r'@(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}(?![A-Za-z0-9])')
PATTERNS = dict(email=SCREEN_EMAIL, phone=live_policy.PHONE)
PATTERNS.update({name: re.compile(rx) for name, rx in {
    'pem': r'-----BEGIN', 'aws': r'AKIA[0-9A-Z]{16}', 'github': r'gh[pousr]_[A-Za-z0-9]{20,}',
    'key': r'sk-[A-Za-z0-9]{20,}', 'slack': r'xox[abp]-[A-Za-z0-9-]+', 'home': r'/home/[^\s"\x27]+',
    'loopback': r'127\.0\.0\.1', 'database': r'[\w./-]*\.sqlite3', 'chat': r'iMessage;[^\s"\x27]*'}.items()})


def release_config(raw):
    keys = {'siteCheckout', 'siteRemote', 'liveUrl', 'stopFile', 'dailyCap', 'minIntervalSeconds', 'verifyMinutes'}
    if not isinstance(raw, dict) or set(raw) - keys or not keys - {'dailyCap', 'minIntervalSeconds', 'verifyMinutes'} <= raw.keys():
        raise ValueError('release')
    cfg = {'dailyCap': 10, 'minIntervalSeconds': 120, 'verifyMinutes': 15, **raw}
    for key, low, high in [('dailyCap', 1, 50), ('minIntervalSeconds', 60, 3600), ('verifyMinutes', 5, 60)]:
        if type(cfg[key]) is not int or not low <= cfg[key] <= high: raise ValueError(key)
    if cfg['siteRemote'] != REMOTE: raise ValueError('siteRemote')
    if cfg['liveUrl'] != URL: raise ValueError('liveUrl')
    for key in ('siteCheckout', 'stopFile'):
        if not isinstance(cfg[key], str) or not Path(cfg[key]).is_absolute(): raise ValueError(key)
    return cfg


# RFC 2606 / 6761 reserved names: an address here can never reach a person (a form placeholder such as you@example.com).
RESERVED_DOMAINS = ('example.com', 'example.org', 'example.net')
RESERVED_TLDS = ('example', 'test', 'invalid', 'localhost')


def reserved_address(value):
    """True only for an email whose domain is a reserved example domain, or a subdomain of one, in any letter case."""
    domain = value.rpartition('@')[2].lower().rstrip('.')
    return domain in RESERVED_DOMAINS or domain.endswith(tuple('.' + d for d in RESERVED_DOMAINS)) \
        or domain.rpartition('.')[2] in RESERVED_TLDS


# In a binary file (a NUL byte in the first 8 KB, or one of these extensions) an email counts only with a local part of 3 or
# more characters and one of these real top-level domains, so chance byte runs in an image cannot block a release while an
# address written into image metadata or a PDF is still caught.
BINARY_EXTENSIONS = ('jpg', 'jpeg', 'png', 'webp', 'gif', 'ico', 'woff', 'woff2', 'pdf', 'zip')
BINARY_TLDS = ('com', 'org', 'net', 'edu', 'gov', 'mil', 'io', 'us', 'co', 'uk', 'ca', 'info', 'biz', 'me', 'app', 'dev', 'ai')


def is_binary(text, path=''):
    return '\0' in text[:8192] or os.path.splitext(path)[1][1:].lower() in BINARY_EXTENSIONS


def pattern_hits(name, rx, text, path=''):
    if name == 'phone' and is_binary(text, path): rx = live_policy.PHONE_STRICT  # HASS-SEC-2 (M3): image bytes keep the strict shape
    hits = {m.group() for m in rx.finditer(text)}
    if name != 'email': return hits
    binary = is_binary(text, path)
    return {h for h in hits if not reserved_address(h) and (not binary or (
        len(h.partition('@')[0]) >= 3 and h.rpartition('.')[2].lower() in BINARY_TLDS))}


# HASS-SEC-2 (M3): an owner number is found in any format: every run of digits (with spaces, dots, dashes, brackets, slashes or
# a + between them) is read as its digits, and holds the number when it holds its last 10 digits (all of a shorter one).
DIGIT_RUN = re.compile(r'\d(?:[ \t.\-()/+]{0,3}\d)*')


def owner_needles(forbidden):
    """(exact values, owner numbers as digits, owner email addresses casefolded) for the owner addresses and chat ids."""
    exact, digits, emails = [], set(), set()
    for value in forbidden:
        if not value: continue
        exact.append(value)
        key = conversation.sender_key(value.rpartition(';-;')[2])  # a chat id names its address after ;-;
        if key and key.startswith('+'): digits.add(key[1:][-10:])
        elif key: emails.add(key)
    return exact, digits, emails


def owner_found(data, needles):
    exact, digits, emails = needles
    if any(value.encode() in data for value in exact): return True
    if not (digits or emails): return False
    text = data.decode('latin1')
    if emails and any(e in text.casefold() for e in emails): return True
    return bool(digits) and any(d in re.sub(r'\D', '', m.group()) for m in DIGIT_RUN.finditer(text) for d in digits)


def privacy(files, baseline, message, forbidden=()):
    """Compare values per path, never counts. Binary files are scanned too, with the stricter binary email rule above.
    Reserved example addresses are not personal."""
    found = set()
    for path, data in {**{p: b for p, b in files.items() if baseline.get(p) != b}, '<commit>': message.encode()}.items():
        text, old = data.decode('latin1'), baseline.get(path, b'').decode('latin1') if path != '<commit>' else ''
        for name, rx in PATTERNS.items():
            if pattern_hits(name, rx, text, path) - pattern_hits(name, rx, old, path): found.add(name)
    # Owner identity is prohibited even in an unchanged, grandfathered file, in any format (HASS-SEC-2, M3).
    needles = owner_needles(forbidden)
    if any(owner_found(data, needles) for data in [*files.values(), message.encode()]): found.add('owner')
    return sorted(found)


def sha(data): return hashlib.sha256(data).hexdigest()
def utcnow(): return datetime.now(timezone.utc)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): raise ValueError('redirect')


def fetch_live(url, base):
    target, allowed = urllib.parse.urlsplit(url), urllib.parse.urlsplit(base)
    if target.scheme != 'https' or target.netloc != allowed.netloc or target.username or target.fragment:
        raise ValueError('live-url')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(url, timeout=10) as response:
        data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024: raise ValueError('live-size')
        return data


class LiveEditor(conversation.Editor):
    def __init__(self, state, release, host_dir, *, registry=None, clock=utcnow, sleep=time.sleep,
                 git=None, fetch=fetch_live):
        super().__init__(state, registry)
        self.cfg, self.root = release, Path(host_dir)
        self.books = journal.Books(self.root)
        self.wt = editor._load(state)[2]
        self.state_dir = state
        self.site = Path(release['siteCheckout'])
        self.clock, self.sleep, self.git_runner, self.fetch = clock, sleep, git, fetch
        self.conv = None
        self.settings = conversation.load_settings(Path(state))
        self.alerts = set()

    def git(self, *args, cwd=None):
        if self.git_runner: return self.git_runner(Path(cwd or self.site), *args)
        return subprocess.run(['git', '-C', str(cwd or self.site), *args], capture_output=True, timeout=60, check=True).stdout.decode().strip()

    def private_values(self):
        """Every owner address and chat id (Mike's and, with gIsOwner, G's): none may appear in a published file."""
        st = self.settings
        return (*st['ownerSenders'], st['ownerChat'], *st.get('ownerChats', ()), *st.get('gSenders', ()), st.get('gChat'))

    def alert(self, code):
        if code not in self.alerts:
            LOG.error('ALERTS %s', code)
            self.alerts.add(code)

    def load(self):
        try: out = self.books.load()
        except journal.BooksError:
            self.alert('release-books')
            raise
        self.alerts.discard('release-books')
        return out

    def stopped(self):
        try: os.lstat(self.cfg['stopFile']); return True
        except FileNotFoundError: return False

    def refuse(self, reason): return {'result': 'refused', 'reason': reason + '. The website is unchanged.'}

    def day(self): return self.clock().astimezone(PACIFIC).date().isoformat()

    def cap_used(self, books):
        return sum(journal.instant(p['at']).astimezone(PACIFIC).date().isoformat() == self.day() for p in books['pushes'])

    def interval(self, books):
        if books['latest_attempt']:
            wait = self.cfg['minIntervalSeconds'] - (self.clock() - journal.instant(books['latest_attempt'])).total_seconds()
            if wait > 0: self.sleep(wait)

    def site_state(self, head):
        self.git('fetch', 'origin')
        if self.git('remote', 'get-url', 'origin') != self.cfg['siteRemote'] or self.git('status', '--porcelain'):
            raise ValueError('site-state')
        if self.git('rev-parse', 'HEAD') != head or self.git('rev-parse', 'origin/main') != head:
            raise ValueError('site-state')

    def tree(self):
        result = {}
        for rel in self.git('ls-files', '-z').split('\0'):
            if not rel: continue
            path = self.site / rel
            if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file(): raise ValueError('site-state')
            result[rel] = path.read_bytes()
        return result

    def build(self, commit, today, cid, label, checks=False):
        folder = self.root / 'build' / cid / label
        if folder.exists(): shutil.rmtree(folder)
        folder.mkdir(parents=True, mode=0o700)
        raw = subprocess.run(['git', '-C', str(self.wt), 'archive', commit], capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive: archive.extractall(folder, filter='data')
        content = load_and_validate(folder / 'hass/content', folder / 'storefront-mockup')
        if checks:
            if sitegen.stale_paths(content, folder) or migration_check.run_checks(folder)[0]: raise ValueError('build-check')
            subprocess.run([sys.executable, '-B', '-m', 'unittest', 'hass.tests.test_publish', 'hass.tests.test_content',
                            'hass.tests.test_style_no_commerce'], cwd=folder, capture_output=True, timeout=300, check=True)
        return sitegen.publish_files(content, folder, today=date.fromisoformat(today))

    def baseline(self, books, cid):
        if books['last_build_today'] is None: raise ValueError('baseline-date')
        files = self.build(self.git('rev-parse', 'HEAD', cwd=self.wt), books['last_build_today'], cid, 'base')
        if files != self.tree(): raise ValueError('baseline')
        return files

    def _asker(self, j):
        """The owner chat whose yes started this release, as recorded in the release entry when that yes was applied (two owners
        can hold drafts with the same change_id, so the newest draft row is never used). An entry with no recorded chat (written
        before this field, or Graham's one-command revert) goes to ownerChat."""
        return j.get('chat') or self.settings['ownerChat']

    def open_release(self):
        """HASS-OWNERS-2: the owner chat whose release has not settled (any journal entry not closed), or None. An unreadable book\n        says None here: apply() refuses on it anyway, in plain words."""
        try: _books, entries = self.load()
        except (journal.BooksError, OSError, ValueError): return None
        return next((self._asker(j) for j in entries if j['state'] not in journal.CLOSED), None)

    def _has_draft(self, cid):
        db = getattr(self.conv, 'db', None)
        return bool(db and db.execute('SELECT 1 FROM drafts WHERE change_id = ?', (cid,)).fetchone())

    @staticmethod
    def _landed_change(entries, cid):
        return any(j['change_id'] == cid and j['kind'] == 'change' and j['state'] in journal.LANDED for j in entries)

    def went_live(self, change_id):
        """HASS-SEC-2 (M1): True only when the change went on the website through this engine (a change entry that landed).
        A change saved in private mode before live, one whose release failed, and an unreadable book are all False."""
        try: _books, entries = self.load()
        except (journal.BooksError, OSError, ValueError): return False
        return self._landed_change(entries, change_id)

    def _original_owner(self, j):
        """HASS-SEC-2 (L6): for an undo, the owner chat whose change it takes back (as recorded when that change went live), else None."""
        if j['kind'] != 'undo' or not j.get('orig'): return None
        orig = next((e for e in self.books.journals() if e['change_id'] == j['orig'] and e['kind'] == 'change'), None)
        return (self._asker(orig),) if orig else None

    def _summary(self, cid):
        """The chat summary of a change (what the owner was shown), or None."""
        db = getattr(self.conv, 'db', None)
        row = db.execute('SELECT summary FROM drafts WHERE change_id = ? ORDER BY row_id DESC LIMIT 1', (cid,)).fetchone() if db else None
        return row[0] if row else None

    def _code(self, cid):
        if self.conv:
            row = self.conv.db.execute('SELECT code FROM drafts WHERE change_id = ? ORDER BY row_id DESC LIMIT 1', (cid,)).fetchone()
            if row: return row[0]
        return cid[-4:]

    routes_chat = True  # the conversation passes the approving owner's chat, kept in the release entry

    def apply(self, change_id, draft_hash, chat=None):
        guard = getattr(self, 'environment_guard', None)
        if guard and (problem := guard(change_id)): return problem
        if not journal.CID.fullmatch(str(change_id)): return self.refuse('the change could not be read')
        with self.books.lock() as held:
            if not held: return self.refuse('another change is going live')
            if self.stopped(): return self.refuse('live changes are stopped right now')
            try:
                self._reconcile(notify=False)
                books, entries = self.load()
            except journal.BooksError: return self.refuse(BOOK_REASON)
            if any(j['state'] not in journal.CLOSED for j in entries): return self.refuse('the last change is not settled yet; G is checking it')
            if any(j['change_id'] == change_id for j in entries): return self.refuse('this change already has a release record')
            shown = self.show(change_id)
            draft = shown.get('draft')
            if not draft or draft.get('draft_hash') != draft_hash: return self.refuse('the draft no longer matches')
            undo = bool(draft['ops']) and all(c['op'] == 'history.revert' for c in draft['ops'])
            # HASS-SEC-2 (M1): an undo may only take back a change that went live through this engine; a change saved in private
            # mode before live never passed the live gate, and its undo would publish the content it replaced, unchecked.
            if undo and not all(self._landed_change(entries, cid) for cid in live_policy.undone(draft)): return self.refuse(UNDO_NOT_LIVE)
            used = self.cap_used(books)
            if used >= self.cfg['dailyCap'] and not undo: return self.refuse(f"today's limit of {self.cfg['dailyCap']} live changes is reached; send it again tomorrow")
            self.interval(books)
            if self.stopped(): return self.refuse('live changes are stopped right now')
            if guard and (problem := guard(change_id)): return problem
            if reasons := live_policy.check(draft): return self.refuse('; '.join(reasons))
            try: self.site_state(books['last_site_commit'])
            except (ValueError, subprocess.SubprocessError, OSError):
                self.alert('site-state')
                return self.refuse('someone else changed the website repo; G must check')
            try: self.baseline(books, change_id)
            except (ValueError, subprocess.SubprocessError, OSError):
                self.alert('baseline')
                return self.refuse("the website and Hass's copy differ; G must check")
            j = dict(change_id=change_id, code=self._code(change_id), kind='undo' if undo else 'change',
                     orig=draft['ops'][0]['args']['changeId'] if undo else None, draft_hash=draft_hash,
                     writer_before=self.git('rev-parse', 'HEAD', cwd=self.wt), site_before=books['last_site_commit'],
                     today=self.day(), seq=self.books.next_seq(), push_attempts=[],
                     state='intent', notified=[], at=self.clock().isoformat(), **({'chat': chat} if chat else {}))
            self.books.write(j)
            result = super().apply(change_id, draft_hash)
            if result['result'] not in ('applied', 'already-applied'):
                self.books.write(j, 'not-applied')
                return result
            self.books.write(j, 'applied', writer_after=result['commit'])
            self.pipeline(j)
            return result

    def message(self, j):
        suffix = f" undo of {j['orig']}" if j['kind'] == 'undo' else ''
        return f"hass live: {j['change_id']} ({j['code']}){suffix}" if j['kind'] != 'baseline' else f"hass baseline: {j['writer_after']}"

    def pipeline(self, j):
        guard = getattr(self, 'environment_guard', None)
        if guard and j['kind'] != 'baseline' and guard(j['change_id'], recorded=True):
            self.alert('env-gone')
            return
        # A built record is the durable intent for mirroring and committing locally.
        try:
            files = self.build(j['writer_after'], j['today'], j['change_id'], 'new', checks=True)
            old = self.tree()
            before = self.build(j['writer_before'], j['today'], j['change_id'], 'before')
            if j['kind'] != 'baseline':
                record = self.show(j['change_id']).get('change', {})
                design = record.get('kind') == 'design'  # HASS-SITE-LOOK-1b: a look change (or its undo) changes design files only
                collections = set() if design else {r['collection'] for r in record.get('records', [])}
                allowed = set(DESIGN_SITE) if design else {'community.json'}
                if collections & {'products', 'store'}: allowed |= {'index.html', 'catalog-products.js', 'hike/index.html'}
                if 'store' in collections: allowed |= {'about/index.html', 'getting-here/index.html', 'policies/index.html', 'faq/index.html'}
                if 'makers' in collections: allowed |= {'index.html', 'producers.js', 'catalog-products.js'}
                if collections & {'events', 'routeIdeas', 'club'}: allowed |= {'index.html', 'hike/index.html'}
                for touched in record.get('records', []):
                    for value in (touched.get('before'), touched.get('after')):
                        if isinstance(value, dict):
                            image = value.get('image') or (value.get('homeImage') or {}).get('image')
                            if image: allowed.add(image)
                changed = {p for p in before.keys() | files.keys() if before.get(p) != files.get(p)}
                if any(p not in allowed and (design or not (p.startswith('assets/products/photo-') and p not in before)) for p in changed):
                    raise ValueError('unexplained-diff')
            if privacy(files, {} if j['kind'] == 'baseline' else old, self.message(j), self.private_values()): raise ValueError('privacy')
            manifest = {p: sha(b) for p, b in files.items() if old.get(p) != b}
            if not manifest: raise ValueError('empty-build')
            sitegen.write_files(files, self.root / 'build' / j['change_id'] / 'out')
        except (ValueError, OSError, subprocess.SubprocessError):
            self.fail(j, 'checks')
            return
        self.books.write(j, 'built', manifest=manifest)
        try:
            for rel in old.keys() - files.keys(): (self.site / rel).unlink()
            sitegen.write_files(files, self.site)
            self.git('add', '-A')
            self.git('commit', '-s', '-m', self.message(j), '-m', 'Reviewed typed content change')
            commit = self.git('rev-parse', 'HEAD')
        except (ValueError, OSError, subprocess.SubprocessError):
            self.fail(j, 'commit')
            return
        self.books.write(j, 'committed', site_commit=commit)
        self.push(j)

    def fail(self, j, step):
        # Only called before any push or after positive proof of no delivery.
        self.git('reset', '--hard', j['site_before'])
        self.books.write(j, 'not-published', step=step, reason='live changes are stopped right now' if step == 'stopped' else 'the release checks did not finish')
        self.alert('not-published')

    def remote(self): return self.git('ls-remote', 'origin', 'refs/heads/main').split()[0]

    def landed(self, j, remote):
        if remote == j.get('site_commit'): return True
        self.git('fetch', 'origin')
        # Verify an exact subject, never trust a substring grep of an unrelated message.
        subjects = self.git('log', 'origin/main', '--format=%s').splitlines()
        return self.message(j) in subjects

    def push(self, j):
        for delay in (0, 10, 30, 60):
            if delay: self.sleep(delay)
            if self.stopped():
                self.fail(j, 'stopped')
                return
            self.books.write(j, 'pushing', push_attempts=[*j['push_attempts'], self.clock().isoformat()])
            try:
                self.git('push', 'origin', j['site_commit'] + ':refs/heads/main')
            except subprocess.CalledProcessError as exc:
                text = (exc.stderr or b'').decode(errors='replace') if isinstance(exc.stderr, bytes) else exc.stderr or ''
                # Only these connect-stage errors prove no send. A timeout is ambiguous.
                if re.search(r'connect to host [^\n]+: Connection refused|Could not resolve hostname', text):
                    if delay != 60: continue
                    self.fail(j, 'connect')
                    return
                self.books.write(j, 'unknown')
                return
            except (OSError, subprocess.SubprocessError):
                self.books.write(j, 'unknown')
                return
            try: landed = self.remote() == j['site_commit']
            except (OSError, subprocess.SubprocessError, IndexError): landed = False
            self.books.write(j, 'pushed' if landed else 'unknown', pushed_at=self.clock().isoformat())
            return

    @staticmethod
    def served_path(rel):
        # Cloudflare Pages 308-redirects /x/index.html to /x/ and /y.html to /y; request what it serves directly.
        if rel == 'index.html': return ''
        if rel.endswith('/index.html'): return rel[:-len('index.html')]
        if rel.endswith('.html'): return rel[:-len('.html')]
        return rel

    def live_matches(self, j):
        paths = sorted(j['manifest'])
        matched = True
        for rel in paths[:10]:
            try:
                url = self.cfg['liveUrl'] + '/' + urllib.parse.quote(self.served_path(rel), safe='/') + '?hass=' + j['change_id']
                if sha(self.fetch(url, self.cfg['liveUrl'])) != j['manifest'][rel]: matched = False
            except (OSError, ValueError): matched = False
        return matched and len(paths) <= 10

    def _reconcile(self, notify=True):
        _books, entries = self.load()
        for j in entries:
            state, facts, fields = j['state'], {}, {}
            guard = getattr(self, 'environment_guard', None)
            if guard and j['kind'] != 'baseline' and guard(j['change_id'], recorded=True):
                self.alert('env-gone')
                continue
            if state == 'intent':
                recovery = super().recover()
                if recovery.get('result') != 'ok' or any(x['state'] == 'unresolved' for x in recovery.get('recovered', [])):
                    raise journal.BooksError('release-books')
                shown = self.show(j['change_id']).get('change', {})
                facts['applied'] = shown.get('state') == 'applied'
                if facts['applied']: fields['writer_after'] = shown['commit']
            elif state in ('pushing', 'unknown'):
                if j.get('next_check') and self.clock() < journal.instant(j['next_check']):
                    if notify: self.notify(j)
                    continue
                try:
                    remote = self.remote()
                    facts['landed'] = self.landed(j, remote)
                    if not facts['landed'] and remote == j['site_before']:
                        if j.get('observed_before'):
                            facts['before_twice'] = (self.clock() - journal.instant(j['observed_before'])).total_seconds() >= 120
                        else: fields['observed_before'] = self.clock().isoformat()
                    else: fields['observed_before'] = None
                except (OSError, subprocess.SubprocessError, IndexError): fields['observed_before'] = None
                fields['next_check'] = (self.clock() + timedelta(seconds=120 if fields.get('observed_before') else 600)).isoformat()
                if facts.get('landed'): fields['pushed_at'] = self.clock().isoformat()
            elif state in ('pushed', 'unconfirmed'):
                if state == 'unconfirmed' and j.get('checked_at') and (self.clock() - journal.instant(j['checked_at'])).total_seconds() < 600:
                    if notify: self.notify(j)
                    continue
                age = (self.clock() - journal.instant(j.get('pushed_at', j['at']))).total_seconds()
                facts['matches'] = self.live_matches(j) if age <= 72 * 3600 else False
                facts['expired'] = age >= self.cfg['verifyMinutes'] * 60
                fields['checked_at'] = self.clock().isoformat()
                fields['unchecked'] = sorted(j['manifest'])[10:]
            new, action = journal.decide(state, facts)
            if action == 'reset': self.git('reset', '--hard', j['site_before'])
            if new == 'not-published' and state != new: fields.update(step=action or 'interrupted', reason='the release was interrupted')
            if new != state or fields: self.books.write(j, new, **fields)
            if new in ('unknown', 'unconfirmed', 'not-published'): self.alert(new)
            if notify: self.notify(j)
        self._close_undone_chat_drafts()

    def notify(self, j):
        state = j['state']
        if not self.conv or state in j['notified']: return
        attachments, extra = [], None
        chat = self._asker(j)
        original = self._original_owner(j) if state == 'live' else None  # HASS-SEC-2 (L6): (owner chat, code) of the change undone
        if state == 'live' and j['kind'] == 'undo' and not self._has_draft(j['change_id']):
            text = owner_answers.LIVE_TAKEN_BACK  # Graham's one-command revert: there is no chat draft to point at
            if original: chat = original[0]  # ... told to the owner whose change it took back
        elif state == 'live':
            shot = self.conv.screenshot(j['change_id'])
            attachments = [shot] if shot else []
            posted = getattr(self.conv, 'npp_posted', lambda cid: None)(j['change_id'])  # NPP-G S13: a listing's own live confirmation
            if posted: text, attachments = posted, []
            else:
                text = owner_answers.LIVE_SHOWN.format()
                text += ' ' + (owner_answers.LIVE_PICTURE if shot else owner_answers.LIVE_NO_PICTURE)
            if original and original[0] != chat:  # another owner's undo went live: the owner whose change it was is told too
                who = getattr(self.conv, '_who', lambda _chat: 'the owner')(chat)
                extra = (original[0], owner_answers.undone_by_other(who, self._summary(j['orig'])))
        elif state == 'not-published': text = owner_answers.LIVE_NOT_PUBLISHED.format(code=j['code'], reason=owner_answers.live_reason(j.get('reason')))
        elif state == 'unknown': text = owner_answers.LIVE_UNKNOWN.format(code=j['code'])
        elif state == 'unconfirmed': text = owner_answers.LIVE_UNCONFIRMED.format(code=j['code'])
        else: return
        if chat not in self.settings.get('ownerChats', (self.settings['ownerChat'],)): attachments = []  # G's chat is text only; every owner chat gets the picture
        self.conv.outbox.add(chat, text, attachments)
        if extra: self.conv.outbox.add(*extra, [])
        self.books.write(j, notified=[*j['notified'], state])

    def reconcile(self):
        with self.books.lock() as held:
            if not held: return
            try: self._reconcile()
            except journal.BooksError: return

    def revert_last(self):
        """Graham's one-command revert: the newest change that reached the website and has not been undone is put back by the
        same release path as an owner's undo (writer commit, build, checks, one push, live check). Not a rollback of the site
        repo: a new commit. Refuses while any release is open, while STOP is present and when the books are unreadable."""
        try: _books, entries = self.load()
        except journal.BooksError: return {'result': 'refused'}
        undone = {j['orig'] for j in entries if j['kind'] == 'undo' and j['state'] in journal.LANDED}
        target = next((j for j in reversed(entries) if j['kind'] == 'change' and j['state'] in journal.LANDED
                       and j['change_id'] not in undone), None)
        if target is None: return {'result': 'nothing-to-revert'}
        prepare = getattr(self, 'undo_preparer', None) or self.prepare
        made = prepare([{'op': 'history.revert', 'args': {'changeId': target['change_id']}}])
        if made.get('result') != 'ok': return {'result': 'refused'}
        draft = made['draft']
        out = self.apply(draft['change_id'], draft['draft_hash'])
        if out['result'] not in ('applied', 'already-applied'): return {'result': out['result'], 'reason': out.get('reason')}
        # The chat draft stays as it was until the undo is proved live (see _close_undone_chat_drafts, run by every reconcile).
        state = self.entry_state(draft['change_id'])
        fact = {'change_id': draft['change_id'], 'undid': target['change_id'], 'state': state}
        if state not in journal.LANDED: return {'result': state or 'unknown', 'reason': 'the change is still on the website', **fact}
        return {'result': 'ok', **fact}

    def entry_state(self, cid):
        return next((j['state'] for j in self.books.journals() if j['change_id'] == cid), None)

    def _close_undone_chat_drafts(self):
        """Graham's one-command revert has no chat draft of its own. Only when that undo is proved live is the chat draft it took
        back marked undone; a failed, unknown or unconfirmed undo leaves it as it was, and a restart picks it up here again."""
        try: _books, entries = self.load()
        except journal.BooksError: return
        for j in entries:
            if j['kind'] == 'undo' and j['state'] == 'live' and j.get('orig') and not self._has_draft(j['change_id']):
                self._close_chat_draft(j['orig'])

    def _close_chat_draft(self, cid):
        """Keep Mike's `history`/`status` honest: the chat draft that was undone by the operator is marked undone."""
        path = Path(editor.open_state(self.state_dir)) / 'conversation.sqlite3'
        if not path.is_file(): return
        import sqlite3
        db = sqlite3.connect(path, timeout=10)
        try:
            db.execute("UPDATE drafts SET state = 'reverted', reason = 'undone by Graham' WHERE change_id = ? AND state IN ('applied', 'verified')", (cid,))
            db.commit()
        finally: db.close()

    def operate(self, command, cid=None, confirm=None, resolution=None, from_remote=False):
        if command == 'revert-last': return self.revert_last()
        with self.books.lock() as held:
            if not held: return {'result': 'busy'}
            entries = self.books.journals()
            if command == 'adopt':
                if any(j['state'] not in journal.CLOSED for j in entries): return {'result': 'open-release'}
                head = self.remote()
                self.site_state(head)
                if from_remote: found = None
                else:
                    timestamp = self.git('show', '-s', '--format=%cI', 'HEAD')
                    first = journal.instant(timestamp).astimezone(PACIFIC).date() - timedelta(days=1)
                    today = date.fromisoformat(self.day())
                    found, files = False, {}
                    for i in range(min(14, (today - first).days + 1)):
                        d = (first + timedelta(days=i)).isoformat()
                        files = self.build(self.git('rev-parse', 'HEAD', cwd=self.wt), d, 'adopt', 'base')
                        if files == self.tree(): found = d; break
                    if found is False: return {'result': 'differs', 'paths': len(files.keys() | self.tree().keys())}
                journal.atomic(self.root / 'publish.json', dict(anchor_site_commit=head, anchor_build_today=found,
                    anchor_seq=max([j['seq'] for j in entries] + [0]), anchor_at=self.clock().isoformat()))
                return {'result': 'adopted'}
            self._reconcile()
            books, entries = self.load()
            if command == 'status': return {'result': 'ok', **books, 'caps_used': self.cap_used(books), 'open': [{'change_id': j['change_id'], 'state': j['state']} for j in entries if j['state'] not in journal.CLOSED]}
            if command == 'baseline':
                if self.stopped() or any(j['state'] not in journal.CLOSED for j in entries): return {'result': 'held'}
                if self.cap_used(books) >= self.cfg['dailyCap']: return {'result': 'cap'}
                if confirm:
                    self.interval(books)
                    if self.stopped(): return {'result': 'held'}
                self.site_state(books['last_site_commit'])
                head = self.git('rev-parse', 'HEAD', cwd=self.wt)
                files = self.build(head, self.day(), 'baseline', 'new', checks=True)
                manifest = sha(json.dumps({p: sha(b) for p, b in files.items()}, sort_keys=True).encode())[:12]
                risks = privacy(files, {}, 'hass baseline: ' + head, self.private_values())
                if confirm != manifest or risks:
                    # The exact pages this baseline would publish (writer HEAD, today's date), for G to open and look at.
                    shown = self.root / 'build' / 'baseline-preview'
                    if shown.exists(): shutil.rmtree(shown)
                    shown.mkdir(parents=True, mode=0o700)
                    sitegen.write_files(files, shown)
                    return {'result': 'preview', 'paths': len(files), 'privacy': risks, 'manifest': manifest, 'preview_dir': str(shown), 'writer_head': head}
                cid = 'chg-' + sha((head + manifest + self.clock().isoformat()).encode())[:12]
                j = dict(change_id=cid, code=manifest, kind='baseline', orig=None, draft_hash=manifest, writer_before=head,
                    writer_after=head, site_before=books['last_site_commit'], today=self.day(), seq=self.books.next_seq(),
                    push_attempts=[], state='applied', notified=[], at=self.clock().isoformat())
                self.books.write(j)
                self.pipeline(j)
                return {'result': 'ok', 'change_id': cid, 'state': j['state']}
            if command == 'unblock' and cid is None:
                pending = [e for e in entries if e['state'] == 'not-published']
                if len(pending) == 1: cid = pending[0]['change_id']
            j = next((e for e in entries if e['change_id'] == cid), None)
            if not j: return {'result': 'not-found'}
            guard = getattr(self, 'environment_guard', None)
            if guard and j['kind'] != 'baseline' and guard(j['change_id'], recorded=True):
                self.alert('env-gone')
                return {'result': 'env-gone'}
            if command == 'retry':
                if j['state'] != 'not-published' or self.stopped(): return {'result': 'held'}
                if self.landed(j, self.remote()): return {'result': 'already-landed'}
                self.interval(books)
                if self.stopped(): return {'result': 'held'}
                self.site_state(j['site_before'])
                self.books.write(j, 'applied', today=self.day())
                self.pipeline(j)
            elif command == 'resolve':
                if j['state'] not in ('unknown', 'unconfirmed') or resolution not in ('live', 'reverted'): return {'result': 'wrong-state'}
                if resolution == 'reverted': self.site_state(j['site_before'])
                self.books.write(j, 'live' if resolution == 'live' else 'reverted')
            elif command == 'unblock':
                if j['state'] != 'not-published': return {'result': 'wrong-state'}
                self.site_state(books['last_site_commit'])
                self.baseline(books, cid)
                self.books.write(j, 'closed')
            return {'result': 'ok', 'change_id': cid, 'state': j['state']}


def main(argv=None):
    from hass import host
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['status', 'adopt', 'baseline', 'retry', 'resolve', 'unblock', 'revert-last'])
    ap.add_argument('change_id', nargs='?')
    ap.add_argument('--host', required=True)
    ap.add_argument('--confirm')
    ap.add_argument('--as', dest='resolution', choices=['live', 'reverted'])
    ap.add_argument('--from-remote', action='store_true')
    args = ap.parse_args(argv)
    try:
        cfg = host.load_host(args.host)
        from hass.sandbox import policy
        mode = policy(cfg)
        if mode['hold'] or 'site' not in mode['live']:
            raise ValueError('sandbox')
        live = LiveEditor(cfg['state'], cfg['release'], Path(args.host).resolve().parent)
        # Recovery and retry validate each journal's recorded target before any target I/O.
        from hass.sandbox_editor import SiteEditor
        site = SiteEditor(cfg['state'], host.site_gate(cfg), lambda: live)
        live.environment_guard = site.check_environment
        live.undo_preparer = site.prepare  # the operator's undo carries the recorded target binding
        out = live.operate(args.command, args.change_id, args.confirm, args.resolution, args.from_remote)
        # CLI never emits paths, sender, owner text or push history.
        out = {k: v for k, v in out.items() if k not in ('pushes', 'latest_attempt')}
        code = 0 if out['result'] in ('ok', 'adopted', 'preview') else 1
    except (ValueError, OSError, subprocess.SubprocessError, host.HostConfigError): out, code = {'result': 'refused'}, 1
    print(json.dumps(out, sort_keys=True))
    return code


if __name__ == '__main__': sys.exit(main())
