"""Contract tests for the offline NPP receipt evidence drift checker."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass.npp import evidence


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_evidence_latest_record.py'
PASS = 'PASS npp_evidence_latest_record'
FAIL = 'FAIL npp_evidence_latest_record'
LIVE_STEPS = (
    "step 0 approval=2",
    "step 1 publish=change-2:abcdef0:seen",
    "step 2 fallbacks=['a-fallback', 'x-fallback']",
    "step 3 stage=ValueError:stages.outcome: invalid value stages=1",
    "step 4 stages=1 fallbacks=2",
    "step 5 drift=True,False",
    "step 6 approval=ValueError:approval.change_id: invalid value kept=2",
    "step 7 problems=0",
)


def snapshot():
    entries = {}
    for name in ('hass', 'storefront-mockup'):
        tree = ROOT / name
        for path in (tree, *tree.rglob('*')):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


def different_even_if_missing(pinned, returned):
    return returned != pinned


class NppEvidenceLatestRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('npp_evidence_latest_record', SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError('could not load the receipt evidence checker')
        cls.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(cls.tool)

    def cli(self, *args):
        with tempfile.TemporaryDirectory() as cwd:
            return subprocess.run([sys.executable, '-B', str(SCRIPT), *args], cwd=cwd,
                                  capture_output=True, text=True, timeout=10)

    def run_main(self, code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.tool.main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(result, code)
        self.assertEqual(stderr.getvalue(), '')
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def assert_findings(self, lines, *expected):
        self.assertEqual([line for line in lines if line.startswith('FAIL')], list(expected))

    def test_c1_full_pass(self):
        # The direct entry point could discard main's result or print the wrong trailer.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # Even when later steps run, an earlier mismatch must keep the run failed.
        with patch.object(evidence, '_drift', different_even_if_missing):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines[-1], 'step 7 problems=0')
        self.assert_findings(lines, 'FAIL evidence-changed 5')

    def test_c2_1_leaked_mutation(self):
        # Losing deepcopy exposes the stage list and makes the final document invalid.
        with patch.object(evidence, 'deepcopy', lambda doc: doc):
            lines = self.run_main(1, FAIL)
        self.assert_findings(lines, 'FAIL leaked-mutation 4', 'FAIL evidence-changed 4',
                             'FAIL invalid-doc', 'FAIL evidence-changed 7')

    def test_c2_2_invalid_doc(self):
        # A real validator must reject a snapshot with the wrong schema version.
        original_doc = evidence.Evidence.doc

        def wrong_version(builder):
            doc = original_doc(builder)
            doc['evidence_version'] = 2
            return doc

        with patch.object(evidence.Evidence, 'doc', wrong_version):
            lines = self.run_main(1, FAIL)
        self.assert_findings(lines, 'FAIL invalid-doc', 'FAIL evidence-changed 7')

    def test_c2_3_evidence_changed(self):
        # A comparison against the wrong pin/index can miss an isolated change.
        with patch.object(evidence, '_drift', different_even_if_missing):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, [*LIVE_STEPS[:5], 'step 5 drift=True,True',
                                 'FAIL evidence-changed 5', *LIVE_STEPS[6:]])

    def test_c2_4_check_error(self):
        # An unexpected builder error must not escape or be treated as a refusal.
        with patch.object(evidence.Evidence, 'stage', side_effect=RuntimeError('synthetic')):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, [*LIVE_STEPS[:3], 'FAIL check-error'])

    def test_c3_usage_exit_2(self):
        # Don't accept ignored arguments, including argparse's usual help option.
        for arg in ('extra', '--unknown', '--help', '--'):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertEqual(result.stdout.splitlines()[-1:], [])
                self.assertTrue(result.stderr.startswith('usage: '))
                self.assertIn('error: unrecognized arguments:', result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Detect a receipt write, bytecode cache, or modification to checked-in inputs.
        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # No debug lines or warnings, including on a run with multiple findings.
        with patch.object(evidence, 'deepcopy', lambda doc: doc):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, [*LIVE_STEPS[:4], 'step 4 stages=2 fallbacks=2',
                                 'FAIL leaked-mutation 4', 'FAIL evidence-changed 4',
                                 *LIVE_STEPS[5:7], 'step 7 problems=1',
                                 'FAIL invalid-doc', 'FAIL evidence-changed 7'])

    def test_c6_fixture(self):
        # Returning no model is not drift, even though it differs from the pin.
        with patch.object(evidence, '_drift', different_even_if_missing):
            lines = self.run_main(1, FAIL)
        self.assertIn('step 5 drift=True,True', lines)
        self.assert_findings(lines, 'FAIL evidence-changed 5')

    def test_c7_live_pins(self):
        # Compare exact live stdout to an oracle independent of the tool's pins.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(result.stdout, '\n'.join((*LIVE_STEPS, PASS, '')))
        self.assertEqual(result.stderr, '')
        self.assertEqual(tuple(self.tool.EXPECTED), LIVE_STEPS)
