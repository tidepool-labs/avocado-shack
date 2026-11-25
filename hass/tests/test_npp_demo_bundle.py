"""Synthetic tests for the one-run demo bundle producer; never reads the private recording or replay store."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hass.tests.npp import run_npp
from hass.tests.test_npp_demo_acceptance import synthetic_receipts
from scripts.hass import npp_card_gallery, npp_demo_acceptance, npp_demo_bundle as bundle

HEAD = 'a' * 40


def sha(data):
    return hashlib.sha256(data).hexdigest()


def transport(cards):
    """cards: {outbox row: (attachment bytes, receipt state or None)}."""
    return SimpleNamespace(cards={row: ('text', data, 'x') for row, (data, _) in cards.items()},
                           receipts={row: {'state': state} for row, (_, state) in cards.items() if state})


def synthetic_run(report, *, attachment=None, skip=()):
    """A stand-in for run_npp.main that drives the module globals the producer hooks, then prints the report."""
    def main(argv, environ=None):
        assert argv[:4] == ['--preview', '--json', '--strict', '--recorded']
        for case in run_npp.load_cases().values():
            for variant, view in run_npp.case_views(case):
                versions, cards = [], {}
                for version in view['expect'].get('versions', []):
                    row = view['id'] * 100 + version['n']
                    png = f'card {view["id"]} {variant} {version["n"]}'.encode()
                    delivered = version.get('delivered') is True and (view['id'], variant, version['n']) not in skip
                    versions.append({'n': version['n'], 'outbox_id': row, 'card_png_sha': sha(png),
                                     'delivered_at': '2026-11-25T00:00:00' if delivered else None})
                    if delivered:
                        cards[row] = ((attachment or {}).get((view['id'], version['n']), png), 'confirmed')
                run_npp.check_card(view, SimpleNamespace(transport=transport(cards)), {}, versions,
                                   None, [], None, None, None, None)
        print(json.dumps(report, sort_keys=True))
        return 0
    return main


class DeliveryNoteTests(unittest.TestCase):
    def test_only_confirmed_transport_bytes_become_delivery_rows(self):
        png = b'frozen card'
        rows = bundle.Deliveries()
        versions = [{'n': 1, 'outbox_id': 11, 'card_png_sha': sha(png), 'delivered_at': 't'},
                    {'n': 2, 'outbox_id': 12, 'card_png_sha': sha(b'v2'), 'delivered_at': 't'},
                    {'n': 3, 'outbox_id': 13, 'card_png_sha': sha(b'v3'), 'delivered_at': None},
                    {'n': 4, 'outbox_id': None, 'card_png_sha': sha(b'v4'), 'delivered_at': 't'},
                    {'n': 5, 'outbox_id': 15, 'card_png_sha': sha(b'v5'), 'delivered_at': 't'}]
        # v2 reached chat with other bytes; v3 never delivered; v4 never queued; v5 has no receipt.
        rows.note(7, 'b', transport({11: (png, 'confirmed'), 12: (b'stale', 'confirmed'), 13: (b'v3', 'confirmed'),
                                     15: (b'v5', None)}), versions)
        self.assertEqual(rows.rows, [
            {'id': 7, 'variant': 'b', 'n': 1, 'state': 'confirmed', 'png_sha256': sha(png), 'attachment_sha256': sha(png)},
            {'id': 7, 'variant': 'b', 'n': 2, 'state': 'confirmed', 'png_sha256': sha(b'v2'),
             'attachment_sha256': sha(b'stale')}])

    def test_hooks_bind_each_card_check_to_its_variant(self):
        rows, seen = bundle.Deliveries(), []
        views = rows.views(lambda case: iter([(None, {'id': 3}), ('b', {'id': 3})]))
        check = rows.check_card(lambda view, fx, state, versions, *a, **k: seen.append(view['id']) or ['finding'])
        png = b'p'
        fx = SimpleNamespace(transport=transport({1: (png, 'confirmed')}))
        version = [{'n': 1, 'outbox_id': 1, 'card_png_sha': sha(png), 'delivered_at': 't'}]
        for _variant, view in views({}):
            self.assertEqual(check(view, fx, {}, version, 'extra'), ['finding'])
        self.assertEqual(seen, [3, 3])
        self.assertEqual([(r['id'], r['variant']) for r in rows.rows], [(3, None), (3, 'b')])


class CheckoutTests(unittest.TestCase):
    def git(self, repo, *args):
        subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, timeout=30)

    def test_clean_head_or_refuse_mixed_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            self.git(repo, 'init', '-q')
            (repo / 'a.txt').write_text('a')
            self.git(repo, 'add', 'a.txt')
            self.git(repo, '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-q', '-m', 'a')
            head = bundle.checkout(repo)
            self.assertRegex(head, '^[0-9a-f]{40}$')
            for change in ('untracked', 'modified'):
                with self.subTest(change=change):
                    target = repo / ('b.txt' if change == 'untracked' else 'a.txt')
                    target.write_text('changed')
                    with self.assertRaisesRegex(bundle.Refused, 'checkout-dirty'):
                        bundle.checkout(repo)
                    self.git(repo, 'checkout', '-q', '--', '.')
                    self.git(repo, 'clean', '-qfd')
            self.assertEqual(bundle.checkout(repo), head)


class ReplayTests(unittest.TestCase):
    def run_replay(self, main):
        rows = bundle.Deliveries()
        with patch.object(run_npp, 'main', main), patch.object(run_npp, 'check_card', lambda *a, **k: []):
            return bundle.replay(Path('recording.json'), rows), rows

    def test_report_bytes_are_exactly_what_run_npp_printed(self):
        report, _ = synthetic_receipts()
        raw, rows = self.run_replay(synthetic_run(report))
        self.assertEqual(raw, (json.dumps(report, sort_keys=True) + '\n').encode())
        self.assertEqual(len(rows.rows), 78)
        # The hooks were scoped to the run.
        self.assertIs(run_npp.case_views.__module__, run_npp.__name__)

    def test_extra_output_error_or_no_report_is_refused(self):
        for printed in ('{"cases": []}\n{"cases": []}', 'not json', '{"error": "dependency missing"}', ''):
            with self.subTest(printed=printed):
                with self.assertRaises(bundle.Refused):
                    self.run_replay(lambda argv, environ=None, p=printed: print(p, end='\n' if p else ''))


class ReferenceTests(unittest.TestCase):
    def test_only_drawn_and_validated_files_count(self):
        def gallery(argv):
            out = Path(argv[argv.index('--out') + 1])
            out.mkdir()
            for case_id in ('01', '02', '03'):
                (out / f'card-{case_id}.png').write_bytes(f'png {case_id}'.encode())
            print('DRAWN 01 Validate: PASS')
            print('DRAWN 02 Validate: REFUSED: card-copy')
            print('DRAWN 04 Validate: PASS')  # printed, but no file was written
            print('FAIL 05 fixture-refused')
            return 1
        with tempfile.TemporaryDirectory() as folder, patch.object(npp_card_gallery, 'main', gallery):
            cards = bundle.references(Path(folder) / 'gallery')
        self.assertEqual(cards, [{'id': '01', 'png_sha256': sha(b'png 01')}])


class ProducerConsumerJoinTests(unittest.TestCase):
    def produce(self, report, *, heads=(HEAD, HEAD), cards=None, run=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        recording = Path(folder.name) / 'recording.json'
        recording.write_bytes(b'{"synthetic": true}')
        report['summary']['fingerprint']['recorded_sha256'] = sha(recording.read_bytes())
        cards = cards if cards is not None else [{'id': f'{i:02}', 'png_sha256': 'c' * 64} for i in range(1, 13)]
        with patch.object(run_npp, 'main', run or synthetic_run(report)), \
                patch.object(run_npp, 'check_card', lambda *a, **k: []), \
                patch.object(bundle, 'checkout', side_effect=list(heads)), \
                patch.object(bundle, 'references', return_value=cards):
            head, recorded, raw, evidence = bundle.produce(recording, Path(folder.name) / 'out')
        out = Path(folder.name) / 'out'
        self.assertEqual((out / 'replay.json').read_bytes(), raw)
        self.assertEqual((out / 'evidence.json').read_bytes(), evidence)
        self.assertEqual((out / 'evidence.json').stat().st_mode & 0o777, 0o600)
        return npp_demo_acceptance.check(raw, evidence, checkout=head, recording_sha256=recorded), raw, evidence

    def test_same_run_producer_output_passes_the_consumer(self):
        report, _ = synthetic_receipts()
        result, _, _ = self.produce(report)
        self.assertEqual(result, {'status': 'pass', 'reasons': [], 'cases': 38, 'variants': 49, 'required_variants': 49,
                                  'deliveries': 78, 'required_deliveries': 78, 'reference_cards': 12})

    def test_missing_or_wrong_chat_bytes_hold_delivery_coverage(self):
        report, _ = synthetic_receipts()
        for kind in ('missing', 'wrong-bytes'):
            with self.subTest(kind=kind):
                if kind == 'missing':
                    run = synthetic_run(report, skip={(1, None, 1)})
                else:
                    run = synthetic_run(report, attachment={(1, 1): b'another card'})
                result, _, _ = self.produce(report, run=run)
                self.assertEqual(result['reasons'], ['delivery-coverage'])
                self.assertEqual(result['deliveries'], 77)

    def test_gallery_cannot_stand_in_for_deliveries_or_vice_versa(self):
        report, _ = synthetic_receipts()
        result, _, _ = self.produce(report, cards=[{'id': '01', 'png_sha256': 'c' * 64}])
        self.assertEqual((result['reasons'], result['reference_cards'], result['deliveries']),
                         (['reference-coverage'], 1, 78))

    def test_mixed_run_or_stale_checkout_holds(self):
        report, _ = synthetic_receipts()
        _, raw, evidence = self.produce(report)
        other = json.loads(raw)
        other['cases'][0]['slug'] = 'another run'
        mixed = json.dumps(other, sort_keys=True).encode() + b'\n'
        recorded = report['summary']['fingerprint']['recorded_sha256']
        self.assertEqual(npp_demo_acceptance.check(mixed, evidence, checkout=HEAD, recording_sha256=recorded)['reasons'],
                         ['bundle-binding'])
        self.assertEqual(npp_demo_acceptance.check(raw, evidence, checkout='b' * 40, recording_sha256=recorded)['reasons'],
                         ['bundle-binding'])

    def test_head_moving_during_the_run_writes_nothing(self):
        report, _ = synthetic_receipts()
        with self.assertRaisesRegex(bundle.Refused, 'checkout-changed'):
            self.produce(report, heads=(HEAD, 'b' * 40))

    def test_recording_changing_during_replay_or_gallery_writes_nothing(self):
        # Contract: the bundle is bound to the recording digest taken at the start; a change at ANY point of
        # production (replay, or the later gallery render) is refused. Bug: checking only right after replay
        # let a recording edited during references() be accepted with the stale digest.
        report, _ = synthetic_receipts()
        for stage in ('replay', 'gallery'):
            with self.subTest(stage=stage):
                folder = tempfile.TemporaryDirectory()
                self.addCleanup(folder.cleanup)
                recording = Path(folder.name) / 'recording.json'
                recording.write_bytes(b'{"synthetic": true}')
                report['summary']['fingerprint']['recorded_sha256'] = sha(recording.read_bytes())
                run = synthetic_run(report)

                def changing_run(argv, environ=None):
                    code = run(argv, environ)
                    if stage == 'replay':
                        recording.write_bytes(b'{"synthetic": "edited"}')
                    return code

                def changing_references(gallery_dir, node=None):
                    if stage == 'gallery':
                        recording.write_bytes(b'{"synthetic": "edited"}')
                    return [{'id': f'{i:02}', 'png_sha256': 'c' * 64} for i in range(1, 13)]

                out = Path(folder.name) / 'out'
                with patch.object(run_npp, 'main', changing_run), \
                        patch.object(run_npp, 'check_card', lambda *a, **k: []), \
                        patch.object(bundle, 'checkout', return_value=HEAD), \
                        patch.object(bundle, 'references', changing_references):
                    with self.assertRaisesRegex(bundle.Refused, 'recording-changed'):
                        bundle.produce(recording, out)
                self.assertFalse((out / 'replay.json').exists())
                self.assertFalse((out / 'evidence.json').exists())

    def test_output_inside_git_is_refused_before_running(self):
        with patch.object(run_npp, 'main', side_effect=AssertionError('ran')):
            with self.assertRaisesRegex(ValueError, 'inside a git worktree'):
                bundle.produce(Path(__file__), bundle.ROOT / 'not-here')

    def test_cli_prints_counts_only_hold_on_refusal(self):
        with tempfile.TemporaryDirectory(prefix='private-test-marker-') as folder:
            recording = Path(folder) / 'recording.json'
            recording.write_text('{}')
            with patch.object(bundle, 'produce', side_effect=bundle.Refused('checkout-dirty')), \
                    patch('sys.stdout') as stdout:
                code = bundle.main(['--recorded', str(recording), '--out', str(Path(folder) / 'out')])
        self.assertEqual(code, 1)
        printed = ''.join(call.args[0] for call in stdout.write.call_args_list)
        self.assertEqual(json.loads(printed), {'status': 'hold', 'reasons': ['checkout-dirty']})
        self.assertNotIn('private-test-marker', printed)


if __name__ == '__main__':
    unittest.main()
