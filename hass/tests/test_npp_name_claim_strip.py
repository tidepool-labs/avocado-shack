"""Pin the offline name-claim checker's CLI and its live fixture results."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from hass import claims, newitem


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_name_claim_strip.py'
PASS = 'PASS npp_name_claim_strip'
FAIL = 'FAIL npp_name_claim_strip'
LIVE_LINES = [
    "case 0 name='Wildflower Honey'",
    "case 1 name='Honey'",
    "case 2 name='Wildflower Honey'",
    "case 3 name='Honey'",
    "case 4 name='Apricot Jam'",
    "case 5 name='Olive oil'",
    "case 6 name='Corn tortillas'",
    "case 7 name='Green tea'",
    "case 8 name='Eggs'",
    "case 9 name='Honey'",
    "case 10 name=None",
]


def cli(*args):
    return subprocess.run([sys.executable, '-B', str(SCRIPT), *args],
                          cwd=ROOT, capture_output=True, text=True, timeout=10)


def snapshot():
    entries = {}
    for tree in ('hass', 'storefront-mockup'):
        root = ROOT / tree
        for path in (root, *root.rglob('*')):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class NameClaimStripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('npp_name_claim_strip', SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError(f'Cannot load {SCRIPT.name}')
        cls.tool = importlib.util.module_from_spec(spec)
        # The entry point inserts the repo root; don't let that leak into other tests.
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(cls.tool)

    def run_check(self, code, trailer):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = self.tool.main([])
        self.assertEqual(result, code)
        self.assertEqual(err.getvalue(), '')
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[-1:], [trailer])
        return lines[:-1]

    def test_c1_full_pass(self):
        # Calling the real CLI catches a broken entry point or lost exit code.
        result = cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # Findings must be emitted beside their case, not grouped at the end.
        with patch.object(newitem, 'claim_terms', lambda text: []):
            lines = self.run_check(1, FAIL)
        expected = []
        for i, (name, _, _) in enumerate(self.tool.CASES):
            expected.append(f'case {i} name={name!r}')
            if i in (0, 1, 3, 4, 5, 6, 7, 8):
                expected.extend((f'FAIL claim-left-in-name {i}', f'FAIL name-changed {i}'))
        self.assertEqual(lines, expected)

    def test_c2_1_claim_left_in_name(self):
        # A disabled detector must not hide literal claim fragments in the output.
        with patch.object(newitem, 'claim_terms', lambda text: []):
            lines = self.run_check(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], [
            f'FAIL {reason} {i}'
            for i in (0, 1, 3, 4, 5, 6, 7, 8)
            for reason in ('claim-left-in-name', 'name-changed')
        ])

    def test_c2_2_name_changed(self):
        # Changing term coverage must still compare the emitted name to the pin.
        with patch.object(claims, 'FARM_TERMS', ()):
            lines = self.run_check(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL name-changed')],
                         ['FAIL name-changed 8'])
        self.assertEqual(lines[8], "case 8 name='Free-range eggs'")

    def test_c2_3_check_error(self):
        # A thrown call must stop the loop without exposing exception details.
        real_strip = newitem.without_claims

        def fail_on_second(name, kind):
            if name == 'Raw local honey':
                raise RuntimeError('synthetic exception text')
            return real_strip(name, kind)

        with patch.object(newitem, 'without_claims', side_effect=fail_on_second) as strip:
            lines = self.run_check(1, FAIL)
        self.assertEqual(strip.call_count, 2)
        self.assertEqual(lines, [LIVE_LINES[0], 'FAIL check-error'])

    def test_c3_usage_exit_2(self):
        # Reject even argparse's usual help switches: the CLI takes no arguments.
        for arg in ('fixture', '--unknown', '--help', '-h', '--'):
            with self.subTest(arg=arg):
                result = cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertEqual(result.stderr.splitlines()[-1],
                                 f'{SCRIPT.name}: error: unrecognized arguments: {arg}')

    def test_c4_read_only(self):
        # A new cache or rewritten listing would leave metadata drift in these trees.
        before = snapshot()
        result = cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug text or warnings must not leak onto either CLI output stream.
        result = cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        *lines, trailer = result.stdout.splitlines()
        self.assertEqual(trailer, PASS)
        self.assertEqual(len(lines), 11)
        for i, line in enumerate(lines):
            self.assertRegex(line, rf"^case {i} name=(?:'[^']*'|None)$")

    def test_c6_fixture(self):
        # Removing the farm term family should affect only the free-range case.
        with patch.object(claims, 'FARM_TERMS', ()):
            lines = self.run_check(1, FAIL)
        self.assertEqual(lines, LIVE_LINES[:8] + [
            "case 8 name='Free-range eggs'",
            'FAIL claim-left-in-name 8',
            'FAIL name-changed 8',
        ] + LIVE_LINES[9:])

    def test_c7_live_pins(self):
        # Compare with independent pins, not the checker constant or a reimplementation.
        self.assertEqual(self.run_check(0, PASS), LIVE_LINES)
