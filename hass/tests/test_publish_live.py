"""Fixture-only release integration: local bare Git, real editor, injected clock/fetch/faults."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hass import conversation, editor, host, publish_live as p, release_journal as r
from hass.tests.test_conversation import SETTINGS, T0
from hass.tests.test_editor import WriterRepo, _req, git, HOURS, NEW_HOURS
from hass.tests import fixture_ops
from hass.ops import load_registry


class Crash(BaseException): pass


class ReleaseCase(unittest.TestCase):
    def setUp(self):
        fixture_ops.allow_live(self)
        self.repo = WriterRepo()
        self.addCleanup(self.repo.cleanup)
        self.tmp = tempfile.TemporaryDirectory(prefix='hass-release-')
        self.addCleanup(self.tmp.cleanup)
        # The release engine refuses a site checkout under any symlinked folder (LiveEditor.tree), so the fixture root must be
        # the real path: a TMPDIR that is itself a link (a /dev/shm scratch link, say) must not turn into a baseline alert.
        self.root = Path(self.tmp.name).resolve()
        self.hostdir = self.root / 'host'
        self.hostdir.mkdir(mode=0o700)
        self.site = self.root / 'site'
        self.bare = self.root / 'remote.git'
        git(self.root, 'init', '--bare', '-q', '-b', 'main', str(self.bare))
        git(self.root, 'clone', '-q', str(self.bare), str(self.site))
        git(self.site, 'config', 'user.name', 'fixture')
        git(self.site, 'config', 'user.email', 'fixture@example.invalid')
        self.cfg = dict(siteCheckout=str(self.site), siteRemote=p.REMOTE, liveUrl=p.URL,
                        stopFile=str(self.root / 'STOP'), dailyCap=10, minIntervalSeconds=60, verifyMinutes=5)
        cfg = editor._read(self.repo.state / 'config.json')
        cfg['settings'] = {**SETTINGS, 'liveSite': 'theavocadoman.com', 'approvalNeedsCode': True}
        editor._write_json(self.repo.state / 'config.json', cfg)
        self.now = T0.replace(day=7)
        self.push_calls = 0
        self.fault = None
        self.messages = []
        self.live = self.open()
        self.base = self.fixture_build(self.repo.head(), self.live.day(), 'seed', 'base')
        p.sitegen.write_files(self.base, self.site)
        git(self.site, 'add', '-A')
        git(self.site, 'commit', '-q', '-m', 'seed')
        git(self.site, 'push', '-q', 'origin', 'main')
        self.site_before = git(self.site, 'rev-parse', 'HEAD')
        r.atomic(self.hostdir / 'publish.json', dict(anchor_site_commit=self.site_before,
            anchor_build_today=self.live.day(), anchor_seq=0, anchor_at=self.now.isoformat()))

    def fixture_build(self, commit, today, cid, label, checks=False):
        data = git(self.repo.wt, 'show', commit + ':hass/content/store.json').encode()
        return {'index.html': data, 'style.css': b'fixture css', 'community.json': b'{}'}

    def wrapper(self, cwd, *args):
        if args == ('remote', 'get-url', 'origin'): return p.REMOTE
        if args[0] == 'push':
            self.push_calls += 1
            # The pushing record must already exist before exec starts.
            self.assertEqual(self.live.books.journals()[-1]['state'], 'pushing')
        if self.fault: self.fault(cwd, args)
        return git(cwd, *args)

    def fetch(self, url, base):
        rel = url.split(base + '/', 1)[1].split('?', 1)[0]
        if rel == 'index.html' or rel.endswith('/index.html'): raise ValueError('redirect')  # Pages answers 308
        if rel == '' or rel.endswith('/'): rel += 'index.html'
        elif '.' not in rel.rsplit('/', 1)[-1]: rel += '.html'
        return subprocess.run(['git', '-C', str(self.bare), 'show', 'main:' + rel], capture_output=True, check=True).stdout

    def open(self):
        live = p.LiveEditor(self.repo.state, self.cfg, self.hostdir, registry={**fixture_ops.registry(), 'history.revert': load_registry()['history.revert']},
                           clock=lambda: self.now, sleep=self.wait, git=self.wrapper, fetch=self.fetch)
        live.build = self.fixture_build
        live.conv = SimpleNamespace(outbox=SimpleNamespace(add=lambda chat, text, attachments: self.messages.append((text, attachments))),
                                    screenshot=lambda cid: 'fixture-picture.png')
        live._code = lambda cid: cid[-4:]
        return live

    def wait(self, seconds): self.now += timedelta(seconds=seconds)

    def draft(self, value=None):
        return self.repo.prepare(_req((HOURS, {'hours': value or NEW_HOURS})))['draft']

    def apply(self, draft=None):
        draft = draft or self.draft()
        return self.live.apply(draft['change_id'], draft['draft_hash'])

    def entry(self): return self.live.books.journals()[-1]

    def settle(self):
        self.live.reconcile()
        self.live.reconcile()

    def restart(self):
        self.live = self.open()
        self.settle()

    def assert_refused_unchanged(self, draft):
        writer, site = self.repo.head(), git(self.site, 'rev-parse', 'HEAD')
        books = {f.name: f.read_bytes() for f in self.live.books.directory.iterdir()}
        result = self.apply(draft)
        self.assertEqual(result['result'], 'refused')
        self.assertEqual(self.repo.head(), writer)
        self.assertEqual(git(self.site, 'rev-parse', 'HEAD'), site)
        self.assertEqual({f.name: f.read_bytes() for f in self.live.books.directory.iterdir()}, books)

    def test_happy_then_second_release_and_derived_head(self):
        d = self.draft()
        self.assertEqual(self.apply(d)['result'], 'applied')
        s1 = self.entry()['site_commit']
        self.restart()
        self.assertEqual(self.entry()['state'], 'live')
        self.assertEqual(self.messages[0][1], ['fixture-picture.png'])
        self.assertIn('Your change is on the website now.', self.messages[0][0])
        for _ in range(3): self.live.reconcile()
        self.assertEqual(len(self.messages), 1)
        self.now += timedelta(seconds=61)
        self.assertEqual(self.apply(self.draft(['Fixture new hours']))['result'], 'applied')
        self.assertEqual(self.entry()['site_before'], s1)
        self.settle()
        books, entries = self.live.load()
        self.assertEqual(len(books['pushes']), 2)
        self.assertEqual(self.push_calls, 2)
        for j in entries:
            log = git(self.bare, 'log', '--format=%s')
            self.assertEqual(log.count('hass live: ' + j['change_id']), 1)

    def test_a_listing_job_gets_its_posted_line_instead_of_the_ordinary_live_message(self):
        # Contract NPP-G S13: when the live check sees a listing job's change, the owner gets the conversation's own one-line
        # `Posted: <link>` (no picture); an ordinary change keeps "Your change is on the website now."
        # Bug: notify() always sent the ordinary line, so the S13 confirmation was never sent.
        self.live.conv.npp_posted = lambda cid: 'Posted: https://example.test/?item=x#market (say undo to take it down)'
        self.assertEqual(self.apply()['result'], 'applied')
        self.settle()
        self.assertEqual(self.entry()['state'], 'live')
        self.assertEqual(self.messages[-1], ('Posted: https://example.test/?item=x#market (say undo to take it down)', []))

    def test_gate_stop_lock_policy_site_and_exact_baseline(self):
        d = self.draft()
        stop = Path(self.cfg['stopFile'])
        stop.symlink_to(self.root / 'missing')
        self.assert_refused_unchanged(d)
        stop.unlink()
        with self.live.books.lock(): self.assert_refused_unchanged(d)
        with mock.patch.object(p.live_policy, 'check', return_value=['protected']): self.assert_refused_unchanged(d)
        (self.site / 'style.css').write_bytes(b'drift')
        self.assert_refused_unchanged(d)
        git(self.site, 'add', '-A'); git(self.site, 'commit', '-q', '-m', 'foreign')
        git(self.site, 'push', '-q', 'origin', 'main')
        self.assert_refused_unchanged(d)
        # A clean, tracked one-byte drift anchored at that commit passes G6, not G7.
        r.atomic(self.hostdir / 'publish.json', dict(anchor_site_commit=git(self.site, 'rev-parse', 'HEAD'),
            anchor_build_today=self.live.day(), anchor_seq=0, anchor_at=self.now.isoformat()))
        self.assert_refused_unchanged(d)
        self.assertEqual(self.push_calls, 0)

    def test_stale_and_bad_hash_are_not_applied_duplicate_does_not_push(self):
        d = self.draft()
        result = self.live.apply(d['change_id'], 'wrong')
        self.assertEqual(result['result'], 'refused')
        before = self.repo.head()
        with mock.patch.object(conversation.Editor, 'apply', return_value={'result': 'stale'}):
            self.assertEqual(self.apply(d)['result'], 'stale')
        self.assertEqual(self.repo.head(), before)
        self.assertEqual(self.entry()['state'], 'not-applied')
        self.assertEqual(self.push_calls, 0)
        self.assertEqual(self.apply(d)['result'], 'refused')

    def test_open_unknown_and_corrupt_books_fail_closed(self):
        d = self.draft()
        path = self.hostdir / 'publish.json'
        raw = path.read_bytes()
        for content in (None, b'{'):
            if content is None: path.unlink()
            else: path.write_bytes(content); path.chmod(0o600)
            self.assert_refused_unchanged(d)
            path.write_bytes(raw); path.chmod(0o600)
        self.assertEqual(self.apply(d)['result'], 'applied')
        self.settle()
        self.assertEqual(self.entry()['state'], 'live')

    def test_crashes_before_apply_after_apply_built_and_commit(self):
        for target in ('intent-before', 'applied-before', 'built-after', 'committed-before'):
            with self.subTest(target=target):
                # Each scenario is isolated from the prior one by re-anchoring and a new draft.
                d = self.draft([target])
                write = self.live.books.write
                def crash(j, state=None, **fields):
                    next_state = state or j['state']
                    if target == 'intent-before' and next_state == 'intent':
                        write(j, state, **fields); raise Crash()
                    if target == 'applied-before' and next_state == 'applied': raise Crash()
                    if target == 'built-after' and next_state == 'built':
                        write(j, state, **fields); raise Crash()
                    if target == 'committed-before' and next_state == 'committed': raise Crash()
                    return write(j, state, **fields)
                with mock.patch.object(self.live.books, 'write', side_effect=crash), self.assertRaises(Crash): self.apply(d)
                self.restart()
                self.assertEqual(self.entry()['state'], 'not-applied' if target == 'intent-before' else 'not-published')
                self.assertEqual(self.push_calls, 0)
                if target != 'intent-before':
                    self.assert_refused_unchanged(self.draft(['next']))
                    j = self.entry(); self.live.books.write(j, 'closed')
                    git(self.repo.wt, 'reset', '--hard', j['writer_before'])

    def test_post_push_record_failure_recovers_without_second_push(self):
        write = self.live.books.write
        def fail(j, state=None, **fields):
            if state == 'pushed': raise OSError('fixture fsync')
            return write(j, state, **fields)
        with mock.patch.object(self.live.books, 'write', side_effect=fail), self.assertRaises(OSError): self.apply()
        self.assertEqual(self.entry()['state'], 'pushing')
        self.restart()
        self.assertEqual(self.entry()['state'], 'live')
        self.assertEqual(self.push_calls, 1)

    def test_crash_after_durable_pushed_and_next_write_failure(self):
        write = self.live.books.write
        def crash(j, state=None, **fields):
            result = write(j, state, **fields)
            if state == 'pushed': raise Crash()
            return result
        with mock.patch.object(self.live.books, 'write', side_effect=crash), self.assertRaises(Crash): self.apply()
        s1 = self.entry()['site_commit']
        with mock.patch.object(self.live.books, 'write', side_effect=OSError('fixture')):
            with self.assertRaises(OSError): self.live.reconcile()
        self.restart()
        self.apply(self.draft(['Second benign change']))
        self.assertEqual(self.entry()['site_before'], s1)
        self.settle()
        self.assertEqual(len(self.live.load()[0]['pushes']), 2)

    def test_lost_response_unknown_then_landed(self):
        def lose(cwd, args):
            if args[0] == 'push':
                git(cwd, *args)
                raise subprocess.TimeoutExpired('git', 60)
            if args[0] == 'ls-remote': raise subprocess.TimeoutExpired('git', 60)
        self.fault = lose
        self.apply()
        self.settle()
        self.assertEqual(self.entry()['state'], 'unknown')
        self.assertIn('may or may not', self.messages[0][0])
        self.assertNotIn('unchanged', self.messages[0][0])
        self.assert_refused_unchanged(self.draft(['Next change']))
        self.fault = None
        self.now += timedelta(minutes=11)
        self.restart()
        self.assertEqual(self.entry()['state'], 'live')
        self.assertEqual(self.push_calls, 1)

    def test_remote_before_requires_two_observations_120_seconds(self):
        def lose(cwd, args):
            if args[0] == 'push': raise subprocess.TimeoutExpired('git', 60)
        self.fault = lose
        self.apply()
        self.live.reconcile()
        self.assertEqual(self.entry()['state'], 'unknown')
        self.now += timedelta(seconds=119)
        self.live.reconcile()
        self.assertEqual(self.entry()['state'], 'unknown')
        self.now += timedelta(seconds=1)
        self.live.reconcile()
        self.assertEqual(self.entry()['state'], 'not-published')
        self.assertIn('unchanged', self.messages[-1][0])
        self.fault = None
        self.assertEqual(self.live.operate('retry', self.entry()['change_id'])['state'], 'pushed')
        self.settle()
        self.assertEqual(self.live.operate('retry', self.entry()['change_id'])['result'], 'held')

    def test_stop_during_build_and_retry_then_stops_after_pushing_is_not_recalled(self):
        build = self.live.build
        def stop_build(*args, **kw):
            result = build(*args, **kw)
            if kw.get('checks'): Path(self.cfg['stopFile']).touch()
            return result
        self.live.build = stop_build
        self.apply()
        self.settle()
        self.assertEqual((self.entry()['state'], self.entry()['step']), ('not-published', 'stopped'))
        self.assertEqual(git(self.site, 'rev-parse', 'HEAD'), self.site_before)
        self.assertEqual(self.push_calls, 0)
        cid = self.entry()['change_id']
        self.assertEqual(self.live.operate('retry', cid)['result'], 'held')
        Path(self.cfg['stopFile']).unlink()
        self.live.build = build
        def during_push(cwd, args):
            if args[0] == 'push': Path(self.cfg['stopFile']).touch()
        self.fault = during_push
        self.live.operate('retry', cid)
        self.settle()
        self.assertEqual(self.entry()['state'], 'live')
        self.assertNotIn('stopped', self.messages[-1][0])
        self.assertEqual(self.push_calls, 1)

    def test_stop_between_connection_retries(self):
        def refuse_connect(cwd, args):
            if args[0] == 'push':
                Path(self.cfg['stopFile']).touch()
                raise subprocess.CalledProcessError(128, 'git', stderr=b'connect to host fixture port 22: Connection refused')
        self.fault = refuse_connect
        self.apply()
        self.assertEqual(self.entry()['step'], 'stopped')
        self.assertEqual(self.push_calls, 1)

    def test_stop_during_interval_wait_before_intent_and_daily_cap(self):
        self.apply(); self.settle()
        d = self.draft(['Later fixture hours'])
        self.live.cfg['dailyCap'] = 1
        self.assert_refused_unchanged(d)
        self.live.cfg['dailyCap'] = 10
        def wait(seconds):
            self.wait(seconds)
            Path(self.cfg['stopFile']).touch()
        self.live.sleep = wait
        self.assert_refused_unchanged(d)
        self.assertEqual(self.push_calls, 1)

    def test_unconfirmed_then_live_notifications_and_wrong_cli_states(self):
        self.apply()
        self.live.fetch = lambda *a: b'wrong'
        self.now += timedelta(minutes=6)
        self.settle()
        self.assertEqual(self.entry()['state'], 'unconfirmed')
        self.assertIn("can't see", self.messages[-1][0])
        cid = self.entry()['change_id']
        self.assertEqual(self.live.operate('unblock', cid)['result'], 'wrong-state')
        self.live.fetch = self.fetch
        self.now += timedelta(minutes=10)
        self.settle()
        self.assertEqual(self.entry()['state'], 'live')
        self.assertEqual(self.live.operate('resolve', cid, resolution='live')['result'], 'wrong-state')

    def test_live_check_requests_pages_urls_without_redirect(self):
        seen = []
        real = self.fetch
        def spy(url, base): seen.append(url); return real(url, base)
        self.live.fetch = spy
        self.apply(); self.settle()
        self.assertEqual(self.entry()['state'], 'live')
        self.assertTrue(seen and not any('index.html' in u for u in seen))
        self.assertEqual(self.live.served_path('hike/index.html'), 'hike/')
        self.assertEqual(self.live.served_path('index.html'), '')
        self.assertEqual(self.live.served_path('a/b.html'), 'a/b')
        self.assertEqual(self.live.served_path('catalog-products.js'), 'catalog-products.js')

    def test_adopt_matching_date_and_real_difference(self):
        # adopt searches from the site commit's real date to today, so the clock must not sit before the commit (the fixed
        # fixture day 7 broke this test once the wall clock passed it).
        self.now = datetime.now(timezone.utc)
        self.assertEqual(self.live.operate('adopt')['result'], 'adopted')
        (self.site / 'style.css').write_bytes(b'changed')
        git(self.site, 'add', '-A'); git(self.site, 'commit', '-q', '-m', 'changed')
        git(self.site, 'push', '-q', 'origin', 'main')
        self.assertEqual(self.live.operate('adopt')['result'], 'differs')

    def test_baseline_confirmation_and_stop_during_baseline_build(self):
        # Different bytes, but still privacy-safe; baseline explicitly confirms them.
        build = self.live.build
        self.live.build = lambda *a, **kw: {**build(*a, **kw), 'style.css': b'new safe css'}
        preview = self.live.operate('baseline')
        self.assertEqual(preview['result'], 'preview')
        self.assertEqual(self.push_calls, 0)
        shown = Path(preview['preview_dir'])  # the exact pages the baseline would publish, for G to look at
        self.assertEqual(preview['writer_head'], self.repo.head())
        self.assertEqual((shown / 'style.css').read_bytes(), b'new safe css')
        self.assertEqual((shown / 'index.html').read_bytes(), self.live.build(self.repo.head(), self.live.day(), 'x', 'p')['index.html'])
        self.assertEqual(self.live.operate('baseline', confirm='wrong')['result'], 'preview')
        def stop_build(*a, **kw):
            result = {**build(*a, **kw), 'style.css': b'new safe css'}
            if a[3] == 'before': Path(self.cfg['stopFile']).touch()
            return result
        self.live.build = stop_build
        self.live.operate('baseline', confirm=preview['manifest'])
        self.assertEqual(self.entry()['step'], 'stopped')
        self.assertEqual(self.push_calls, 0)

    def test_baseline_confirms_with_only_the_example_placeholder_but_not_a_real_address(self):
        build = self.live.build
        page = b'<input placeholder="you@example.com">'
        def with_pages(extra):
            return lambda *a, **kw: {**build(*a, **kw), 'style.css': b'new safe css', 'index.html': page, 'community.js': b"x='You@Mail.Example.COM'", **extra}
        self.live.build = with_pages({'hike/index.html': page + b' person@gmail.com'})
        preview = self.live.operate('baseline')
        self.assertEqual((preview['result'], preview['privacy']), ('preview', ['email']))
        self.assertEqual(self.live.operate('baseline', confirm=preview['manifest'])['result'], 'preview')
        self.assertEqual(self.push_calls, 0)
        self.live.build = with_pages({'hike/index.html': page})
        preview = self.live.operate('baseline')
        self.assertEqual((preview['result'], preview['privacy']), ('preview', []))
        self.assertEqual(self.live.operate('baseline', confirm='wrong')['result'], 'preview')
        self.assertEqual(self.push_calls, 0)
        self.assertEqual(self.live.operate('baseline', confirm=preview['manifest'])['result'], 'ok')

    def test_baseline_confirms_over_random_image_bytes_but_not_an_address_in_image_metadata(self):
        # HASS-BASELINE-FIX-2: the live site's store.jpg and photo-product-054.webp hold byte runs shaped like an address.
        page = b'<input placeholder="you@example.com">'
        site = {'index.html': page, 'assets/store.jpg': junk_jpg(), 'assets/products/photo-product-054.webp': junk_webp()}
        self.live.build = lambda *a, **kw: {**site, 'assets/store.jpg': junk_jpg(exif(b'person@gmail.com'))}
        preview = self.live.operate('baseline')
        self.assertEqual((preview['result'], preview['privacy']), ('preview', ['email']))
        self.assertEqual(self.live.operate('baseline', confirm=preview['manifest'])['result'], 'preview')
        self.live.build = lambda *a, **kw: dict(site)
        preview = self.live.operate('baseline')
        self.assertEqual((preview['result'], preview['privacy'], preview['paths']), ('preview', [], 3))
        self.assertEqual(self.live.operate('baseline', confirm='wrong')['result'], 'preview')
        self.assertEqual(self.push_calls, 0)
        self.assertEqual(self.live.operate('baseline', confirm=preview['manifest'])['result'], 'ok')
        self.assertEqual(self.push_calls, 1)

    def test_undo_uses_same_path_cap_exempt_and_both_ids(self):
        self.apply(); self.settle()
        orig = self.entry()['change_id']
        self.live.cfg['dailyCap'] = 1
        undo = editor.prepare(_req(('history.revert', {'changeId': orig})), state=self.repo.state, registry=self.live.registry)['draft']
        self.assertEqual(self.apply(undo)['result'], 'applied')
        self.assertEqual(self.entry()['kind'], 'undo')
        self.assertEqual(self.entry()['orig'], orig)
        self.assertIn('undo of ' + orig, git(self.bare, 'log', '-1', '--format=%s'))
        self.settle()
        self.assertEqual(self.entry()['state'], 'live')

    def test_stop_undo_in_private_then_unblock_and_retry_no_duplicate(self):
        build = self.live.build
        def stop_build(*args, **kw):
            result = build(*args, **kw)
            if kw.get('checks'): Path(self.cfg['stopFile']).touch()
            return result
        self.live.build = stop_build
        self.apply()
        cid = self.entry()['change_id']
        self.live.build = build
        undo = editor.prepare(_req(('history.revert', {'changeId': cid})), state=self.repo.state, registry=self.live.registry)['draft']
        editor.apply(undo['change_id'], undo['draft_hash'], state=self.repo.state, registry=self.live.registry)
        self.assertEqual(self.live.operate('unblock', cid)['state'], 'closed')
        self.assertEqual(self.push_calls, 0)

    def test_outcome_crash_repeats_at_most_once_never_loses(self):
        self.apply()
        write = self.live.books.write
        def crash(j, state=None, **fields):
            if 'notified' in fields: raise Crash()
            return write(j, state, **fields)
        with mock.patch.object(self.live.books, 'write', side_effect=crash), self.assertRaises(Crash): self.settle()
        self.restart()
        self.settle()
        self.assertEqual(len(self.messages), 2)
        self.assertEqual(self.messages[0], self.messages[1])

    def test_date_only_wrong_anchor_refused_and_new_day_build_passes(self):
        build = self.live.build
        def dated(commit, today, *a, **kw):
            files = build(commit, today, *a, **kw)
            return {**files, 'style.css': today.encode()}
        self.live.build = dated
        for rel, data in dated(self.repo.head(), self.live.day(), 'x', 'base').items():
            (self.site / rel).write_bytes(data)
        git(self.site, 'add', '-A'); git(self.site, 'commit', '-q', '-m', 'dated')
        git(self.site, 'push', '-q', 'origin', 'main')
        path = self.hostdir / 'publish.json'
        a = r.read(path); a['anchor_site_commit'] = git(self.site, 'rev-parse', 'HEAD')
        a['anchor_build_today'] = '2026-11-01'; r.atomic(path, a)
        self.assert_refused_unchanged(self.draft())
        a['anchor_build_today'] = self.live.day(); r.atomic(path, a)
        self.now += timedelta(days=1)
        self.assertEqual(self.apply()['result'], 'applied')
        self.settle()
        self.assertEqual(self.entry()['state'], 'live')

    def test_resolve_reverted_requires_exact_remote_and_local_before(self):
        def lose(cwd, args):
            if args[0] == 'push': raise subprocess.TimeoutExpired('git', 60)
        self.fault = lose
        self.apply()
        cid = self.entry()['change_id']
        with self.assertRaises(ValueError): self.live.operate('resolve', cid, resolution='reverted')
        git(self.site, 'reset', '--hard', self.site_before)
        self.assertEqual(self.live.operate('resolve', cid, resolution='reverted')['state'], 'reverted')
        self.assertEqual(self.live.load()[0]['last_site_commit'], self.site_before)

    def test_real_archive_build_checks(self):
        # Exercise the production builder and subprocess against a full isolated source archive.
        full = self.root / 'full'
        full.mkdir()
        source = Path(__file__).resolve().parents[2]
        for name in ('hass', 'storefront-mockup', 'reports/hermes-handoff'):
            shutil.copytree(source / name, full / name, ignore=shutil.ignore_patterns('__pycache__', 'node_modules'))
        git(full, 'init', '-q'); git(full, 'config', 'user.name', 'fixture'); git(full, 'config', 'user.email', 'fixture@example.invalid')
        git(full, 'add', '-A'); git(full, 'commit', '-q', '-m', 'fixture')
        self.live.wt = full
        files = p.LiveEditor.build(self.live, git(full, 'rev-parse', 'HEAD'), self.live.day(), 'real', 'new', checks=True)
        self.assertIn('index.html', files)
        self.assertIn('style.css', files)
        self.assertNotIn('community-server.py', files)


class PureTests(unittest.TestCase):
    def test_privacy_exact_values_per_path_and_owner_even_unchanged(self):
        before = {'index.html': b'first@gmail.com 555-111-2222'}
        rows = [({'index.html': b'first@gmail.com 555-111-2222'}, '', (), []),
                ({'index.html': b'other@gmail.com 555-111-2222'}, '', (), ['email']),
                ({'index.html': b'first@gmail.com 555-333-4444'}, '', (), ['phone']),
                ({**before, 'new.html': before['index.html']}, '', (), ['email', 'phone']),
                (before, 'ghp_' + 'a' * 25, (), ['github']),
                (before, '', ('first@gmail.com',), ['owner'])]
        for files, message, forbidden, expected in rows:
            with self.subTest(expected=expected): self.assertEqual(p.privacy(files, before, message, forbidden), expected)
        for value in ('-----BEGIN', 'AKIA' + 'A'*16, 'sk-' + 'a'*20, 'xoxb-abc', '/home/fixture/data', '127.0.0.1', 'x.sqlite3', 'iMessage;fixture'):
            self.assertTrue(p.privacy({'new': value.encode()}, {}, ''))

    def test_privacy_ignores_only_reserved_example_addresses(self):
        # HASS-BASELINE-FIX-1: the live form placeholder you@example.com cannot be personal; nothing else is relaxed.
        ignored = ['you@example.com', 'You@Mail.Example.COM', 'a@EXAMPLE.ORG', 'a@x.y.example.net', 'a@example.net',
                   'a@site.example', 'a@host.test', 'a@host.INVALID', 'a@host.localhost', '<input placeholder="you@example.com">']
        for value in ignored:
            for path in ('index.html', 'community.js', 'hike/index.html'):
                with self.subTest(value=value, path=path): self.assertEqual(p.privacy({path: value.encode()}, {}, ''), [])
        blocked = ['person@gmail.com', 'you@notexample.com', 'you@example.com.evil.org', 'you@example.comx', 'you@xexample.org',
                   'you@example.co', 'you@mytest.org', 'you@test.example.com.au', 'you@example-com.com', 'you@invalid.com']
        for value in blocked:
            with self.subTest(value=value): self.assertEqual(p.privacy({'index.html': value.encode()}, {}, ''), ['email'])
        mixed = b'you@example.com and person@gmail.com'
        self.assertEqual(p.privacy({'index.html': mixed}, {}, ''), ['email'])
        # Other kinds are untouched next to a placeholder.
        self.assertEqual(p.privacy({'index.html': b'you@example.com 555-111-2222'}, {}, ''), ['phone'])
        self.assertEqual(p.privacy({'a.js': b'you@example.com ghp_' + b'a' * 25}, {}, ''), ['github'])
        self.assertEqual(p.privacy({'a.js': b'you@example.com'}, {}, '', ('you@example.com',)), ['owner'])
        self.assertEqual(p.privacy({'a.js': b'ok'}, {}, 'msg you@example.com person@gmail.com'), ['email'])
        self.assertEqual(p.privacy({'a.js': b'ok'}, {}, 'msg you@example.com'), [])

    def test_email_screen_ignores_random_image_bytes_but_finds_real_addresses_anywhere(self):
        # HASS-BASELINE-FIX-2: the exact runs from the live store.jpg and photo-product-054.webp never count, in any file.
        for path, data in (('assets/store.jpg', junk_jpg()), ('assets/products/photo-product-054.webp', junk_webp()),
                           ('blob', junk_jpg()), ('index.html', b'x w@J.Wa y .@0y.Ty z'), ('a.js', b'"w@J.Wa",".@0y.Ty"')):
            with self.subTest(path=path):
                self.assertEqual(p.privacy({path: data}, {}, ''), [])
                self.assertEqual(p.pattern_hits('email', p.PATTERNS['email'], data.decode('latin1')), set())
        real = (b'person@gmail.com', b'PERSON@GMAIL.COM', b'first.last+tag@mail.Gmail.Com', b'abc@site.co.uk')
        for value in real:
            for path, data in (('index.html', b'<p>Email ' + value + b'.</p>'), ('a.js', b'x="...' + value + b'"'),
                               ('community.json', b'{"e": "' + value + b'"}'), ('notes.txt', value),
                               ('menu.pdf', b'%PDF-1.4\n(' + value + b') Tj'), ('assets/store.jpg', junk_jpg(exif(value))),
                               ('assets/products/photo-product-054.webp', junk_webp(exif(value))), ('blob', junk_jpg(exif(value)))):
                with self.subTest(value=value, path=path): self.assertEqual(p.privacy({path: data}, {}, ''), ['email'])
        # A binary file also needs a local part of 3+ characters and a listed top-level domain; text needs neither.
        for value in (b'ab@gmail.com', b'person@site.zz'):
            with self.subTest(value=value):
                self.assertEqual(p.privacy({'index.html': value}, {}, ''), ['email'])
                self.assertEqual(p.privacy({'assets/store.jpg': junk_jpg(exif(value))}, {}, ''), [])
        # Reserved example addresses stay ignored, in text and in images.
        for value in (b'you@example.com', b'person@mail.example.org', b'You@Mail.Example.COM'):
            for path, data in (('index.html', value), ('assets/store.jpg', junk_jpg(exif(value)))):
                with self.subTest(value=value, path=path): self.assertEqual(p.privacy({path: data}, {}, ''), [])
        # Other kinds still fire inside binary bytes.
        self.assertEqual(p.privacy({'assets/store.jpg': junk_jpg(b'\x00555-111-2222\x00')}, {}, ''), ['phone'])
        self.assertEqual(p.privacy({'assets/store.jpg': junk_jpg(b'Mike')}, {}, '', ('Mike',)), ['owner'])

    def test_fetch_rejects_redirect_http_and_foreign_host(self):
        for url in ('http://theavocadoman.com/x', 'https://elsewhere.invalid/x', 'https://theavocadoman.com:444/x'):
            with self.assertRaises(ValueError): p.fetch_live(url, p.URL)
        with self.assertRaises(ValueError): p.NoRedirect().redirect_request(None, None, None, None, None, None)
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'a' * (2*1024*1024 + 1)
        opener = mock.Mock(); opener.open.return_value = response
        with mock.patch.object(p.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaises(ValueError): p.fetch_live(p.URL + '/x', p.URL)

    def test_release_config_is_closed_and_bounded(self):
        cfg = dict(siteCheckout='/fixture/site', siteRemote=p.REMOTE, liveUrl=p.URL, stopFile='/fixture/STOP')
        self.assertEqual(p.release_config(cfg)['dailyCap'], 10)
        for over in ({'extra': True}, {'dailyCap': True}, {'dailyCap': 51}, {'minIntervalSeconds': 59},
                     {'verifyMinutes': 61}, {'siteRemote': 'other'}, {'liveUrl': 'http://theavocadoman.com'}, {'stopFile': 'relative'}):
            with self.subTest(over=over), self.assertRaises(ValueError): p.release_config({**cfg, **over})


def exif(value): return b'Exif\x00\x00MM\x00*\x00\x00\x00\x08Artist\x00' + value + b'\x00\x01\x02'


# Fake images around the exact byte runs found in the live site's images, with non-alphanumeric and digit neighbours.
def junk_jpg(extra=b''):
    return b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01' + extra + b'\x8fw@J.Wa\x03\xc1\x00w@J.Wa7\xffw@J.Wa'


def junk_webp(extra=b''):
    return b'RIFF\x02\x1b\x01\x00WEBPVP8 ' + extra + b'\xe2.@0y.Ty\x9a\x00.@0y.Ty3\x0c.@0y.Ty'


if __name__ == '__main__': unittest.main()
