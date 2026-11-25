"""End-to-end CLI tests using synthetic receipts, never the private replay store."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hass.tests.npp import run_npp
from scripts.hass import npp_demo_acceptance

ROOT = Path(__file__).resolve().parents[2]
CHECKOUT, RECORDING, PNG = 'a' * 40, 'b' * 64, 'c' * 64


def synthetic_receipts():
    rows, deliveries = [], []
    for case in run_npp.load_cases().values():
        for variant, view in run_npp.case_views(case):
            identity = {'id': case['id'], 'variant': variant}
            layers = {'conversation' if view['path'] == 'question' else 'card': 'pass'}
            if view.get('inputs', {}).get('web') is not None:
                layers['research'] = 'pass'
                seed = run_npp.owner_seed(view)
                if seed['maker'] and (seed['town'] or seed['url']) and view['expect'].get('research'):
                    layers['seed'] = 'pass'
            rows.append(dict(identity, path=view['path'], terminal=view['terminal'], result='pass', layers=layers))
            for version in view['expect'].get('versions', []):
                if version.get('delivered') is True:
                    deliveries.append(dict(identity, n=version['n'], state='confirmed',
                                           png_sha256=PNG, attachment_sha256=PNG))
    report = {'cases': rows, 'summary': {'preview': True, 'runs': 49, 'pass': 49, 'fail': 0, 'not-run': 0,
                                        'fingerprint': {'recorded_sha256': RECORDING}}}
    evidence = {'checkout': CHECKOUT, 'deliveries': deliveries,
                'reference_cards': [{'id': f'{i:02}', 'png_sha256': PNG} for i in range(1, 13)]}
    return report, evidence


class DemoAcceptanceTests(unittest.TestCase):
    def invoke(self, report, evidence, *, bind=True):
        return self.invoke_bytes(json.dumps(report).encode(), evidence, bind=bind)

    def invoke_bytes(self, report, evidence, *, bind=True):
        evidence = copy.copy(evidence)
        if bind:
            evidence['replay_sha256'] = hashlib.sha256(report).hexdigest()
        with tempfile.TemporaryDirectory(prefix='private-test-marker-') as folder:
            replay = Path(folder) / 'replay.json'
            receipt = Path(folder) / 'evidence.json'
            replay.write_bytes(report)
            receipt.write_text(json.dumps(evidence), encoding='utf-8')
            proc = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/hass/npp_demo_acceptance.py'),
                                   str(replay), str(receipt), '--checkout', CHECKOUT, '--recording-sha256', RECORDING],
                                  cwd=folder, check=False, capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.stderr, '')
        self.assertNotIn('private-test-marker', proc.stdout)
        return proc.returncode, json.loads(proc.stdout)

    def assert_hold(self, report, evidence, reason, **kwargs):
        code, output = self.invoke(report, evidence, **kwargs)
        self.assertEqual(code, 1)
        self.assertEqual(output['status'], 'hold')
        self.assertEqual(output['reasons'], [reason])
        return output

    def test_complete_report_and_bundle_pass(self):
        # The CLI accepts question-only variants and intentionally unsent versions, not merely all-listing runs.
        report, evidence = synthetic_receipts()
        self.assertEqual(self.invoke(report, evidence), (0, {
            'status': 'pass', 'reasons': [], 'cases': 38, 'variants': 49, 'required_variants': 49,
            'deliveries': 78, 'required_deliveries': 78, 'reference_cards': 12,
        }))

    def test_missing_variant_holds_even_when_summary_claims_everything_passed(self):
        # All 38 case IDs are still present: a case count alone misses exactly this omission.
        report, evidence = synthetic_receipts()
        report['cases'].pop(next(i for i, row in enumerate(report['cases']) if row['variant'] is not None))
        output = self.assert_hold(report, evidence, 'variant-coverage')
        self.assertEqual((output['cases'], output['variants']), (38, 48))

    def test_failed_or_missing_layer_and_duplicate_variant_hold(self):
        # A stale summary or row result must not hide a layer failure or an extra copy of a passing row.
        for mutation in ('not-run', 'missing-layer', 'duplicate'):
            with self.subTest(mutation=mutation):
                report, evidence = synthetic_receipts()
                row = report['cases'][0]
                if mutation == 'not-run':
                    row['layers'][next(iter(row['layers']))] = 'not-run'
                elif mutation == 'missing-layer':
                    row['layers'].pop(next(iter(row['layers'])))
                else:
                    report['cases'].append(copy.deepcopy(row))
                self.assert_hold(report, evidence, 'variant-coverage')

    def test_no_missing_or_unconfirmed_or_stale_delivery(self):
        # A green replay can still have an incomplete chat capture. Digest equality must be checked per version.
        for mutation in ('omit', 'queued', 'stale', 'superseded'):
            with self.subTest(mutation=mutation):
                report, evidence = synthetic_receipts()
                rows = evidence['deliveries']
                if mutation == 'omit':
                    rows.pop()
                elif mutation == 'queued':
                    rows[0]['state'] = 'queued'
                elif mutation == 'stale':
                    rows[0]['attachment_sha256'] = 'd' * 64
                else:
                    rows.append(dict(next(row for row in rows if row['id'] == 25 and row['n'] == 1), n=2))
                self.assert_hold(report, evidence, 'delivery-coverage')

    def test_reference_id_cannot_be_replaced_by_duplicate(self):
        # Twelve rows do not prove that twelve distinct expected cards were rendered.
        report, evidence = synthetic_receipts()
        evidence['reference_cards'][-1]['id'] = '01'
        self.assertEqual(self.assert_hold(report, evidence, 'reference-coverage')['reference_cards'], 11)

    def test_fixed_delivery_total_cannot_shrink_with_corpus(self):
        # An accidental fixture edit must not lower the release target even if the report
        # and bundle agree with the newly shortened expectation and all 12 references exist.
        report, evidence = synthetic_receipts()
        dropped = evidence['deliveries'].pop(0)
        cases = run_npp.load_cases()
        self.assertIsNone(dropped['variant'])
        version = next(row for row in cases[dropped['id']]['expect']['versions'] if row['n'] == dropped['n'])
        version['delivered'] = False
        replay = json.dumps(report).encode()
        evidence['replay_sha256'] = hashlib.sha256(replay).hexdigest()
        with patch.object(run_npp, 'load_cases', return_value=cases):
            with self.assertRaisesRegex(ValueError, 'unexpected versioned corpus'):
                npp_demo_acceptance.check(replay, json.dumps(evidence).encode(),
                                         checkout=CHECKOUT, recording_sha256=RECORDING)

    def test_fixture_only_or_other_run_evidence_holds(self):
        # Prevent a fixture-only green result, an old bundle, or a different recording/checkout being reused.
        for mutation in ('fake-preview', 'wrong-recording', 'old-report', 'old-checkout'):
            with self.subTest(mutation=mutation):
                report, evidence = synthetic_receipts()
                reason = 'recorded-renderer-replay-required'
                if mutation == 'fake-preview':
                    report['summary']['preview'] = False
                elif mutation == 'wrong-recording':
                    report['summary']['fingerprint']['recorded_sha256'] = PNG
                else:
                    reason = 'bundle-binding'
                    if mutation == 'old-checkout':
                        evidence['checkout'] = 'd' * 40
                    else:
                        evidence['replay_sha256'] = PNG
                self.assert_hold(report, evidence, reason, bind=mutation != 'old-report')

    def test_malformed_report_holds_without_echoing_input(self):
        # Malformed or ambiguous evidence never becomes acceptance evidence or leaks the data in a traceback.
        for report in (b'{"private-test-marker":', b'{"cases":[],"cases":[]}'):
            with self.subTest(report=report):
                code, output = self.invoke_bytes(report, {})
                self.assertEqual(code, 1)
                self.assertEqual(output, {'status': 'hold', 'reasons': ['unreadable-receipt-or-corpus']})


if __name__ == '__main__':
    unittest.main()
