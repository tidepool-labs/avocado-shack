#!/usr/bin/env python3
"""Rehearse duplicate recovery: python3 -B scripts/hass/demo_duplicate_recovery.py.

Fixed public bouquet fixture, temporary catalog, real editor and phone renderer.
The chat sender and identification are fixtures; no private inputs or live apply.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import sys
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hass import preview
from hass.npp import stages
from hass.tests import test_npp_stages, test_preview

CASES = ROOT / 'hass/tests/npp/cases'
ORIGINAL = 'Mixed flower bouquet'
REPLACEMENT = 'Garden stem bouquet'


def loopback_only(host):
    if host is not None and not ipaddress.ip_address(host).is_loopback:
        raise AssertionError('offline fixture attempted a non-loopback connection')


class Exercise(unittest.TestCase):
    report: dict[str, Any]

    def journey(self):
        fixture: Any = test_npp_stages.StageTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        chat = fixture.case
        self.enterContext(patch.object(stages.photo_polish, 'start', side_effect=fixture.deny))
        resolve, connect = socket.getaddrinfo, socket.socket.connect

        def checked_resolve(host, *args, **kwargs):
            loopback_only(host)
            return resolve(host, *args, **kwargs)

        def checked_connect(sock, address):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                loopback_only(address[0])
            return connect(sock, address)

        self.enterContext(patch.object(socket, 'getaddrinfo', side_effect=checked_resolve))
        self.enterContext(patch.object(socket.socket, 'connect', checked_connect))
        chat.settings.update(houseRender=True, photo_polish=False, liveSite=True)
        fixture.conv.settings.update(chat.settings)
        config = chat.repo.state / 'config.json'
        config.write_text(json.dumps({**json.loads(config.read_bytes()), 'settings': chat.settings}))
        photo = (CASES / 'photos/golden-006.jpg').read_bytes()
        chat.fetch = lambda _provider_id, count: [photo][:count]
        fixture.reading.update(item=ORIGINAL, kind='fresh', category_guess='flowers')
        fixture.reading['confidence']['brand'] = 0
        test_preview.BrowserCase.make_previewer(SimpleNamespace(repo=chat.repo, env=None))
        renderer = preview.Previewer(chat.repo.wt, viewports=('phone',))
        shots, editor_results = [], []
        real_candidate = fixture.conv.editor.candidate

        def capture(*args, **kwargs):
            shot = renderer.capture(*args, **kwargs)
            shots.append(shot)
            return shot

        def inspect(ops):
            value = real_candidate(ops)
            editor_results.append(value)
            return value

        fixture.conv.previewer = SimpleNamespace(capture=capture)
        self.enterContext(patch.object(fixture.conv.editor, 'candidate', side_effect=inspect))
        catalog = chat.repo.wt / 'hass/content/products.json'
        original = catalog.read_bytes()
        self.assertEqual(sum(row['name'] == ORIGINAL for row in json.loads(original)['products']), 1)
        chat.base = chat.repo.head()

        self.report['failed_step'] = 'duplicate_refused'
        chat.say(f'{ORIGINAL}, $10 each', photos=1, apply=False)
        chat.work()
        self.assertEqual(chat.transport.texts, [stages.missing.DUPLICATE])
        chat.say('yes', apply=False)  # acknowledges the question, not a listing approval
        chat.work()
        rejected, = editor_results
        self.assertEqual(rejected['result'], 'refused')
        self.assertIn('already has this name and brand', rejected['reason'])
        self.assertEqual(shots, [])
        fixture.no_draft()
        self.assertEqual(chat.yes(1, apply=False), 'no-target')
        self.assertEqual(catalog.read_bytes(), original)
        self.report['steps'].append(self.report['failed_step'])

        self.report['failed_step'] = 'replacement_delivered'
        job = chat.job()
        request = fixture.conv.npp.request(job, chat.now)
        chat.say(f'Call it {REPLACEMENT}', apply=False)
        chat.work()
        self.assertEqual(chat.job()['job_id'], job['job_id'])
        self.assertEqual(fixture.conv.npp.request(chat.job(), chat.now)['attachments'], request['attachments'])
        self.assertEqual([row['result'] for row in editor_results], ['refused', 'ok'])
        draft, = fixture.saved
        self.assertEqual(draft['ops'][-1]['args']['name'], REPLACEMENT)
        self.assertEqual(draft['ops'][-1]['args']['sellingPrice'], '10.00 each')
        shot, = shots
        self.assertTrue(shot['ok'] and shot['checks']['noPosts'])
        self.assertIn(REPLACEMENT, [row['text'] for row in shot['cardEvidence']['fragments']])
        row = chat.version(2)
        self.assertEqual(row['state'], 'queued')
        outbox, = chat.transport.cards
        self.assertEqual(outbox, row['outbox_id'])
        _, png, digest = chat.transport.cards[outbox]
        self.assertTrue(png.startswith(test_preview.PNG_SIGNATURE))
        self.assertEqual(shot['cardEvidence']['pngSha256'], digest)
        self.assertEqual(row['card_png_sha'], digest)
        self.assertEqual(hashlib.sha256(png).hexdigest(), digest)
        self.assertEqual(chat.yes(2, apply=False), 'no-target')
        chat.confirm(2)
        self.assertEqual(chat.version(2)['state'], 'delivered')
        self.report['steps'].append(self.report['failed_step'])

        self.report['failed_step'] = 'only_confirmed_version_reaches_off_gate'
        self.assertEqual(chat.yes(1, apply=False), 'no-target')
        self.assertEqual(chat.yes(2, apply=False), 'approval-held')
        chat.work()
        self.assertEqual(len(chat.transport.cards), 1)
        self.assertEqual(catalog.read_bytes(), original)
        self.assertEqual(fixture.conv.db.execute('SELECT count(*) FROM npp_approvals').fetchone()[0], 0)
        fixture.run_research.assert_not_called()
        chat.assert_unpublished()
        self.report['steps'].append(self.report['failed_step'])


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    start = time.monotonic()
    report = {'result': 'FAIL', 'mode': 'public OFF fixture only', 'steps': [], 'failed_step': 'browser'}
    if preview.Previewer(ROOT).env.get('PLAYWRIGHT_MODULE'):
        report['failed_step'] = 'fixture_setup'
        run = Exercise('journey')
        run.report = report
        result = unittest.TestResult()
        run.run(result)
        if result.wasSuccessful() and not result.skipped:
            report['result'] = 'PASS'
            report.pop('failed_step')
        elif len(report['steps']) == 3:
            report['failed_step'] = 'fixture_cleanup'
    report['seconds'] = round(time.monotonic() - start, 3)
    print(json.dumps(report, sort_keys=True))
    return int(report['result'] != 'PASS')


if __name__ == '__main__':
    sys.exit(main())
