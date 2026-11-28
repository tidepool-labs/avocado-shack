"""Offline behaviour tests for the kept-private intake drift check."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_intake_private_lines.py'
PASS = 'PASS npp_intake_private_lines'
FAIL = 'FAIL npp_intake_private_lines'
# Independent stdout pins, including repr's escaped private-use quote marks.
CASE_LINES = [
    'case 0 lines=[]',
    r"case 1 lines=['Kept private, not on the website:', 'Bought: 12 \ue000jars\ue001.', "
    "'Sold per item.', 'Price: $9.50 for each one.', 'You paid: $4.25 for each one.']",
    r"case 2 lines=['Kept private, not on the website:', 'Bought: 1 \ue000loaf\ue001.']",
    r"case 3 lines=['Kept private, not on the website:', 'Bought: 2.5 \ue000lb\ue001.', "
    "'Sold per pound.', 'Price: $6.00 per pound.']",
    r"case 4 lines=['Kept private, not on the website:', 'Origin: \ue000Fillmore hills\ue001.', "
    r"'On the label (unverified, your word): \ue000raw\ue001.']",
    "case 5 lines=['Kept private, not on the website:', 'Best by: Jan 15, 2027.', "
    '"Bought or received: a day I can\'t read."]',
    r"case 6 lines=['Kept private, not on the website:', 'Low on stock at: 0.', "
    r"'Your sentence for customers: \ue000Great on toast\ue001.']",
    "case 7 lines=['Kept private, not on the website:', 'Skipped, so I left them blank: qty, price, cost.']",
    'case 8 lines=[]',
]


def snapshot():
    entries = {}
    for tree in (ROOT / 'hass', ROOT / 'storefront-mockup'):
        for path in (tree, *tree.rglob('*')):
            info = path.lstat()
            entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return entries


class PrivateLinesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('npp_intake_private_lines', SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', list(sys.path)):
            spec.loader.exec_module(cls.tool)

    def invoke(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args], cwd=ROOT,
                              capture_output=True, text=True, timeout=10)

    def run_main(self, code, trailer):
        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
            result = self.tool.main([])
        self.assertEqual(result, code)
        self.assertEqual(stderr.getvalue(), '')
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def test_c1_full_pass(self):
        # A working main() is not enough if the CLI fails to import or exit cleanly.
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # Findings must stay beside their case rather than being batched at the end.
        with patch.object(self.tool.item_intake, 'PRIVATE_HEAD', 'Draft:'):
            lines = self.run_main(1, FAIL)
        expected = [CASE_LINES[0]]
        for i in range(1, 8):
            expected.extend((CASE_LINES[i].replace('Kept private, not on the website:', 'Draft:'),
                             f'FAIL unmarked-private {i}', f'FAIL lines-changed {i}'))
        self.assertEqual(lines, [*expected, CASE_LINES[8]])

    def test_c2_1_unmarked_private(self):
        # Pin the heading independently so a renamed repo constant cannot redefine it.
        with patch.object(self.tool.item_intake, 'PRIVATE_HEAD', 'Draft:'):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], [
            finding for i in range(1, 8)
            for finding in (f'FAIL unmarked-private {i}', f'FAIL lines-changed {i}')
        ])
        # A nonempty intake with no summary at all is also unmarked.
        original = self.tool.item_intake.private_lines

        def omit_loaf(intake):
            rendered = original(intake)
            return [] if intake == {'qty': 1, 'qty_unit': 'loaf'} else rendered

        with patch.object(self.tool.item_intake, 'private_lines', omit_loaf):
            lines = self.run_main(1, FAIL)
        i = lines.index('case 2 lines=[]')
        self.assertEqual(lines[i + 1:i + 3], ['FAIL unmarked-private 2', 'FAIL lines-changed 2'])

    def test_c2_2_lines_changed(self):
        # A valid heading must not let changed price/cost wording go unnoticed.
        with patch.object(self.tool.item_intake, '_per', lambda intake: 'each'):
            lines = self.run_main(1, FAIL)
        changed = CASE_LINES[3].replace('Price: $6.00 per pound.', 'Price: $6.00 each.')
        position = lines.index(changed)
        self.assertEqual(lines[position + 1], 'FAIL lines-changed 3')

    def test_c2_3_check_error(self):
        # A renderer failure must stop the loop without printing exception text.
        repo = self.tool.item_intake
        first = repo.private_lines({})
        with patch.object(repo, 'private_lines', side_effect=[first, RuntimeError('fixture detail')]) as call:
            lines = self.run_main(1, FAIL)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(lines, [CASE_LINES[0], 'FAIL check-error'])

    def test_c3_usage_exit_2(self):
        # Even argparse's usual help flags and end-of-options marker are not accepted.
        for arg in ('extra', '--unknown', '-h', '--help', '--'):
            with self.subTest(arg=arg):
                result = self.invoke(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f'{SCRIPT.name}: error: unrecognized arguments: {arg}')

    def test_c4_read_only(self):
        # Catch writes to either source tree, including incidental bytecode.
        before = snapshot()
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Diagnostic chatter or extra blank lines must not enter either stream.
        result = self.invoke()
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        *passed, trailer = result.stdout.splitlines()
        self.assertEqual(trailer, PASS)
        with patch.object(self.tool.item_intake, 'PRIVATE_HEAD', 'Draft:'):
            findings = self.run_main(1, FAIL)
        for line in passed:
            self.assertRegex(line, r'\Acase [0-8] lines=\[.*\]\Z')
        for line in findings:
            self.assertRegex(line, r'\A(?:case [0-8] lines=\[.*\]|FAIL (?:unmarked-private|lines-changed) [0-8])\Z')

    def test_c6_fixture(self):
        # A mutation of pricing units must affect only the two priced intakes.
        with patch.object(self.tool.item_intake, '_per', lambda intake: 'each'):
            lines = self.run_main(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')],
                         ['FAIL lines-changed 1', 'FAIL lines-changed 3'])

    def test_c7_live_pins(self):
        # Verify the exact serialized wording and exercise the real producer for every case.
        repo = self.tool.item_intake
        with patch.object(repo, 'private_lines', wraps=repo.private_lines) as call:
            self.assertEqual(self.run_main(0, PASS), CASE_LINES)
        self.assertEqual(call.call_count, len(CASE_LINES))
