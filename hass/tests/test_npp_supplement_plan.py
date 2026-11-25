"""H44: exercise the counts-only CLI on metadata, never on a recording."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/hass/npp_supplement_plan.py'


def key(kind, *, pin='a', digest='b', ordinal=0):
    return f'{kind}:{pin * 64}:{digest * 64}:{ordinal}'


def op(kind, max_calls: int | None = 1, **identity):
    return {'key': key(kind, **identity), 'max_calls': max_calls}


def covered(*operations):
    return {'complete': True, 'operations': list(operations)}


class SupplementPlanCLI(unittest.TestCase):
    def run_plan(self, cases, base=(), *, scope=('14', '16'), raw=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic-metadata.json'
            data = {'base_keys': list(base), 'cases': cases}
            path.write_text(json.dumps(data) if raw is None else raw, encoding='utf-8')
            before = path.read_bytes()
            args = [arg for case in scope for arg in ('--case', case)]
            result = subprocess.run([sys.executable, '-B', str(SCRIPT), str(path), *args],
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.stderr, '')
            self.assertEqual(path.read_bytes(), before)
            return result.returncode, json.loads(result.stdout)

    def test_shared_missing_key_charges_once_and_base_hits_charge_zero(self):
        # Per-case billing would double-charge the shared copy key; per-kind hit checks would miss image v2.
        shared = op('copy', 3)
        cases = {'14': covered(shared, op('image', 2), op('s2')),
                 '16': covered(shared, op('image', 2, ordinal=1))}
        code, result = self.run_plan(cases, [key('image'), key('s2')])
        self.assertEqual(code, 0)
        self.assertEqual(result, {'status': 'WITHIN_CAPS', 'cases': 2, 'exact_base_hits': 2,
                                  'distinct_missing': {'copy': 1, 'image': 1, 's2': 0},
                                  'maximum_calls': {'codex': 3, 'images': 2}})

    def test_model_and_input_digests_are_part_of_identity(self):
        # A join on kind/ordinal, or on only one digest, underestimates the budget.
        cases = {'14': covered(op('copy', pin='d'), op('copy', digest='e')), '16': covered()}
        code, result = self.run_plan(cases, [key('copy')])
        self.assertEqual(code, 0)
        self.assertEqual(result['exact_base_hits'], 0)
        self.assertEqual(result['maximum_calls']['codex'], 2)

    def test_either_cap_holds_on_maximum_not_on_number_of_keys(self):
        # Each budget is independent, exact limits pass, and two one-key estimates can still exceed a cap.
        for (copy, image), outcome in [((40, 4), (0, 'WITHIN_CAPS')),
                                       ((41, 4), (2, 'HOLD')), ((40, 5), (2, 'HOLD'))]:
            with self.subTest(copy=copy, image=image):
                code, result = self.run_plan({'14': covered(op('copy', copy), op('image', image)),
                                              '16': covered()})
                self.assertEqual((code, result['status']), outcome)
                self.assertEqual(result['maximum_calls'], {'codex': copy, 'images': image})

    def test_missing_identification_holds_even_below_codex_cap(self):
        # The proposed budget is for ID-only selector calls, not new photo identification.
        code, result = self.run_plan({'14': covered(op('s2')), '16': covered()})
        self.assertEqual((code, result['status'], result['reason']), (2, 'HOLD', 'missing_identification'))
        self.assertEqual(result['distinct_missing']['s2'], 1)

    def test_absent_unfinished_or_unbounded_scope_cannot_look_free(self):
        # An unobserved reachable branch is not an explicit complete case with zero operations.
        for name, cases in {
            'absent': {'14': covered()},
            'extra': {'14': covered(), '16': covered(), '17': covered()},
            'unobserved': {'14': covered(), '16': {'complete': False, 'operations': []}},
            'not_boolean': {'14': covered(), '16': {'complete': 1, 'operations': []}},
            'unknown_maximum': {'14': covered(op('copy', None)), '16': covered()},
            'zero_maximum': {'14': covered(op('copy', 0)), '16': covered()},
            'boolean_maximum': {'14': covered(op('copy', True)), '16': covered()},
        }.items():
            with self.subTest(name=name):
                code, result = self.run_plan(cases)
                self.assertEqual(code, 2)
                self.assertEqual(result['status'], 'HOLD')
                self.assertNotIn('maximum_calls', result)

    def test_conflicting_bounds_for_shared_key_are_not_resolved_by_row_order(self):
        code, result = self.run_plan({'14': covered(op('image', 2)), '16': covered(op('image', 3))})
        self.assertEqual((code, result), (2, {'status': 'HOLD', 'reason': 'conflicting_bounds'}))

    def test_invalid_scope_flags_do_not_echo_input(self):
        # argparse must not reflect a pasted label or path in its error message.
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--private-example'],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.stderr, '')
        self.assertEqual((result.returncode, json.loads(result.stdout)),
                         (2, {'status': 'HOLD', 'reason': 'invalid_arguments'}))

    def test_malformed_input_returns_only_fixed_status_and_does_not_echo_data(self):
        # JSON last-wins parsing or reflected diagnostics could hide incomplete scope or leak metadata.
        for raw in ('{"base_keys": [], "base_keys": [], "cases": {}}',
                    '{"malformed_do_not_echo":',
                    json.dumps({'base_keys': [], 'cases': {'14': covered(op('not-a-provider')), '16': covered()}}),
                    json.dumps({'base_keys': [key('copy')] * 2, 'cases': {'14': covered(), '16': covered()}})):
            with self.subTest(raw=raw[:28]):
                self.assertEqual(self.run_plan({}, raw=raw), (2, {'status': 'HOLD', 'reason': 'invalid_metadata'}))
