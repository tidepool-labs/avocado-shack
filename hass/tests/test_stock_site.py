"""Stock queue acceptance: private fake till, real editor/ops/policy; no network."""
import json
import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch

from hass import audit, auto_policy, editor, live_policy, stock_site as s
from hass.clover import cache
from hass.clover.config import CloverConfig, from_settings, ConfigProblem
from hass.tests.test_editor import WriterRepo, git


class Crash(BaseException): pass


class FakeLive:
    def __init__(self, case):
        self.case, self.wt, self.cfg = case, case.repo.wt, {'dailyCap': 10}
        self.calls, self.states, self.used, self.day = [], {}, 0, ''
        self.refuse, self.unsettled = False, False

    def prepare(self, ops):
        return editor.prepare({'ops': ops}, state=self.case.repo.state, now=self.case.now)

    def baseline(self, books, cid):
        if self.unsettled: raise ValueError('baseline')

    def load(self): return {}, []
    def reconcile(self): pass
    def entry_state(self, cid): return self.states.get(cid)

    def cap_used(self, books):
        day = self.case.now.date().isoformat()
        if day != self.day: self.used, self.day = 0, day
        return self.used

    def apply(self, cid, dh):
        if self.refuse: return {'result': 'refused'}
        draft = editor.show(cid, state=self.case.repo.state)['draft']
        self.case.assertEqual(live_policy.check(draft), [])
        self.case.assertLessEqual(len(draft['ops']), min(editor.MAX_OPS, live_policy.MAX_RECORDS))
        for op in draft['ops']:
            self.case.assertEqual(set(op['args']), {'id', 'available'})
            self.case.assertIn(op['args']['available'], ('no', 'yes', 'limited'))
        out = editor.apply(cid, dh, state=self.case.repo.state, now=self.case.now)
        self.case.assertEqual(out['result'], 'applied', out)
        self.calls.append(draft['ops']); self.used += 1; self.states[cid] = 'live'
        return out


class StockCase(unittest.TestCase):
    def setUp(self):
        self.repo = WriterRepo(); self.addCleanup(self.repo.cleanup)
        self.now = datetime.now(ZoneInfo('America/Los_Angeles')).replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=1)
        self.cfg = CloverConfig('sandbox', 'FAKEMERCHANT1', '/not-read', site_stock='auto')
        self.live = FakeLive(self)
        self.products_path = self.repo.wt / 'hass/content/products.json'
        self.store_path = self.repo.wt / 'hass/content/store.json'
        self.original = json.loads(self.products_path.read_text())
        self.products = [p for p in self.original['products'] if p['status'] == 'active'][:141]
        self.ids = [p['id'] for p in self.products]
        for p in self.products: p.update(available='yes', available_on=self.today())
        self.links = {pid: {'cloverId': 'T' + str(n)} for n, pid in enumerate(self.ids)}
        self.stocks = {pid: 3 for pid in self.ids}
        self.hidden, self.missing = set(), set()
        self.configure()
        self.root = self.repo.state / 'clover'; self.root.mkdir(mode=0o700)
        self.path = self.root / 'site-stock.json'
        self.write_links()

    def today(self): return self.now.astimezone(ZoneInfo('America/Los_Angeles')).date().isoformat()

    def configure(self):
        editor._write_json(self.products_path, self.original)
        self.check_today()
        git(self.repo.wt, 'add', '-A'); git(self.repo.wt, 'commit', '-qm', 'fixture stock')

    def check_today(self):
        store = json.loads(self.store_path.read_text()); store['selection_checked_on'] = self.today()
        editor._write_json(self.store_path, store)

    def write_links(self): editor._write_json(self.root / 'links.json', self.links)

    def queue(self): return s.StockSite(self.repo.state, self.cfg, self.live, clock=lambda: self.now)

    def pull(self, **changes):
        self.now += timedelta(minutes=15)
        self.stocks.update(changes)
        rows = []
        for pid, link in self.links.items():
            if pid in self.missing: continue
            rows.append(dict(id=link['cloverId'], name='Fixture item', sku='PRIVATE-SKU', code='', price_cents=12345,
                price_type='FIXED', unit_name='', category_ids='[]', categories='[]', hidden=int(pid in self.hidden), available=1,
                stock=None if self.stocks[pid] is None else str(self.stocks[pid]), stock_modified=None, modified_time=0))
        cache.write_items(self.repo.state, rows, self.now, cache.identity_of(self.cfg))

    def runq(self): return self.queue().run()
    def data(self): return json.loads(self.path.read_text())
    def sets(self): return self.data()['sets']
    def yes(self):
        code = next(c for c, st in reversed(list(self.sets().items())) if st['state'] == 'open')
        self.assertTrue(s.approve(self.repo.state, code, 'owner')); return code
    def baseline(self): self.pull(); self.runq(); self.assertFalse(self.data()['pending'])
    def change(self, pid, **fields):
        doc = json.loads(self.products_path.read_text())
        next(p for p in doc['products'] if p['id'] == pid).update(fields)
        editor._write_json(self.products_path, doc)
        git(self.repo.wt, 'add', '-A'); git(self.repo.wt, 'commit', '-qm', 'fixture owner edit')
    def published(self): return [r for r in audit.AuditLog(self.repo.state, lambda: self.now).rows() if r['step'] == 'published']

    def test_deferred_crossing_applied_once(self):
        self.baseline(); pid = self.ids[0]; self.pull(**{pid: 0})
        with editor._writer_lock(self.repo.state): self.assertEqual(self.runq(), 'writer-busy')
        self.assertEqual(self.data()['pending'][pid]['target'], 'no')
        self.pull(); self.assertEqual(self.runq(), 'live')
        for _ in range(2): self.pull(); self.runq()
        self.assertEqual(len(self.live.calls), 1); self.assertEqual(len(self.published()), 1)

    def test_publish_refused_and_cap_reserve_retry(self):
        self.baseline(); pid = self.ids[0]; self.pull(**{pid: 0})
        self.live.refuse = True; self.assertEqual(self.runq(), 'publish-refused')
        self.live.refuse = False; self.live.used = 7
        self.pull(); self.assertEqual(self.runq(), 'cap-reserve')
        self.live.used = 0; self.pull(); self.assertEqual(self.runq(), 'live')
        self.assertEqual(len(self.live.calls), 1)

    def test_failed_partial_stale_identity_and_duplicate_byte_identical(self):
        self.baseline(); pid = self.ids[0]; self.pull(**{pid: 0})
        with editor._writer_lock(self.repo.state): self.runq()
        before = self.path.read_bytes()
        cache.record_failure(self.repo.state, 'unreachable', self.now, identity=cache.identity_of(self.cfg))
        self.assertEqual(self.runq(), 'no-read'); self.assertEqual(self.path.read_bytes(), before)
        self.pull(); self.now += timedelta(minutes=21)
        self.assertEqual(self.runq(), 'no-read'); self.assertEqual(self.path.read_bytes(), before)
        self.missing = set(self.ids[:30]); self.pull()
        self.assertEqual(self.runq(), 'short-read'); self.assertEqual(self.path.read_bytes(), before)
        self.missing.clear(); self.pull(); self.cfg = replace(self.cfg, merchant_id='OTHERFAKE001')
        self.assertEqual(self.runq(), 'no-read'); self.assertEqual(self.path.read_bytes(), before)
        self.cfg = replace(self.cfg, merchant_id='FAKEMERCHANT1'); self.assertEqual(self.runq(), 'live')
        before = self.path.read_bytes(); self.runq(); self.assertEqual(self.path.read_bytes(), before)

    def test_reversal_and_owner_wins(self):
        self.baseline(); a, b = self.ids[:2]; self.pull(**{a: 0, b: 0})
        with editor._writer_lock(self.repo.state): self.runq()
        self.change(b, available='limited'); self.pull(**{a: 4}); self.runq()
        self.assertFalse(self.data()['pending']); self.assertFalse(self.live.calls)
        self.assertEqual(len(audit.AuditLog(self.repo.state, lambda: self.now).rows()), 1)

    def test_corrupt_file_and_second_run_lock(self):
        self.baseline(); self.path.write_bytes(b'{')
        with self.assertRaises(ValueError): self.runq()
        self.assertEqual(self.path.read_bytes(), b'{')
        with self.queue().locked(): self.assertEqual(self.runq(), 'busy')
        self.assertEqual(self.path.read_bytes(), b'{'); self.assertFalse(self.live.calls)

    def put(self, data): self.path.write_text(json.dumps(data, sort_keys=True))

    def healthy(self):
        # Contract: a private file that is whole loads. Bug it catches: the new checks refusing a real state.
        data = json.loads(self.clean); pid = self.ids[0]
        words = {pid: dict(till='T0', base='yes', target='no')}
        data['sets']['stk-fixture'] = dict(hash=s.digest(words), words=words, approved_by=None, approved_at=None, state='open')
        data['counts'][pid] = dict(till='T0', count='12.5')
        data['inflight'] = dict(change_id='fixture-change', products={})
        data['pending'][pid] = dict(target='no', base='yes', till='T0', crossing='c1', first=1.5, attempts=0, reason='', held=None, parked=None, new=False)
        return data

    def test_healthy_state_still_loads(self):
        self.baseline(); self.clean = self.path.read_bytes(); data = self.healthy(); self.put(data)
        self.assertEqual(self.queue().load(), data)
        data['inflight'] = None; self.put(data); self.assertEqual(self.queue().load(), data)

    def test_damaged_state_refused_with_fixed_value_error(self):
        # Contract: a damaged private file is refused with its own fixed ValueError, never a crash or a value.
        # Bug it catches: KeyError/AttributeError/TypeError/InvalidOperation tracebacks, or a half-read file accepted.
        self.baseline(); self.clean = self.path.read_bytes(); pid = self.ids[0]
        def setfield(key, value):
            def edit(d):
                st = self.healthy()['sets']['stk-fixture']
                if value is KeyError: del st[key]
                else: st[key] = value
                d['sets']['stk-fixture'] = st
            return edit
        def hold(key, value): return lambda d: d.update({key: value})
        def entry(**c):
            def edit(d):
                d['counts'][pid] = dict(till='T0', count='1'); d['counts'][pid].update(c)
                for k in [k for k, v in c.items() if v is KeyError]: del d['counts'][pid][k]
            return edit
        def first(value): return lambda d: d['pending'].__setitem__(pid, dict(self.healthy()['pending'][pid], first=value))
        cases = [('stock set', 'no hash', setfield('hash', KeyError)), ('stock set', 'hash null', setfield('hash', None)),
                 ('stock set', 'hash number', setfield('hash', 7)), ('stock set', 'wrong hash', setfield('hash', '0' * 64)),
                 ('stock inflight', 'text', hold('inflight', 'LEAK')), ('stock inflight', 'list', hold('inflight', [])),
                 ('stock inflight', 'empty', hold('inflight', {})), ('stock inflight', 'no products', hold('inflight', dict(change_id='LEAK'))),
                 ('stock inflight', 'no change', hold('inflight', dict(products={}))),
                 ('stock count', 'text', lambda d: d['counts'].__setitem__(pid, 'LEAK')), ('stock count', 'null', lambda d: d['counts'].__setitem__(pid, None)),
                 ('stock count', 'list', lambda d: d['counts'].__setitem__(pid, [])), ('stock count', 'no count', entry(count=KeyError)),
                 ('stock count', 'no till', entry(till=KeyError)), ('stock count', 'till number', entry(till=5)),
                 ('stock count', 'count null', entry(count=None)), ('stock count', 'count number', entry(count=3)),
                 ('stock count', 'count text', entry(count='LEAK')), ('stock count', 'count nan', entry(count='NaN')),
                 ('stock count', 'count infinite', entry(count='-Infinity')),
                 ('stock pending', 'first true', first(True)), ('stock pending', 'first false', first(False))]
        for message, name, edit in cases:
            with self.subTest(f'{message}: {name}'):
                data = self.healthy(); edit(data); self.put(data); before = self.path.read_bytes()
                with self.assertRaises(ValueError) as caught: self.runq()
                self.assertEqual(str(caught.exception), message)
                self.assertNotIn('LEAK', str(caught.exception)); self.assertEqual(self.path.read_bytes(), before)

    def test_pause_is_not_bypassed(self):
        self.baseline(); self.pull(**{self.ids[0]: 0})
        with sqlite3.connect(self.repo.state / 'conversation.sqlite3') as db:
            db.execute('CREATE TABLE control(name TEXT, set_at TEXT)')
            db.execute("INSERT INTO control VALUES ('paused', 'fixture')")
        self.assertEqual(self.runq(), 'paused'); self.assertFalse(self.live.calls)
        with sqlite3.connect(self.repo.state / 'conversation.sqlite3') as db: db.execute('DELETE FROM control')
        self.pull(); self.assertEqual(self.runq(), 'live')

    def test_first_sync_preview_only(self):
        for pid in self.ids[:9]: self.stocks[pid] = 0
        for pid in self.ids[9:133]: self.change_in_memory(pid, None)
        self.configure(); self.pull(); self.assertEqual(self.runq(), 'held')
        self.assertEqual(len(self.products), 141); self.assertEqual(len(self.sets()), 1)
        self.assertEqual(len(self.data()['pending']), 133); self.assertFalse(self.live.calls)
        report = next((self.root / 'reports').glob('stock-reconcile-*-stk-*.md'))
        self.assertEqual(report.stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(report.read_text().splitlines()), 134)
        code = next(iter(self.sets())); self.pull(); self.runq(); self.assertEqual(list(self.sets()), [code])
        self.assertTrue(s.decline(self.repo.state, code, 'owner')); self.pull(); self.runq()
        self.assertFalse(self.data()['pending']); self.pull(**{self.ids[0]: 4}); self.runq()
        self.pull(**{self.ids[0]: 0}); self.runq()
        self.assertEqual(len(self.live.calls), 1)

    def change_in_memory(self, pid, word):
        product = next(p for p in self.products if p['id'] == pid)
        if word is None: product.pop('available', None); product.pop('available_on', None)
        else: product['available'] = word

    def large_set(self):
        for pid in self.ids[:133]: self.change_in_memory(pid, None)
        self.configure(); self.pull(); self.runq(); return self.yes()

    def test_first_sync_batches_over_limit(self):
        code = self.large_set()
        for _ in range(7): self.pull(); self.assertEqual(self.runq(), 'live')
        self.pull(); self.assertEqual(self.runq(), 'cap-reserve')
        self.now += timedelta(days=1); self.check_today()
        git(self.repo.wt, 'add', '-A'); git(self.repo.wt, 'commit', '-qm', 'next day check')
        for _ in range(7): self.pull(); self.assertEqual(self.runq(), 'live')
        self.pull(); self.runq()
        self.assertEqual([len(ops) for ops in self.live.calls], [10] * 13 + [3])
        ids = [op['args']['id'] for batch in self.live.calls for op in batch]
        self.assertEqual(len(set(ids)), 133); self.assertEqual(len(self.published()), 14)
        self.assertEqual(self.sets()[code]['state'], 'done'); self.assertFalse(self.data()['pending'])

    def test_crash_after_batch_five_no_second_release(self):
        self.large_set()
        for _ in range(4): self.pull(); self.runq()
        self.pull()
        with patch.object(s.StockSite, 'finish', side_effect=Crash), self.assertRaises(Crash): self.runq()
        self.assertEqual(len(self.live.calls), 5)
        self.pull(); self.runq(); self.assertEqual(len(self.live.calls), 6)
        self.assertEqual(len(self.published()), 6)

    def test_crash_after_publish_then_stock_reverses(self):
        self.baseline(); pid = self.ids[0]; self.pull(**{pid: 0})
        with patch.object(s.StockSite, 'finish', side_effect=Crash), self.assertRaises(Crash): self.runq()
        self.assertEqual(len(self.live.calls), 1)
        self.pull(**{pid: 3}); self.assertEqual(self.runq(), 'live')
        product = next(p for p in json.loads(self.products_path.read_text())['products'] if p['id'] == pid)
        self.assertEqual(product['available'], 'yes')
        self.assertNotIn(pid, self.data()['pending'])
        self.assertEqual([batch[0]['args']['available'] for batch in self.live.calls], ['no', 'yes'])
        self.assertEqual(len(self.published()), 2)
        self.pull(); self.assertEqual(self.runq(), 'ok'); self.assertEqual(len(self.live.calls), 2)

    def test_crash_before_inflight_and_unsettled(self):
        self.baseline(); self.pull(**{self.ids[0]: 0})
        prepare = self.live.prepare
        def crash(ops): prepare(ops); raise Crash()
        with patch.object(self.live, 'prepare', side_effect=crash), self.assertRaises(Crash): self.runq()
        self.assertIsNone(self.data()['inflight']); self.pull(); self.runq(); self.assertEqual(len(self.live.calls), 1)
        self.pull(**{self.ids[1]: 0}); self.live.refuse = True; self.runq()
        cid = self.data()['inflight']['change_id']; self.live.states[cid] = 'not-published'; self.live.unsettled = True
        self.pull(); self.assertEqual(self.runq(), 'publish-refused'); self.assertIsNotNone(self.data()['inflight'])
        self.live.unsettled = False; self.live.refuse = False; self.live.states[cid] = 'not-applied'
        self.pull(); self.runq(); self.assertEqual(len(self.live.calls), 2)

    def test_decline_after_batch_three(self):
        code = self.large_set()
        for _ in range(3): self.pull(); self.runq()
        self.assertTrue(s.decline(self.repo.state, code, 'owner'))
        self.pull(); self.runq(); self.assertEqual(len(self.live.calls), 3); self.assertFalse(self.data()['pending'])

    def test_deferred_over_limit(self):
        # More than 250 links makes 25 Sold outs stay below the mass guard.
        for n in range(160):
            pid = f'gap-{n}'; self.links[pid] = {'cloverId': f'GAP{n}'}; self.stocks[pid] = 3
        self.write_links()
        self.baseline()
        for mode in ('auto', 'draft'):
            self.cfg = replace(self.cfg, site_stock=mode); self.live.used = 0
            target = 0 if mode == 'auto' else 3
            self.pull(**{pid: target for pid in self.ids[:25]})
            with editor._writer_lock(self.repo.state): self.runq()
            if mode == 'draft': self.yes()
            start = len(self.live.calls)
            for _ in range(3): self.pull(); self.runq()
            self.assertEqual([len(b) for b in self.live.calls[start:]], [10, 10, 5])
            self.pull(); self.runq(); self.assertEqual(len(self.live.calls), start + 3)

    def test_pending_ineligible_then_eligible(self):
        self.baseline(); pid = self.ids[0]; self.pull(**{pid: 0})
        with editor._writer_lock(self.repo.state): self.runq()
        attempts = self.data()['pending'][pid]['attempts']
        self.hidden.add(pid); self.pull(); self.runq()
        self.assertEqual(self.data()['pending'][pid]['parked'], 'hidden')
        self.missing.add(pid); self.pull(); self.runq()
        self.assertEqual(self.data()['pending'][pid]['parked'], 'not-in-read')
        self.assertEqual(self.data()['pending'][pid]['attempts'], attempts)
        self.missing.clear(); self.hidden.clear(); self.pull(); self.runq()
        for _ in range(2): self.pull(); self.runq()
        self.assertEqual(len(self.live.calls), 1)

    def test_no_count_inactive_and_target_rechecked(self):
        self.baseline(); a, b = self.ids[:2]; self.pull(**{a: 0, b: 0})
        with editor._writer_lock(self.repo.state): self.runq()
        self.change(b, status='hidden'); self.pull(**{a: None}); self.runq()
        self.assertEqual(self.data()['pending'][a]['parked'], 'no-count')
        self.assertEqual(self.data()['pending'][b]['parked'], 'not-active')
        self.change(b, status='active'); self.pull(**{a: 4}); self.runq()
        self.assertNotIn(a, self.data()['pending']); self.assertEqual(len(self.live.calls), 1)

    def test_unlink_relink_and_gone(self):
        self.baseline(); a, b, c = self.ids[:3]; self.pull(**{a: 0, b: 0, c: 0})
        with editor._writer_lock(self.repo.state): self.runq()
        self.links.pop(a); self.links[b]['cloverId'] = 'NEWITEM'; self.write_links()
        doc = json.loads(self.products_path.read_text()); doc['products'] = [p for p in doc['products'] if p['id'] != c]
        editor._write_json(self.products_path, doc); git(self.repo.wt, 'add', '-A'); git(self.repo.wt, 'commit', '-qm', 'fixture removal')
        self.pull(); self.runq(); pending = self.data()['pending']
        self.assertEqual(list(pending), [b]); self.assertTrue(pending[b]['held']); self.assertFalse(self.live.calls)

    def test_approved_set_word_changes_get_new_preview(self):
        self.change_in_memory(self.ids[0], None); self.configure(); self.pull(); self.runq(); code = self.yes()
        self.hidden.add(self.ids[0]); self.pull(); self.runq()
        self.hidden.clear(); self.pull(**{self.ids[0]: 0}); self.runq()
        self.assertNotEqual(self.data()['pending'][self.ids[0]]['held'], code); self.assertFalse(self.live.calls)

    def test_missing_first_read_and_new_link(self):
        self.pull(); self.now += timedelta(minutes=21); self.assertEqual(self.runq(), 'no-read'); self.assertFalse(self.path.exists())
        pid = self.ids[0]; self.missing.add(pid); self.pull(); self.runq()
        self.assertNotIn(pid, self.data()['counts']); self.assertFalse(self.live.calls)
        self.assertIn('not found in the till read', next((self.root / 'reports').glob('*-gaps.md')).read_text())
        report = (self.root / 'reports/site-stock-totals.json').read_text()
        self.assertNotIn('PRIVATE-SKU', report)
        self.missing.clear(); self.stocks[pid] = 0; self.pull(); self.runq()
        self.assertEqual(len(self.sets()), 1); self.assertTrue(self.data()['pending'][pid]['new'])

    def test_mass_guard_warning_and_off_default(self):
        for pid in self.ids[:25]: self.stocks[pid] = 0
        self.pull(); self.runq(); self.assertFalse(self.live.calls)
        self.assertIn('unusual', next(iter(self.sets().values()))['summary'])
        self.cfg = replace(self.cfg, site_stock='off'); before = self.path.read_bytes()
        with patch.object(self.live, 'prepare', side_effect=AssertionError): self.assertEqual(self.runq(), 'off')
        self.assertEqual(self.path.read_bytes(), before)
        raw = dict(environment='sandbox', merchantId='FAKEMERCHANT1', tokenFile='/not-read')
        self.assertEqual(from_settings(raw).site_stock, 'off')
        with self.assertRaises(ConfigProblem): from_settings(dict(raw, siteStock='bad'))
        ops = [{'op': 'product.set_availability', 'args': {}}] * 10
        self.assertTrue(auto_policy.qualifies(ops, ['product.set_availability'], False)[0])
        self.assertFalse(auto_policy.qualifies(ops + ops, ['product.set_availability'], False)[0])

    def test_stale_shelf_check_still_allows_word_updates(self):
        self.baseline(); self.pull(**{pid: 0 for pid in self.ids[:10]})
        yesterday = (self.now - timedelta(days=1)).astimezone(ZoneInfo('America/Los_Angeles')).date().isoformat()
        for p in self.products: p['available_on'] = yesterday
        editor._write_json(self.products_path, self.original)
        store = json.loads(self.store_path.read_text()); store['selection_checked_on'] = yesterday
        editor._write_json(self.store_path, store); git(self.repo.wt, 'add', '-A'); git(self.repo.wt, 'commit', '-qm', 'older check')
        self.pull(); self.assertEqual(self.runq(), 'live'); self.assertEqual(len(self.live.calls[0]), 10)
        self.assertEqual(json.loads(self.store_path.read_text())['selection_checked_on'], yesterday)
        updated = json.loads(self.products_path.read_text())['products']
        self.assertEqual(next(p for p in updated if p['id'] == self.ids[0])['available_on'], self.today())

    def test_shelf_check_and_prepare_race(self):
        self.baseline(); self.pull(**{pid: 0 for pid in self.ids[:10]})
        yesterday = (self.now - timedelta(days=1)).astimezone(ZoneInfo('America/Los_Angeles')).date().isoformat()
        for p in self.products: p['available_on'] = yesterday
        editor._write_json(self.products_path, self.original)
        store = json.loads(self.store_path.read_text()); store['selection_checked_on'] = yesterday
        editor._write_json(self.store_path, store); git(self.repo.wt, 'add', '-A'); git(self.repo.wt, 'commit', '-qm', 'no check')
        self.assertFalse(self.live.calls)  # the race below starts before any prepare
        self.check_today(); git(self.repo.wt, 'add', '-A'); git(self.repo.wt, 'commit', '-qm', 'check restored')
        pid = self.ids[0]; prepare = self.live.prepare
        def race(ops):
            if ops[0]['args']['id'] == pid: self.change(pid, status='hidden')
            return prepare(ops)
        with patch.object(self.live, 'prepare', side_effect=race): self.pull(); self.runq()
        self.assertEqual(self.data()['pending'][pid]['parked'], 'editor-refused'); self.assertEqual(len(self.live.calls[0]), 9)

    def test_real_live_apply_baseline_and_owner_undo_target(self):
        from hass import publish_live, release_journal
        from hass.ops import load_registry
        from hass.tests import test_publish_live
        fixture = test_publish_live.ReleaseCase('test_happy_then_second_release_and_derived_head')
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        products, store = self.products_path.read_bytes(), self.store_path.read_bytes()
        self.repo = fixture.repo
        self.products_path = self.repo.wt / 'hass/content/products.json'
        self.store_path = self.repo.wt / 'hass/content/store.json'
        self.products_path.write_bytes(products); self.store_path.write_bytes(store)
        # MAIN-RED-AVOCADO-SHACK: from 23:30 Pacific the two pull() steps (+15 min each) crossed the shop
        # midnight, so the shelf check was stale ('not-checked-today'). The release fixture needs the real
        # clock, so start an hour earlier in that late window instead of leaving the day.
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        if self.now.astimezone(ZoneInfo('America/Los_Angeles')).hour >= 23: self.now -= timedelta(hours=1)
        self.check_today()
        git(self.repo.wt, 'add', '-A'); git(self.repo.wt, 'commit', '-qm', 'fixture site stock')
        fixture.now = self.now
        self.live = fixture.live
        self.live.registry = load_registry()
        self.live.clock = lambda: self.now
        self.live.prepare = lambda ops: editor.prepare({'ops': ops}, state=self.repo.state, now=self.now)
        def build(commit, today, cid, label, checks=False):
            return {'index.html': git(self.repo.wt, 'show', commit + ':hass/content/products.json').encode(),
                    'style.css': b'fixture css', 'community.json': b'{}'}
        self.live.build = build
        publish_live.sitegen.write_files(build(self.repo.head(), '', '', ''), fixture.site)
        git(fixture.site, 'add', '-A'); git(fixture.site, 'commit', '-qm', 'fixture baseline')
        git(fixture.site, 'push', '-q', 'origin', 'main')
        release_journal.atomic(fixture.hostdir / 'publish.json', dict(anchor_site_commit=git(fixture.site, 'rev-parse', 'HEAD'),
            anchor_build_today=self.today(), anchor_seq=0, anchor_at=self.now.isoformat()))
        self.root = self.repo.state / 'clover'; self.root.mkdir(mode=0o700)
        self.path = self.root / 'site-stock.json'; self.write_links()
        self.change(self.ids[0], available='no', available_on=self.today())
        # Re-anchor after this fixture edit; the queue must not move writer HEAD before live.apply.
        publish_live.sitegen.write_files(build(self.repo.head(), '', '', ''), fixture.site)
        git(fixture.site, 'add', '-A'); git(fixture.site, 'commit', '-qm', 'initial sold out')
        git(fixture.site, 'push', '-q', 'origin', 'main')
        release_journal.atomic(fixture.hostdir / 'publish.json', dict(anchor_site_commit=git(fixture.site, 'rev-parse', 'HEAD'),
            anchor_build_today=self.today(), anchor_seq=0, anchor_at=self.now.isoformat()))
        self.pull(); self.runq(); self.yes(); self.pull()
        with patch.object(self.live, 'apply', wraps=self.live.apply) as apply:
            self.assertEqual(self.runq(), 'live'); self.assertEqual(apply.call_count, 1)
        self.assertEqual(fixture.push_calls, 1)
        self.live.baseline(self.live.load()[0], 'acceptance-readback')
        cid = self.data()['lastStockRelease']['change_id']
        self.assertEqual(self.data()['lastStockRelease']['actor'], 'stock-sync')
        self.assertEqual(self.data()['lastStockRelease']['undo'], 'That was a stock update from the till')
        # Existing revert-last chooses the latest landed change, even an automatic one.
        with patch.object(self.live, 'prepare', return_value={'result': 'refused'}) as undo:
            self.live.revert_last()
            self.assertEqual(undo.call_args.args[0], [{'op': 'history.revert', 'args': {'changeId': cid}}])


if __name__ == '__main__': unittest.main()
