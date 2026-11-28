"""Offline contract tests for the live-gate refusal wording drift check."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/hass/npp_refusal_plain_reason.py'
PASS = 'PASS npp_refusal_plain_reason'
FAIL = 'FAIL npp_refusal_plain_reason'


def snapshot():
    result = {}
    for name in ('hass', 'storefront-mockup'):
        tree = ROOT / name
        for path in (tree, *tree.rglob('*')):
            info = path.lstat()
            result[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
    return result


class NppRefusalPlainReasonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError(f'Cannot load {SCRIPT.name}')
        cls.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', sys.path.copy()):
            spec.loader.exec_module(cls.tool)

    def run_check(self, code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.tool.main([])
        self.assertEqual(status, code)
        self.assertEqual(stderr.getvalue(), '')
        lines = stdout.getvalue().splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], trailer)
        return lines[:-1]

    def cli(self, *args, cwd=ROOT):
        return subprocess.run(
            [sys.executable, '-B', str(SCRIPT), *args], cwd=cwd,
            capture_output=True, text=True, encoding='utf-8', timeout=10,
        )

    def test_c1_full_pass(self):
        # A checker with a false green could skip the repo call entirely.
        policy = self.tool.live_policy
        with patch.object(policy, '_plain_reason', wraps=policy._plain_reason) as probe:
            lines = self.run_check(0, PASS)
        self.assertEqual(probe.call_args_list, [call(reason) for reason in self.tool.CASES])
        self.assertEqual(len(lines), 17)

    def test_c2_findings_trailer(self):
        # A finding in the final case must still set the aggregate status.
        policy = self.tool.live_policy
        real = policy._plain_reason

        def changed_last(reason):
            why, nxt = real(reason)
            return (why, 'Try new wording.') if reason == 'fixture nonsense' else (why, nxt)

        with patch.object(policy, '_plain_reason', side_effect=changed_last):
            lines = self.run_check(1, FAIL)
        self.assertEqual(lines[-1], 'FAIL reason-changed 16')

    def test_c2_1_unplain_refusal(self):
        # Case-sensitive checks or checking only the explanation miss this referral.
        policy = self.tool.live_policy
        with patch.object(policy, 'RESEND', 'Ask Graham to send it again.'):
            lines = self.run_check(1, FAIL)
        expected = []
        for i, line in enumerate(self.tool.EXPECTED):
            if i in (6, 7, 8, 11):
                why, _, _ = line.partition(' next=')
                expected.extend([
                    why + " next='Ask Graham to send it again.'",
                    f'FAIL unplain-refusal {i}',
                    f'FAIL reason-changed {i}',
                ])
            else:
                expected.append(line)
        self.assertEqual(lines, expected)

        # An empty why and a mixed-case referral in why must also be flagged.
        real = policy._plain_reason
        for replacement in ('', 'Ask gRaHaM.'):
            with self.subTest(why=replacement):
                def changed_why(reason):
                    why, nxt = real(reason)
                    return (replacement if reason == 'fixture nonsense' else why), nxt

                with patch.object(policy, '_plain_reason', side_effect=changed_why):
                    lines = self.run_check(1, FAIL)
                self.assertEqual(lines[-2:], ['FAIL unplain-refusal 16', 'FAIL reason-changed 16'])

    def test_c2_2_reason_changed(self):
        # Wording may still be plain but differ from the pin; report it inline.
        with patch.object(self.tool.live_policy, 'PLAIN_KINDS', {}):
            lines = self.run_check(1, FAIL)
        expected = self.tool.EXPECTED.copy()
        expected[6:7] = [expected[6].replace('a price', "a claim I can't check"), 'FAIL reason-changed 6']
        self.assertEqual(lines, expected)

    def test_c2_3_check_error(self):
        # A later exception must not leak its text, retry, or run another case.
        policy = self.tool.live_policy
        real = policy._plain_reason
        first, second = self.tool.CASES[:2]

        def interrupted(reason):
            if reason == second:
                raise RuntimeError('synthetic exception text')
            return real(reason)

        with patch.object(policy, '_plain_reason', side_effect=interrupted) as probe:
            lines = self.run_check(1, FAIL)
        self.assertEqual(probe.call_args_list, [call(first), call(second)])
        self.assertEqual(lines, [self.tool.EXPECTED[0], 'FAIL check-error'])

    def test_c3_usage_exit_2(self):
        # Positionals, unknown flags and even argparse's usual help are not accepted.
        for arg in ('fixture', '--unknown', '-h', '--help', '--'):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, '')
                self.assertIn('error: unrecognized arguments:', result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # A report or cache write could alter tracked inputs or leave new files.
        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # A debug banner, malformed repr line or import warning breaks the CLI protocol.
        result = self.cli(cwd=ROOT.parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(len(lines), 18)
        for i, line in enumerate(lines[:-1]):
            self.assertRegex(line, rf'^case {i} why=(?:".*"|\'.*\') next=(?:None|".*"|\'.*\')$')

    def test_c6_fixture(self):
        # The known-kind fallback changes case 6 only, not unchecked or unknown claims.
        with patch.object(self.tool.live_policy, 'PLAIN_KINDS', {}):
            lines = self.run_check(1, FAIL)
        self.assertEqual([line for line in lines if line.startswith('FAIL ')], ['FAIL reason-changed 6'])

    def test_c7_live_pins(self):
        # A wording change, a missing row, or a changed None next step breaks an exact pin.
        lines = self.run_check(0, PASS)
        self.assertEqual(lines, self.tool.EXPECTED)


if __name__ == '__main__':
    unittest.main()
