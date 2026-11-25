"""Synthetic tests for joining a saved NPP recording with its top-up; never reads the private recording or replay store."""
import contextlib
import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hass.tests.npp import run_npp
from scripts.hass import npp_merge_recordings as merge_tool

PIN, OTHER = 'a' * 64, 'b' * 64


def key(digest, ordinal=0, pin=PIN):
    return f'{pin}:{digest}:{ordinal}'


def recording(path, kinds, source='attended recording'):
    data = {kind: {'kind': kind, 'source': source, 'entries': rows} for kind, rows in kinds.items()}
    Path(path).write_text(json.dumps(data, sort_keys=True) + '\n')
    return Path(path)


class MergeRecordingsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='npp-merge-')
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.base = recording(self.dir / 'base.json', {
            's2': {key('1' * 64): {'output': {'name': 'synthetic'}}},
            'image': {key('2' * 64): {'output': 'aW1n'}},
        })

    def run_tool(self, *args, versioned=frozenset()):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = merge_tool.main([str(a) for a in args], versioned=versioned)
        return code, json.loads(out.getvalue())

    def test_a_recorder_top_up_joins_the_base_and_replays_both(self):
        recorder = run_npp.Recorder(run_npp.RecordCaps(1, 1), codex=object(), images=object())
        recorder.record('copy', PIN, '3' * 64, 0, lambda: {'name': 'T1'})
        recorder.record('copy', PIN, '3' * 64, 1, lambda: None)  # a recorded decline is kept as a row
        recorder.record('image', PIN, '4' * 64, 0, lambda: 'bmV3')
        topup = self.dir / 'topup.json'
        recorder.save(topup)
        out = self.dir / 'joined.json'
        base_sha = hashlib.sha256(self.base.read_bytes()).hexdigest()
        code, report = self.run_tool(out, self.base, topup, '--base-sha256', base_sha)
        self.assertEqual(code, 0, report)
        self.assertEqual(report['output']['rows'], {'copy': 2, 'image': 2, 's2': 1})
        self.assertEqual(report['inputs'][0]['sha256'], base_sha)
        self.assertEqual(report['output']['sha256'], hashlib.sha256(out.read_bytes()).hexdigest())
        self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)
        self.assertNotIn('synthetic', json.dumps(report))  # counts and digests only, never a row
        tapes = run_npp.Tapes(self.dir / 'no-versioned-tapes', out)
        self.assertEqual(tapes.lookup('s2', PIN, '1' * 64, 0)['output'], {'name': 'synthetic'})
        self.assertEqual(tapes.lookup('image', PIN, '4' * 64, 0)['output'], 'bmV3')
        self.assertIsNone(tapes.lookup('copy', PIN, '3' * 64, 1)['output'])
        with self.assertRaises(run_npp.TapeMiss):
            tapes.lookup('copy', PIN, '3' * 64, 2)

    def test_joined_file_uses_the_recorder_byte_format(self):
        topup = recording(self.dir / 'topup.json', {'copy': {key('5' * 64): {'output': None}}})
        out = self.dir / 'joined.json'
        self.assertEqual(self.run_tool(out, self.base, topup)[0], 0)
        expected = {**json.loads(self.base.read_text()), **json.loads(topup.read_text())}
        self.assertEqual(out.read_text(), json.dumps(expected, sort_keys=True) + '\n')

    def test_a_repeated_key_is_refused_and_nothing_is_written(self):
        topup = recording(self.dir / 'topup.json', {'image': {key('2' * 64): {'output': 'b3RoZXI='}}})
        out = self.dir / 'joined.json'
        code, report = self.run_tool(out, self.base, topup)
        self.assertEqual(code, 2)
        self.assertIn('never overwritten', report['refused'])
        self.assertFalse(out.exists())

    def test_a_key_already_on_the_versioned_tapes_is_refused(self):
        topup = recording(self.dir / 'topup.json', {'s2': {key('6' * 64): {'output': {}}}})
        code, report = self.run_tool(self.dir / 'joined.json', self.base, topup,
                                     versioned=frozenset({f"s2:{key('6' * 64)}"}))
        self.assertEqual(code, 2)
        self.assertIn('versioned tapes', report['refused'])

    def test_the_real_versioned_tapes_are_consulted_by_default(self):
        versioned = merge_tool.versioned_keys()
        self.assertEqual(versioned, set(run_npp.Tapes().entries))
        self.assertTrue(versioned)
        kind, _, rest = sorted(versioned)[0].partition(':')
        topup = recording(self.dir / 'topup.json', {kind: {rest: {'output': None}}})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = merge_tool.main([str(self.dir / 'joined.json'), str(self.base), str(topup)])
        self.assertEqual(code, 2)
        self.assertIn('versioned tapes', json.loads(out.getvalue())['refused'])

    def test_a_different_source_label_is_refused(self):
        topup = recording(self.dir / 'topup.json', {'image': {key('7' * 64): {'output': 'eA=='}}}, source='synthetic')
        code, report = self.run_tool(self.dir / 'joined.json', self.base, topup)
        self.assertEqual(code, 2)
        self.assertIn('source label', report['refused'])

    def test_wrong_base_digest_is_refused(self):
        topup = recording(self.dir / 'topup.json', {'copy': {key('8' * 64): {'output': None}}})
        code, report = self.run_tool(self.dir / 'joined.json', self.base, topup, '--base-sha256', 'f' * 64)
        self.assertEqual(code, 2)
        self.assertIn('BASE digest', report['refused'])
        self.assertFalse((self.dir / 'joined.json').exists())

    def test_malformed_inputs_are_refused(self):
        bad = {
            'not-object': [],
            'kind-mismatch': {'s2': {'kind': 'image', 'source': 'attended recording', 'entries': {key('9' * 64): {'output': 1}}}},
            'extra-field': {'s2': {'kind': 's2', 'source': 'x', 'entries': {key('9' * 64): {'output': 1, 'note': 2}}}},
            'bad-key': {'s2': {'kind': 's2', 'source': 'x', 'entries': {'pin:digest:0': {'output': 1}}}},
            'leading-zero-ordinal': {'s2': {'kind': 's2', 'source': 'x', 'entries': {f"{PIN}:{'9' * 64}:01": {'output': 1}}}},
            'no-rows': {'s2': {'kind': 's2', 'source': 'x', 'entries': {}}},
        }
        for name, data in bad.items():
            with self.subTest(name):
                path = self.dir / f'{name}.json'
                path.write_text(json.dumps(data))
                code, report = self.run_tool(self.dir / f'out-{name}.json', self.base, path)
                self.assertEqual(code, 2)
                self.assertIn('refused', report)
                self.assertFalse((self.dir / f'out-{name}.json').exists())
        (self.dir / 'garbage.json').write_text('{not json')
        self.assertEqual(self.run_tool(self.dir / 'out-garbage.json', self.base, self.dir / 'garbage.json')[0], 2)

    def test_output_must_be_new_and_outside_the_checkout(self):
        topup = recording(self.dir / 'topup.json', {'copy': {key('a' * 64): {'output': None}}})
        existing = self.dir / 'exists.json'
        existing.write_text('keep')
        code, report = self.run_tool(existing, self.base, topup)
        self.assertEqual((code, existing.read_text()), (2, 'keep'))
        inside = merge_tool.REPO / 'hass' / f'npp-merge-test-{os.getpid()}.json'
        code, report = self.run_tool(inside, self.base, topup)
        self.assertEqual(code, 2)
        self.assertIn('outside the checkout', report['refused'])
        self.assertFalse(inside.exists())

    def test_the_same_file_twice_or_a_missing_input_is_refused(self):
        self.assertEqual(self.run_tool(self.dir / 'o1.json', self.base, self.base)[0], 2)
        self.assertEqual(self.run_tool(self.dir / 'o2.json', self.base, self.dir / 'absent.json')[0], 2)
        self.assertEqual(self.run_tool(self.dir / 'o3.json', self.base, self.dir)[0], 2)

    def test_a_repeated_json_key_is_refused_before_it_can_drop_a_row(self):
        row, entry = key('c' * 64), '{"output": 1}'
        texts = {
            'row': '{"copy": {"entries": {"%s": %s, "%s": {"output": 2}}, "kind": "copy", "source": "attended recording"}}'
                   % (row, entry, row),
            'kind': '{"copy": {"entries": {"%s": %s}, "kind": "copy", "source": "attended recording"}, '
                    '"copy": {"entries": {"%s": %s}, "kind": "copy", "source": "attended recording"}}'
                    % (row, entry, key('d' * 64), entry),
            'field': '{"copy": {"entries": {"%s": {"output": 1, "output": 2}}, "kind": "copy", "source": "a", "source": "b"}}'
                     % row,
        }
        for name, text in texts.items():
            with self.subTest(name):
                path = self.dir / f'dup-{name}.json'
                path.write_text(text)
                code, report = self.run_tool(self.dir / f'out-dup-{name}.json', self.base, path)
                self.assertEqual(code, 2)
                self.assertIn('repeats a key', report['refused'])
                self.assertFalse((self.dir / f'out-dup-{name}.json').exists())

    def test_the_checked_digest_and_the_merged_rows_come_from_the_same_bytes(self):
        topup = recording(self.dir / 'topup.json', {'copy': {key('e' * 64): {'output': None}}})
        original = self.base.read_bytes()
        base_sha = hashlib.sha256(original).hexdigest()
        swapped = json.dumps({'s2': {'kind': 's2', 'source': 'attended recording',
                                     'entries': {key('f' * 64): {'output': 'replaced'}}}}, sort_keys=True).encode()
        real_read, reads = Path.read_bytes, []

        def read_then_replace(path):
            data = real_read(path)
            if path == self.base:
                reads.append(path)
                path.write_bytes(swapped)  # a concurrent replacement after the first read
            return data

        out = self.dir / 'joined.json'
        with patch.object(Path, 'read_bytes', read_then_replace):
            code, report = self.run_tool(out, self.base, topup, '--base-sha256', base_sha)
        self.assertEqual(code, 0, report)
        self.assertEqual(len(reads), 1)
        self.assertEqual(report['inputs'][0]['sha256'], base_sha)
        joined = json.loads(out.read_text())
        self.assertEqual(set(joined['s2']['entries']), {key('1' * 64)})
        self.assertNotIn('replaced', out.read_text())


if __name__ == '__main__':
    unittest.main()
