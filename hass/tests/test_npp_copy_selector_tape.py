"""NPP acceptance runner: the production copy selector is taped like every other model call.

Before this, record and replay both left the Writer without a selector unless a case stubbed one, so every strict
replay card used the local default wording ("basic wording", item-only name) whatever the recording held. Contracts:
record mode calls the real adapter through the capped recorder and saves the choice; replay serves the recorded
choice to the Writer; a recording made without selector tapes keeps the old local defaults (so an existing recording
scores exactly as before); a recording that tapes the selector but not this input is unobserved, never a guess.
Fixtures only: no model, network, live Hass or private recording.
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hass import npp
from hass.npp import copy as npp_copy

ROOT = Path(__file__).resolve().parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_npp = _load("npp_run_selector_tape_under_test", ROOT / "hass" / "tests" / "npp" / "run_npp.py")
KEY = 'd' * 64
CHOICE = {'name': {'template_id': 'name-item'}}


def honey():
    case = run_npp.load_cases()[24]
    return next(view for name, view in run_npp.case_views(case) if name is None)


def copy_pin():
    return npp.assets()[0]['assets']['hass-listing-copy/SKILL.md']


def tape(path, entries):
    path.write_text(json.dumps({'copy': {'kind': 'copy', 'source': 'synthetic test tape', 'entries': entries}}))
    return path


class SpyWriter:
    """Calls the real Writer and keeps what the selector it was handed returned (None when it got none)."""

    def __init__(self):
        self.given = []
        self.original = npp_copy.Writer.write

    def __call__(self, writer, ctx, select=None, **kwargs):
        if select is None:
            self.given.append('no selector')
            return self.original(writer, ctx, None, **kwargs)

        def seen(*args):
            try:
                out = select(*args)
            except Exception as error:
                self.given.append(type(error).__name__)
                raise
            self.given.append(out)
            return out
        return self.original(writer, ctx, seen, **kwargs)


class SelectorTapeTests(unittest.TestCase):
    def run_honey(self, tapes):
        spy = SpyWriter()
        with patch.object(npp_copy.Writer, 'write', autospec=True, side_effect=spy), \
                patch.object(run_npp, 'selector_digest', return_value=KEY):
            failures, evidence = run_npp.run_conversation(honey(), tapes)
        return spy.given, failures, evidence

    def test_a_recording_without_selector_tapes_keeps_the_local_default_wording(self):
        # The saved private recording has no 'copy' kind: replay must score exactly as before.
        given, failures, evidence = self.run_honey(run_npp.Tapes())
        self.assertTrue(given)
        self.assertEqual(set(given), {'no selector'})
        self.assertEqual(evidence['calls'].get('copy', 0), 0)
        self.assertEqual(failures, [])

    def test_a_taped_selection_reaches_the_writer_once_per_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            entries = {f'{copy_pin()}:{KEY}:{n}': {'output': CHOICE} for n in range(4)}
            tapes = run_npp.Tapes(recorded=tape(Path(tmp) / 'copy.json', entries))
            given, failures, evidence = self.run_honey(tapes)
        self.assertTrue(given)
        self.assertEqual(given, [CHOICE] * len(given))
        self.assertEqual(evidence['calls']['copy'], len(given))
        self.assertEqual(failures, [])

    def test_a_recorded_none_replays_as_none_not_as_a_new_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            entries = {f'{copy_pin()}:{KEY}:{n}': {'output': None} for n in range(4)}
            tapes = run_npp.Tapes(recorded=tape(Path(tmp) / 'copy.json', entries))
            given, failures, _ = self.run_honey(tapes)
        self.assertEqual(set(given), {None})
        self.assertEqual(failures, [])

    def test_a_selector_input_the_recording_does_not_hold_is_unobserved_never_a_guess(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = {f'{copy_pin()}:{"e" * 64}:0': {'output': CHOICE}}
            tapes = run_npp.Tapes(recorded=tape(Path(tmp) / 'copy.json', other))
            given, _, evidence = self.run_honey(tapes)
        self.assertIn('TapeUnavailable', given)
        self.assertNotIn(CHOICE, given)
        self.assertTrue(any('tape miss copy' in note for note in evidence['missing']), evidence['missing'])

    def test_the_tape_key_is_the_whole_selector_input(self):
        step, prompt, schema, options = {'model': 'm'}, 'p', {'type': 'object'}, {'templates': {'name': ['name-item']}}
        base = run_npp.selector_digest(step, prompt, schema, options)
        self.assertEqual(base, run_npp.selector_digest(dict(step), prompt, dict(schema), json.loads(json.dumps(options))))
        for changed in (({'model': 'n'}, prompt, schema, options), (step, 'q', schema, options),
                        (step, prompt, {'type': 'array'}, options), (step, prompt, schema, {'templates': {}})):
            self.assertNotEqual(base, run_npp.selector_digest(*changed))


class SelectorRecordTests(unittest.TestCase):
    def test_record_mode_uses_the_production_adapter_within_the_codex_cap_and_round_trips(self):
        sent = []

        def transport(url, body, headers, timeout):
            sent.append(json.loads(body))
            content = json.dumps(CHOICE)
            return 200, json.dumps({'choices': [{'message': {'content': content}}]})

        recorder = run_npp.Recorder(run_npp.RecordCaps(1, 0), codex=lambda _: self.fail('identify Codex'),
                                    images=lambda *_: self.fail('image edit'), selector_transport=transport)
        step = {'model': 'pinned-model', 'effort': 'low', 'timeout_s': 20}
        options = {'kind': 'food', 'category': 'pantry', 'templates': {'name': ['name-item']}}
        key = ('copy', copy_pin(), run_npp.selector_digest(step, 'prompt', {}, options), 0)
        self.assertEqual(recorder.record(*key, lambda: recorder.select(step, 'prompt', {}, options)), CHOICE)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]['model'], 'pinned-model')
        self.assertIn(json.dumps(options), sent[0]['messages'][0]['content'])
        # The same key is not paid twice; a different input past the cap is refused before dispatch.
        self.assertEqual(recorder.record(*key, lambda: self.fail('re-sent')), CHOICE)
        with self.assertRaisesRegex(RuntimeError, 'record cap reached for codex'):
            recorder.select(step, 'prompt', {}, {**options, 'category': 'meat'})
        self.assertEqual(len(sent), 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'copy-tape.json'
            recorder.save(path)
            tapes = run_npp.Tapes(recorded=path)
            self.assertIn('copy', tapes.sources)
            self.assertEqual(tapes.lookup(*key)['output'], CHOICE)

    def test_a_failed_selector_call_is_recorded_as_none(self):
        recorder = run_npp.Recorder(run_npp.RecordCaps(1, 0), codex=lambda _: None, images=lambda *_: None,
                                    selector_transport=lambda *_a: (500, ''))
        self.assertIsNone(recorder.select({'model': 'm', 'effort': 'low', 'timeout_s': 1}, 'p', {}, {}))
        self.assertEqual(recorder.caps.used['codex'], 1)


if __name__ == '__main__':
    unittest.main()
