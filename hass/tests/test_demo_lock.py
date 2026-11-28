"""DEMO-LOCK-1 offline acceptance: the private-demo lock on the one production instance.

Real private writer, real release engine (LiveEditor) with the existing fake push/fetch edges, real host.json switch.
While the lock is on nothing may push, fetch or reset the release site checkout, and only the lock's own private drafts can be undone.
"""
import json
import os
import unittest
from unittest.mock import patch

from hass import host, release_journal, sandbox, sandbox_editor
from hass.tests import test_publish_live as pl
from hass.tests.test_editor import HOURS, NEW_HOURS, git
from hass.tests.test_host import HostCase

LIVE = {'approvals': 'live', 'live': ['site']}


def locked(mode, lock_id='demo-1128'):
    mode['demoLock'] = {'id': lock_id, 'tree': '0' * 40}
    mode['mode_gen'] = mode.get('mode_gen', 0) + 1


def unlocked(mode):
    mode.pop('demoLock', None)
    mode['mode_gen'] = mode.get('mode_gen', 0) + 1


def load_tests(loader, _tests, _pattern):
    """Only this module's own tests: the release fixture class carries its whole suite, which test_publish_live already runs."""
    return unittest.TestSuite(cls(name) for cls in (LockedEditorTests, DemoLockSwitchTests)
                              for name in loader.getTestCaseNames(cls) if name in vars(cls))


class LockedEditorTests(pl.ReleaseCase):
    def setUp(self):
        super().setUp()
        self.site_calls = []
        inner = self.live.git_runner

        def recording(cwd, *args):
            if os.path.realpath(cwd) == os.path.realpath(self.site): self.site_calls.append(args)
            return inner(cwd, *args)
        self.live.git_runner = recording
        self.mode = {**LIVE, 'hostDir': str(self.hostdir)}
        ids = {('site', 'sandbox'): str(self.repo.wt), ('site', 'live'): 'fixture-remote-main'}
        self.ed = sandbox_editor.SiteEditor(self.repo.state, sandbox.Gate(lambda: self.mode, lambda: ids),
                                            lambda: self.live, registry=self.live.registry, clock=lambda: self.now)

    def hours(self, hours=NEW_HOURS):
        return self.ed.prepare([{'op': HOURS, 'args': {'hours': hours}}])['draft']

    def undo(self, cid):
        return self.ed.prepare([{'op': 'history.revert', 'args': {'changeId': cid}}])

    def tree(self):
        return git(self.repo.wt, 'rev-parse', 'HEAD^{tree}')

    def test_new_draft_goes_private_and_its_undo_restores_the_tree_with_no_site_call(self):
        before = self.tree()
        locked(self.mode)
        draft = self.hours()
        self.assertEqual((draft['environment']['env'], draft['environment']['lock']), ('sandbox', 'demo-1128'))
        self.assertEqual(self.ed.apply(draft['change_id'], draft['draft_hash'])['result'], 'applied')
        self.assertNotEqual(self.tree(), before)
        self.ed.reconcile()
        undo = self.undo(draft['change_id'])
        self.assertEqual(undo['result'], 'ok', undo)
        self.assertEqual(self.ed.apply(undo['draft']['change_id'], undo['draft']['draft_hash'])['result'], 'applied')
        self.assertEqual(self.tree(), before)
        self.assertEqual((self.push_calls, self.site_calls), (0, []))
        self.assertEqual(git(self.site, 'rev-parse', 'HEAD'), self.site_before)
        self.assertFalse((self.hostdir / 'releases').exists() and self.live.books.journals())

    def test_undo_of_a_change_made_before_the_lock_is_refused(self):
        live = self.hours()
        self.assertEqual(self.ed.apply(live['change_id'], live['draft_hash'])['result'], 'applied')
        self.assertEqual(self.push_calls, 1)
        unlocked(self.mode)
        self.mode['approvals'], self.mode['live'] = 'private', []
        private = self.hours(["Monday–Saturday 8am–5pm", "Closed Sunday"])
        self.assertEqual(self.ed.apply(private['change_id'], private['draft_hash'])['result'], 'applied')
        self.mode.update(LIVE)
        locked(self.mode)
        calls = len(self.site_calls)
        for cid in (live['change_id'], private['change_id']):
            with self.subTest(env=self.ed._draft(cid)['environment']['env']):
                self.assertNotEqual(self.undo(cid)['result'], 'ok')
        self.assertEqual((self.push_calls, len(self.site_calls)), (1, calls))

    def test_waiting_live_draft_said_yes_to_under_the_lock_is_not_published(self):
        draft = self.hours()
        self.assertEqual(draft['environment']['env'], 'live')
        locked(self.mode)
        self.assertEqual(self.ed.apply(draft['change_id'], draft['draft_hash'])['result'], 'env-changed')
        self.assertEqual((self.push_calls, self.site_calls), (0, []))

    def test_lock_draft_cannot_go_live_after_the_lock_is_off(self):
        locked(self.mode)
        draft = self.hours()
        unlocked(self.mode)
        self.assertEqual(self.ed.apply(draft['change_id'], draft['draft_hash'])['result'], 'env-changed')
        self.assertEqual(self.push_calls, 0)

    def test_reconcile_is_skipped_under_the_lock_and_resumes_after(self):
        draft = self.hours()
        self.live.fetch = lambda url, base: b'stale'  # the live check fails, so the release stays open
        self.assertEqual(self.ed.apply(draft['change_id'], draft['draft_hash'])['result'], 'applied')
        entry = self.live.books.journals()[-1]
        self.assertNotIn(entry['state'], release_journal.CLOSED)
        locked(self.mode)
        calls, self.now = len(self.site_calls), self.now + pl.timedelta(hours=1)
        self.ed.reconcile()
        self.assertEqual((len(self.site_calls), self.live.books.journals()[-1]), (calls, entry))
        with self.assertRaises(sandbox.ModeError):
            self.ed.live()
        unlocked(self.mode)
        self.ed.reconcile()
        self.assertNotEqual(self.live.books.journals()[-1], entry)  # negative control: the same reconcile acts when unlocked

    def test_owner_settings_drop_the_live_site_while_locked(self):
        settings = {'liveSite': 'theavocadoman.com'}
        locked(self.mode)
        self.ed.sync_settings(settings)
        self.assertNotIn('liveSite', settings)
        unlocked(self.mode)
        self.ed.sync_settings(settings)
        self.assertEqual(settings['liveSite'], 'theavocadoman.com')

    def test_operator_release_commands_are_refused_while_locked(self):
        from hass import publish_live
        cfg = {**self.mode, 'state': str(self.repo.state), 'release': self.cfg}
        locked(cfg)
        with patch.object(host, 'load_host', return_value=cfg), patch.object(publish_live, 'LiveEditor') as live, \
             patch('builtins.print') as out:
            self.assertEqual(publish_live.main(['revert-last', '--host', str(self.hostdir / 'host.json')]), 1)
        live.assert_not_called()
        self.assertEqual(json.loads(out.call_args[0][0]), {'result': 'refused'})


class DemoLockSwitchTests(HostCase):
    def setUp(self):
        super().setUp()
        self.path = self.host_json(approvals='private')

    def raw(self):
        return json.loads(self.path.read_text())

    def switch(self, on, lock_id='demo-1128'):
        try: return host.set_demo_lock(self.path, on, lock_id)
        except host.Refuse as exc: return exc.out

    def apply_hours(self, cid=None):
        worker = host.make_worker(host.load_host(self.path), self.store, build=lambda: self.interp, clock=self.clock)
        ops = [{'op': 'history.revert', 'args': {'changeId': cid}}] if cid else [{'op': 'store.set_hours', 'args': {'hours': NEW_HOURS}}]
        d = worker.conv.editor.prepare(ops)['draft']
        self.assertEqual(worker.conv.editor.apply(d['change_id'], d['draft_hash'])['result'], 'applied')
        return d

    def test_on_records_the_writer_tree_and_off_waits_until_it_is_back(self):
        tree, gen = git(self.repo.wt, 'rev-parse', 'HEAD^{tree}'), self.raw().get('mode_gen', 0)
        self.assertEqual(self.switch(True)['result'], 'ok')
        self.assertEqual((self.raw()['demoLock'], self.raw()['mode_gen']), ({'id': 'demo-1128', 'tree': tree}, gen + 1))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.switch(True), {'result': 'refused', 'reason': 'already-on'})
        demo = self.apply_hours()
        self.assertEqual(demo['environment']['lock'], 'demo-1128')
        self.assertEqual(self.switch(False), {'result': 'refused', 'reason': 'demo-change-present'})
        self.apply_hours(demo['change_id'])
        self.assertEqual(self.switch(False)['result'], 'ok')
        self.assertNotIn('demoLock', self.raw())
        self.assertEqual(self.switch(False), {'result': 'refused', 'reason': 'already-off'})

    def test_on_refuses_unsettled_work_and_clover_writes_changing_nothing(self):
        original = self.path.read_bytes()
        journal = self.repo.state / 'journal'
        journal.mkdir(exist_ok=True)
        (journal / 'chg-20261128-000000-aaaaaa.json').write_text('{}')
        self.assertEqual(self.switch(True)['reason'], 'private-change-unsettled')
        (journal / 'chg-20261128-000000-aaaaaa.json').unlink()
        (self.hostdir / 'releases').mkdir(mode=0o700)
        with patch.object(release_journal.Books, 'journals', return_value=[{'state': 'pushing'}]):
            self.assertEqual(self.switch(True)['reason'], 'release-unsettled')
        with patch.object(release_journal.Books, 'journals', side_effect=release_journal.BooksError('release-books')):
            self.assertEqual(self.switch(True)['reason'], 'release-books')
        real = host.load_host
        with patch.object(host, 'load_host', side_effect=lambda p, *a, **k: {**real(p, *a, **k), 'clover': {'writeMode': 'live'}}):
            self.assertEqual(self.switch(True)['reason'], 'clover-writes')
        self.assertEqual(self.switch(True, 'Bad ID')['reason'], 'lock-id')
        (self.repo.wt / 'stray.txt').write_text('x')
        self.assertEqual(self.switch(True)['reason'], 'writer-tree')
        self.assertEqual(self.path.read_bytes(), original)

    def test_cli_and_config_validation(self):
        with patch('builtins.print') as out:
            self.assertEqual(host.main(['demo-lock', 'on', '--id', 'demo-1128', '--host', str(self.path)]), 0)
            self.assertEqual(json.loads(out.call_args[0][0])['demoLock'], 'on')
            self.assertEqual(host.main(['demo-lock', 'on', '--id', 'demo-1128', '--host', str(self.path)]), 2)
        self.assertEqual(host.load_host(self.path)['demoLock']['id'], 'demo-1128')
        for bad in ('demo', {'id': 'demo'}, {'id': 'Demo', 'tree': '0' * 40}, {'id': 'demo', 'tree': 'x' * 40}):
            with self.subTest(bad=bad), self.assertRaises(host.HostConfigError):
                self.write(self.path, json.dumps({**self.raw(), 'demoLock': bad}).encode())
                host.load_host(self.path)
        self.assertIsNone(sandbox.policy(LIVE)['lock'])  # absent demoLock = off
