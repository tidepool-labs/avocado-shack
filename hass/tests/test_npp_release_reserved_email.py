"""Exercise the offline release email check on fixtures only."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_release_reserved_email.py'
PASS = 'PASS npp_release_reserved_email'
FAIL = 'FAIL npp_release_reserved_email'
# Independent output oracle, measured on main; do not read the tool's EXPECTED.
LIVE_LINES = [
    "case 0 hits=['ana@fixture-shop.com'] binary=no",
    'case 1 hits=[] binary=no',
    'case 2 hits=[] binary=no',
    'case 3 hits=[] binary=no',
    'case 4 hits=[] binary=no',
    'case 5 hits=[] binary=yes',
    "case 6 hits=['abc@fixture-shop.com'] binary=yes",
    'case 7 hits=[] binary=yes',
    "case 8 hits=['abc@fixture-shop.xyz'] binary=no",
    "case 9 hits=['abc@fixture-shop.com'] binary=yes",
]


def cli(*args):
    return subprocess.run(
        [sys.executable, '-B', str(SCRIPT), *args],
        cwd=ROOT, capture_output=True, text=True, timeout=10,
    )


def snapshot():
    entries = {}
    for tree in (ROOT / 'hass', ROOT / 'storefront-mockup'):
        for path in (tree, *tree.rglob('*')):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class ReleaseReservedEmailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('npp_release_reserved_email', SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError('cannot load release email check')
        cls.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(cls.tool)

    def run_tool(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        self.assertEqual(stderr.getvalue(), '')
        return code, stdout.getvalue().splitlines()

    def test_c1_full_pass(self):
        # An incorrect exit wrapper can report success but return a nonzero code.
        result = cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # A finding must neither stop later cases nor fall through to PASS.
        with patch.object(self.tool.publish_live, 'BINARY_TLDS', ()):
            code, lines = self.run_tool()
        self.assertEqual(code, 1)
        self.assertEqual(lines, LIVE_LINES[:6] + [
            'case 6 hits=[] binary=yes',
            'FAIL real-address-dropped 6',
            'FAIL hits-changed 6',
            *LIVE_LINES[7:9],
            'case 9 hits=[] binary=yes',
            'FAIL real-address-dropped 9',
            'FAIL hits-changed 9',
            FAIL,
        ])

    def test_c2_1_real_address_dropped(self):
        # An overbroad reserved predicate must report each missing real address.
        with patch.object(self.tool.publish_live, 'reserved_address', return_value=True):
            code, lines = self.run_tool()
        self.assertEqual(code, 1)
        self.assertEqual(lines, [
            'case 0 hits=[] binary=no',
            'FAIL real-address-dropped 0',
            'FAIL hits-changed 0',
            *LIVE_LINES[1:6],
            'case 6 hits=[] binary=yes',
            'FAIL real-address-dropped 6',
            'FAIL hits-changed 6',
            LIVE_LINES[7],
            'case 8 hits=[] binary=no',
            'FAIL real-address-dropped 8',
            'FAIL hits-changed 8',
            'case 9 hits=[] binary=yes',
            'FAIL real-address-dropped 9',
            'FAIL hits-changed 9',
            FAIL,
        ])

    def test_c2_2_hits_changed(self):
        # Checking only lost real addresses would miss a newly reported .test hit.
        with patch.object(self.tool.publish_live, 'RESERVED_TLDS', ()):
            code, lines = self.run_tool()
        self.assertEqual(code, 1)
        self.assertEqual(lines, LIVE_LINES[:3] + [
            "case 3 hits=['qa@shop.test'] binary=no",
            'FAIL hits-changed 3',
        ] + LIVE_LINES[4:] + [FAIL])

    def test_c2_3_check_error(self):
        # A mid-run failure must suppress exception details and skip all later cases.
        repo = self.tool.publish_live
        real_pattern_hits = repo.pattern_hits

        def fail_second(name, rx, text, path):
            if text == 'you@example.com':
                raise RuntimeError('synthetic exception detail')
            return real_pattern_hits(name, rx, text, path)

        with patch.object(repo, 'pattern_hits', side_effect=fail_second) as hits:
            code, lines = self.run_tool()
        self.assertEqual(code, 1)
        self.assertEqual(lines, [LIVE_LINES[0], 'FAIL check-error', FAIL])
        self.assertEqual(hits.call_args_list, [
            call('email', repo.PATTERNS['email'], 'write to ana@fixture-shop.com today', 'page.html'),
            call('email', repo.PATTERNS['email'], 'you@example.com', 'page.html'),
        ])

    def test_c3_usage_exit_2(self):
        # Ignored arguments or argparse's default help would violate the no-argument CLI.
        for arg in ('fixture', '--unknown', '--help', '-h', '--'):
            with self.subTest(arg=arg):
                result = cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertIn('unrecognized arguments:', result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # A report sidecar or rewritten artifact would change the tree snapshot.
        before = snapshot()
        result = cli()
        self.assertEqual(snapshot(), before)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c5_output_shape(self):
        # Debug logging, extra blank lines or malformed labels break the output format.
        result = cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, '')
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], PASS)
        for i, line in enumerate(lines[:-1]):
            self.assertRegex(line, rf'^case {i} hits=\[.*\] binary=(?:yes|no)$')

    def test_c6_fixture(self):
        # Dropping the reserved-ending rule may affect case 3 and no other case.
        with patch.object(self.tool.publish_live, 'RESERVED_TLDS', ()):
            code, lines = self.run_tool()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith('FAIL ')],
                         ['FAIL hits-changed 3'])

    def test_c7_live_pins(self):
        # An altered address filter or binary classifier must change the pinned output.
        code, lines = self.run_tool()
        self.assertEqual(code, 0)
        self.assertEqual(lines, LIVE_LINES + [PASS])


if __name__ == '__main__':
    unittest.main()
