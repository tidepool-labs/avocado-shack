"""DEMO-LOCK-1 offline acceptance: the release pause marker (slice 1a of the private-demo lock).

Real private writer, real release engine (LiveEditor) with the existing fake push/fetch edges. While the `demo-lock` marker
exists beside host.json no release step is admitted, so nothing pushes, fetches or reads the release site checkout.
"""
import os
import unittest
from unittest.mock import patch

from hass import host, publish_live, release_journal, sandbox, sandbox_editor, stock_site
from hass.tests import test_publish_live as pl
from hass.tests.test_editor import HOURS, NEW_HOURS

LIVE = {'approvals': 'live', 'live': ['site']}


def load_tests(loader, _tests, _pattern):
    """Only this module's own tests: the release fixture class carries its whole suite, which test_publish_live already runs."""
    return unittest.TestSuite(MarkerTests(n) for n in loader.getTestCaseNames(MarkerTests) if n in vars(MarkerTests))


class MarkerTests(pl.ReleaseCase):
    def setUp(self):
        super().setUp()
        self.site_calls, inner = [], self.live.git_runner
        self.live.git_runner = lambda cwd, *a: (os.path.realpath(cwd) == os.path.realpath(self.site) and self.site_calls.append(a), inner(cwd, *a))[1]
        self.mode = {**LIVE, 'hostDir': str(self.hostdir)}
        ids = {('site', 'sandbox'): str(self.repo.wt), ('site', 'live'): 'fixture-remote-main'}
        self.ed = sandbox_editor.SiteEditor(self.repo.state, sandbox.Gate(lambda: self.mode, lambda: ids),
                                            lambda: self.live, registry=self.live.registry, clock=lambda: self.now)
        self.marker = self.hostdir / release_journal.DEMO_MARKER

    def say_yes(self, d): return self.ed.apply(d['change_id'], d['draft_hash'])['result']

    def test_release_steps_find_the_interlock_closed_while_marked(self):
        """A caller that read host.json earlier (worker cycle, operator command) still reaches LiveEditor; every release step
        (apply, reconcile, every publish_live CLI command via operate) takes publish.lock and is refused while marked."""
        draft = self.ed.prepare([{'op': HOURS, 'args': {'hours': NEW_HOURS}}])['draft']
        self.assertEqual(draft['environment']['env'], 'live')
        self.marker.write_text('x')
        self.assertNotIn(self.say_yes(draft), ('applied', 'already-applied'))
        self.live.reconcile()
        self.assertEqual(self.live.operate('status'), {'result': 'busy'})
        self.assertRaises(ValueError, self.live.locked_baseline, self.live.load()[0], 'check')
        self.assertEqual((self.push_calls, self.site_calls), (0, []))
        with release_journal.publish_lock(self.hostdir) as held: self.assertTrue(held)  # only the switch may hold it
        self.marker.unlink()  # negative control: the same apply publishes once the interlock opens
        self.assertEqual((self.say_yes(draft), self.push_calls), ('applied', 1))
        with release_journal.publish_lock(self.hostdir) as held, release_journal.Books(self.hostdir).lock() as step:
            self.assertEqual((held, step), (True, False))  # the switch holding the interlock keeps release steps out

    def test_scheduled_stock_hook_never_builds_the_release_engine_while_marked(self):
        clover = {'environment': 'sandbox', 'merchantId': 'FAKEMERCHANT1', 'tokenFile': '/not-read', 'siteStock': 'draft'}
        cfg = {**self.mode, 'state': str(self.repo.state), 'release': self.cfg, 'clover': clover}

        def hook():
            with patch.object(host, 'load_host', return_value=cfg), patch.object(publish_live, 'LiveEditor') as live, \
                 patch.object(stock_site, 'StockSite') as queue:
                self.assertEqual(stock_site.main(['run', '--host', str(self.hostdir / 'host.json')]), 0)
            return live.call_count, queue.call_count
        self.marker.write_text('x')
        self.assertEqual(hook(), (0, 0))
        self.marker.unlink()
        self.assertEqual(hook(), (1, 1))  # negative control: unmarked, the same hook builds the engine and runs the queue
