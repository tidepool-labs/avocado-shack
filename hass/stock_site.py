"""Private stock queue; off by default. LINK authenticates approvals; live wrapper alone applies."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import math
import os
import sqlite3
import stat
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

if __package__ in (None, ''): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hass import audit, auto_policy, corrlog, editor, live_policy
from hass.clover import cache, reports

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

def finite(text):
    try: return isinstance(text, str) and Decimal(text).is_finite()
    except ArithmeticError: return False

def private(path):
    for parent in (path.parent, *path.parent.parents):
        if parent.is_symlink(): raise ValueError('unsafe stock path')
    if path.exists() or path.is_symlink():
        st = path.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077 or st.st_nlink != 1:
            raise ValueError('unsafe stock file')

def atomic(path, value):
    private(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.stock-')
    try:
        with os.fdopen(fd, 'w') as out:
            out.write(value if isinstance(value, str) else json.dumps(value, sort_keys=True))
            out.flush(); os.fsync(out.fileno())
        os.replace(tmp, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

class StockSite:
    def __init__(self, state, config, live, *, preparer=None, clock=lambda: datetime.now(timezone.utc)):
        self.state, self.cfg, self.live, self.clock = Path(state), config, live, clock
        self.prepare = preparer or (live.prepare if live else None)
        self.root = self.state / 'clover'
        self.path = self.root / 'site-stock.json'

    @contextlib.contextmanager
    def locked(self):
        cache._private_dir(self.root, True)
        path = self.root / 'site-stock.lock'
        private(path)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False; return
            yield True
        finally: os.close(fd)

    def load(self) -> dict:
        private(self.path)
        if not self.path.exists(): return dict(counts={}, pending={}, sets={}, inflight=None, asOf='', itemCount=0)
        data = json.loads(self.path.read_text())
        if not isinstance(data, dict) or not all(isinstance(data.get(k), dict) for k in ('counts', 'pending', 'sets')):
            raise ValueError('stock state')
        for p in data['pending'].values():
            if not isinstance(p, dict) or not {'target', 'base', 'till', 'crossing', 'first', 'attempts', 'reason', 'held', 'parked', 'new'} <= p.keys() or p['target'] not in ('yes', 'no', 'limited') or p['base'] not in (None, 'yes', 'no', 'limited') or type(p['attempts']) is not int or not isinstance(p['first'], (int, float)) or isinstance(p['first'], bool):
                raise ValueError('stock pending')
        if not {'inflight', 'asOf', 'itemCount'} <= data.keys(): raise ValueError('stock state')
        if not isinstance(data['asOf'], str) or type(data['itemCount']) is not int or data['itemCount'] < 0: raise ValueError('stock state')
        for c in data['counts'].values():
            if not isinstance(c, dict) or not isinstance(c.get('till'), str) or not finite(c.get('count')): raise ValueError('stock count')
        for code, st in data['sets'].items():
            if not isinstance(st, dict) or not {'state', 'words', 'approved_by', 'approved_at'} <= st.keys() or not isinstance(st.get('hash'), str) or st['hash'] != digest(st['words']): raise ValueError('stock set')
        if data['inflight'] is not None and (not isinstance(data['inflight'], dict) or not {'change_id', 'products'} <= data['inflight'].keys()): raise ValueError('stock inflight')
        if any(p['held'] and (p['held'] not in data['sets'] or pid not in data['sets'][p['held']]['words']) for pid, p in data['pending'].items()): raise ValueError('stock binding')
        return data

    def save(self): atomic(self.path, self.data)

    def event(self, key, reason, cid=None):
        log = audit.AuditLog(self.state, self.clock)
        action = audit.new_action('stock-sync', key, reason)
        if not any(r['action'] == action for r in log.rows()):
            log.record('published' if cid else 'refused', action=action, who='timer', pack='site', target='site', env='live',
                       result='ok' if cid else 'replaced', skill='stock.sync', refs={'change': cid} if cid else None, strict=True)
            corrlog.CorrLog(self.state, self.clock).record('corrected', 'stock-sync-' + reason, msg=key)

    def word(self, count):
        return 'no' if count <= 0 else 'limited' if self.cfg.site_stock_words == 'limited' and count <= self.cfg.low_stock_threshold else 'yes'

    def drop(self, pid, reason):
        p = self.data['pending'].pop(pid)
        self.event(p['crossing'], reason)

    def totals(self, reason=''):
        pending = self.data['pending']
        folder = self.root / 'reports'
        cache._private_dir(folder, True)
        atomic(folder / 'site-stock-totals.json', dict(pending=len(pending), parked=sum(bool(p['parked']) for p in pending.values()),
               oldestPendingAge=max([self.clock().timestamp() - p['first'] for p in pending.values()] or [0]), lastReason=reason,
               batchesLeft=sum(math.ceil(sum(p['held'] == c for p in pending.values()) / self.limit) for c in self.data['sets'])))

    @property
    def limit(self): return min(editor.MAX_OPS, live_policy.MAX_RECORDS)

    def proposal(self, ids, asof, products, items):
        rows = {pid: {k: self.data['pending'][pid][k] for k in ('till', 'base', 'target')} for pid in sorted(ids)}
        code = 'stk-' + digest([rows, asof])[:12]
        sold = sum(r['target'] == 'no' for r in rows.values())
        warning = f'{sold} of these would go to Sold out. That is unusual; check the till first.\n' if sold > max(5, len(self.links) * .1) else ''
        totals = ', '.join(f'{sum(r["target"] == w for r in rows.values())} {label}' for w, label in [('no', 'Sold out'), ('limited', 'Limited'), ('yes', 'Available today')])
        text = warning + f'First stock sync / stock set: {len(rows)} words ({totals}); {math.ceil(len(rows) / self.limit)} batches. Apply? stock yes {code}\n'
        for pid, row in rows.items():
            text += reports._safe(f"{products[pid]['name']} ({pid}): {row['base']} -> {row['target']}; till {items[row['till']].stock}") + '\n'
            self.data['pending'][pid]['held'] = code
        folder = self.root / 'reports'
        cache._private_dir(folder, True)
        atomic(folder / f'stock-reconcile-{asof[:10]}-{code}.md', text)
        self.data['sets'][code] = dict(hash=digest(rows), words=rows, approved_by=None, approved_at=None, state='open', at=asof, summary=text.splitlines()[0])
        for path in folder.glob('stock-reconcile-*.md'):
            if path.name[16:26] < (self.clock() - timedelta(days=90)).date().isoformat():
                private(path); path.unlink()

    def run(self):
        if self.cfg.site_stock == 'off': return 'off'
        with self.locked() as held:
            if not held: return 'busy'
            self.data = self.load()
            conn = cache._open_read(self.state)
            if conn is None: return 'no-read'
            with contextlib.closing(conn) as db:
                db.execute('BEGIN')
                meta = cache._meta(db)
                asof = cache._parse_iso(meta.get('asOf'))
                if (cache._refusal(meta, cache.identity_of(self.cfg)) or meta.get('lastResult') != 'ok' or not asof
                    or meta.get('asOf') != meta.get('lastAttempt') or meta['asOf'] <= self.data['asOf']
                    or not 0 <= (self.clock() - asof).total_seconds() <= 1200): return 'no-read'
                items = {i.id: i for i in (cache._item(r) for r in db.execute(f"SELECT {', '.join(cache.COLUMNS)} FROM items"))}
            if len(items) != int(meta['itemCount']) or len(items) < self.data['itemCount'] * .9:
                self.totals('short-read'); return 'short-read'
            content, self.links = reports.read_inputs(self.state, self.live.wt)
            products = {p['id']: p for p in content['products']}
            pending, counts = self.data['pending'], self.data['counts']
            for pid in list(counts):
                if pid not in self.links: counts.pop(pid)
            for pid in list(pending):
                p = pending[pid]
                reason = 'unlinked' if pid not in self.links else 'relinked' if self.links[pid]['cloverId'] != p['till'] else 'gone' if pid not in products else ''
                if reason: self.drop(pid, reason)
            for pid, link in self.links.items():
                tid, old = link['cloverId'], counts.get(pid)
                item = items.get(tid)
                if pid not in products or item is None or item.stock is None: continue
                new = old is None or old['till'] != tid
                target = self.word(item.stock)
                if new or self.word(Decimal(old['count'])) != target:
                    prior = pending.get(pid)
                    if not new or products[pid].get('available') != target:
                        pending[pid] = dict(target=target, base=prior['base'] if prior else products[pid].get('available'), till=tid,
                            crossing=digest([pid, tid, meta['asOf']])[:12], first=prior['first'] if prior else self.clock().timestamp(),
                            attempts=0, reason='', held=prior['held'] if prior else None, parked=None, new=new or bool(prior and prior['new']))
                counts[pid] = dict(till=tid, count=str(item.stock))
            self.data.update(asOf=meta['asOf'], itemCount=len(items)); self.save()
            self.live.reconcile()
            books, _ = self.live.load()
            try: self.live.baseline(books, 'stock-check')
            except (ValueError, OSError): return self.wait('publish-refused', list(pending))
            inflight = self.data['inflight']
            if inflight:
                state = self.live.entry_state(inflight['change_id'])
                if state not in (None, 'not-applied', 'live'): return self.wait('publish-refused' if state == 'not-published' else 'release-unsettled', list(pending))
                if state == 'live' and not self.finish(inflight, products): return self.wait('publish-refused', list(pending))
                self.data['inflight'] = None
            for pid, p in list(pending.items()):
                item = items.get(p['till'])
                p['parked'] = ('not-in-read' if item is None else 'no-count' if item.stock is None else 'hidden' if item.hidden else 'not-active' if products[pid]['status'] != 'active' else None)
                if p['parked']: continue
                p['target'] = self.word(item.stock)
                code = p['held']
                if code and self.data['sets'][code]['words'][pid]['target'] != p['target']:
                    if not self.data['sets'][code]['approved_by']:
                        self.data['sets'][code]['state'] = 'stale'
                        for entry in pending.values():
                            if entry['held'] == code: entry['held'] = None
                    p['held'] = None
                word = products[pid].get('available')
                if word == p['target']: pending.pop(pid); continue
                if word != p['base']: self.drop(pid, 'owner-wins'); continue

            proposals = [pid for pid, p in pending.items() if not p['held'] and not p['parked'] and (p['new'] or self.cfg.site_stock == 'draft')]
            auto = [pid for pid, p in pending.items() if not p['held'] and pid not in proposals and not p['parked']]
            if sum(pending[pid]['target'] == 'no' for pid in auto) > max(5, len(self.links) * .1): proposals += auto; auto = []
            if proposals: self.proposal(proposals, meta['asOf'], products, items)
            folder = self.root / 'reports'; cache._private_dir(folder, True)
            atomic(folder / f'stock-reconcile-{meta["asOf"][:10]}-gaps.md', '\n'.join(reports._safe(f'{pid}: ' + ('not found in the till read' if link['cloverId'] not in items else pending.get(pid, {}).get('parked') or 'counted')) for pid, link in self.links.items()))
            for code, s in self.data['sets'].items():
                if not any(p['held'] == code for p in pending.values()) and s['state'] == 'open': s['state'] = 'done'
            groups = [auto] + [[pid for pid, p in pending.items() if p['held'] == c and not p['parked']] for c, s in sorted(self.data['sets'].items(), key=lambda pair: pair[1]['at']) if s['state'] == 'open' and s['approved_by']]
            batch = next((g for g in groups if g), [])
            batch = sorted(batch, key=lambda pid: (('no', 'limited', 'yes').index(pending[pid]['target']), pending[pid]['first'], pid))[:self.limit]
            self.save()
            if not batch: self.totals('held' if pending else ''); return 'held' if pending else 'ok'
            if self.paused(): return self.wait('paused', batch)
            if self.live.cap_used(books) >= self.live.cfg['dailyCap'] - 3: return self.wait('cap-reserve', batch)
            with editor._writer_lock(self.state) as available:
                if not available: return self.wait('writer-busy', batch)
            ops = [{'op': 'product.set_availability', 'args': {'id': pid, 'available': pending[pid]['target']}} for pid in batch]
            if not pending[batch[0]]['held'] and not auto_policy.qualifies(ops, ['product.set_availability'], False)[0]: return self.wait('policy', batch)
            made = self.prepare(ops)
            if made.get('result') != 'ok':
                reason = made.get('reason', '')
                bad = next((pid for pid in batch if reason.startswith(pid + ' is ') and 'restore it' in reason), None)
                if bad:
                    pending[bad]['parked'] = 'editor-refused'; batch.remove(bad)
                    if not batch: self.save(); self.totals(); return 'editor-refused'
                    made = self.prepare([op for op in ops if op['args']['id'] != bad])
                if made.get('result') != 'ok': return self.wait('not-checked-today' if 'not checked today' in reason else 'editor-error', batch)
            d = made['draft']
            self.data['inflight'] = dict(change_id=d['change_id'], products={pid: dict(pending[pid]) for pid in batch})
            self.save()
            if self.paused(): return self.wait('paused', batch)
            out = self.live.apply(d['change_id'], d['draft_hash'])
            self.live.reconcile()
            content, _ = reports.read_inputs(self.state, self.live.wt)
            if self.live.entry_state(d['change_id']) == 'live':
                self.live.baseline(self.live.load()[0], 'stock-readback')
                if not self.finish(self.data['inflight'], {p['id']: p for p in content['products']}): return self.wait('publish-refused', batch)
                self.data['inflight'] = None
                self.save(); self.totals(); return 'live'
            return self.wait('writer-busy' if out.get('result') == 'busy' else 'publish-refused', batch)

    def finish(self, flight, products):
        if not all(products.get(pid, {}).get('available') == p['target'] for pid, p in flight['products'].items()): return False
        self.event(flight['change_id'], 'published', flight['change_id'])
        self.data['lastStockRelease'] = dict(actor='stock-sync', change_id=flight['change_id'], undo='That was a stock update from the till')
        for pid, p in flight['products'].items():
            pending = self.data['pending'].get(pid)
            if pending and pending['crossing'] == p['crossing']:
                self.data['pending'].pop(pid)
            elif pending and pending['till'] == p['till']:
                # A later crossing starts from the word this release just published.
                pending['base'] = p['target']
        for code, st in self.data['sets'].items():
            if st['state'] == 'open' and not any(p['held'] == code for p in self.data['pending'].values()): st['state'] = 'done'
        return True

    def paused(self):
        path = self.state / 'conversation.sqlite3'
        if not path.exists(): return False
        with contextlib.closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            return bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='control'").fetchone() and db.execute("SELECT 1 FROM control WHERE name='paused'").fetchone())

    def wait(self, reason, batch):
        for pid in batch:
            if pid in self.data['pending'] and not self.data['pending'][pid]['parked']:
                self.data['pending'][pid]['attempts'] += 1; self.data['pending'][pid]['reason'] = reason
        self.save(); self.totals(reason); return reason


def decision(state, code, owner, yes):
    """Caller MUST authenticate sender+chat, exclude groups, and pass the owner role."""
    if owner not in ('owner', 'operator') and not (isinstance(owner, str) and audit.ROLE_RE.fullmatch(owner) and owner.startswith('owner:')): return False
    queue = StockSite(state, None, None)
    with queue.locked() as held:
        if not held: return False
        queue.data = queue.load()
        s = queue.data['sets'].get(code)
        if not s or s['state'] != 'open' or (yes and s['approved_by']): return False
        s.update(approved_by=owner, approved_at=datetime.now(timezone.utc).isoformat())
        if not yes:
            for pid, p in list(queue.data['pending'].items()):
                if p['held'] == code: queue.drop(pid, 'declined')
            s['state'] = 'dropped'
        queue.save(); return True

def approve(state, code, owner): return decision(state, code, owner, True)
def decline(state, code, owner): return decision(state, code, owner, False)

def main():
    from hass import host, publish_live, sandbox
    from hass.clover.config import from_settings
    from hass.sandbox_editor import SiteEditor
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['run']); ap.add_argument('--host', required=True)
    args = ap.parse_args()
    try:
        cfg = host.load_host(args.host)
        clover = from_settings(cfg['clover'])
        if clover.site_stock == 'off': return 0
        mode = sandbox.policy(cfg)
        if mode['hold'] or 'site' not in mode['live']: return 0
        live = publish_live.LiveEditor(cfg['state'], cfg['release'], Path(args.host).resolve().parent)
        site = SiteEditor(cfg['state'], host.site_gate(cfg), lambda: live)
        live.environment_guard = site.check_environment
        StockSite(cfg['state'], clover, live, preparer=site.prepare).run()
        return 0
    except (OSError, ValueError, KeyError, TypeError, cache.CacheUnsafe): return 1

if __name__ == '__main__': sys.exit(main())
