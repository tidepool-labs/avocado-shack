"""Behavioural contract for the offline NPP owner-words check."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from hass import claims

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_unsaid_owner_words.py'
PASS = 'PASS npp_unsaid_owner_words'
FAIL = 'FAIL npp_unsaid_owner_words'
LIVE_PINS = [
    'case 0 unsaid=[]',
    "case 1 unsaid=['Harbor Lane Farm']",
    "case 2 unsaid=['Harbor Lane Farm']",
    "case 3 unsaid=['Harbor Lane Farm']",
    "case 4 unsaid=['Harbor Lane Farm']",
    'case 5 unsaid=[]',
    'case 6 unsaid=[]',
    "case 7 unsaid=['Cedar Row']",
    "case 8 unsaid=['Fillmore']",
    'case 9 unsaid=[]',
]


def snapshot():
    result = {}
    for tree in (ROOT / 'hass', ROOT / 'storefront-mockup'):
        for path in (tree, *tree.rglob('*')):
            stat = path.lstat()
            result[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return result


class NppUnsaidOwnerWordsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('npp_unsaid_owner_words', SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(cls.tool)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, '-B', str(SCRIPT), *args],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )

    def run_main(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        self.assertEqual(stderr.getvalue(), '')
        return code, stdout.getvalue().splitlines()

    def placeholder_drift(self):
        with patch.object(claims, 'PLACEHOLDER', 'Producer unknown'):
            return self.run_main()

    def test_c1_full_pass(self):
        # The real launcher must propagate the successful status and finish with PASS.
        result = self.cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # A finding must be placed at its case, with a failure trailer after later cases.
        code, lines = self.placeholder_drift()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(lines[7:11], ['FAIL unsaid-changed 6', *LIVE_PINS[7:]])

    def test_c2_1_unsaid_missed(self):
        # A permissive policy must report both failures at each lost ask, in order.
        with patch.object(self.tool.live_policy, '_owner_said', return_value=True):
            code, lines = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        expected = []
        for i in range(10):
            expected.append(f'case {i} unsaid=[]')
            if i in (1, 2, 3, 4, 7, 8):
                expected.extend((f'FAIL unsaid-missed {i}', f'FAIL unsaid-changed {i}'))
        self.assertEqual(lines[:-1], expected)

    def test_c2_2_unsaid_changed(self):
        # Checking only for missed asks would overlook a newly nonempty case 6.
        code, lines = self.placeholder_drift()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')],
                         ['FAIL unsaid-changed 6'])

    def test_c2_3_check_error(self):
        # A mid-run exception must stop the checks without disclosing its message.
        unsaid = self.tool.live_policy.unsaid

        def check(draft, owner_text):
            if owner_text == 'add this honey':
                raise RuntimeError('synthetic exception detail')
            return unsaid(draft, owner_text)

        with patch.object(self.tool.live_policy, 'unsaid', side_effect=check) as call:
            code, lines = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(lines[:-1], [LIVE_PINS[0], 'FAIL check-error'])
        self.assertEqual(call.call_count, 2)

    def test_c3_usage_exit_2(self):
        # Accepting an argument or using default argparse help violates the CLI contract.
        for arg in ('extra', '--unknown', '--help', '-h', '--'):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.startswith('usage: '))
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f'{SCRIPT.name}: error: unrecognized arguments: {arg}')

    def test_c4_read_only(self):
        # Detect new files and modifications to existing inputs or directory entries.
        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Extra logging, blank lines or a trailing debug message would break consumers.
        result = self.cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, '')
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(len(lines), 11)
        for line in lines[:-1]:
            self.assertRegex(line, r"\Acase \d+ unsaid=\[(?:'[^']+'(?:, '[^']+')*)?\]\Z")

    def test_c6_fixture(self):
        # The draft must retain the original fixture brand, not follow the mutated sentinel.
        code, lines = self.placeholder_drift()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(lines[:-1], [
            *LIVE_PINS[:6],
            "case 6 unsaid=['Producer not identified', 'From the market']",
            'FAIL unsaid-changed 6', *LIVE_PINS[7:],
        ])

    def test_c7_live_pins(self):
        # Pin every unmodified answer independently of the tool's own EXPECTED table.
        code, lines = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(lines[:-1], LIVE_PINS)
