"""Offline behavioural contract for the local endpoint/JSON drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from itertools import chain
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_local_endpoint_json.py"
PASS = "PASS npp_local_endpoint_json"
FAIL = "FAIL npp_local_endpoint_json"
LIVE_LINES = [
    "case 0 url=ok:'http://127.0.0.1:11434'",
    "case 1 url=ok:'http://localhost:11434'",
    "case 2 url=ok:'http://[::1]:8080'",
    "case 3 url=refused",
    "case 4 url=refused",
    "case 5 url=refused",
    "case 6 url=refused",
    "case 7 url=refused",
    "case 8 url=refused",
    "case 9 json=ok:{'op': 'product.add', 'n': 2}",
    "case 10 json=refused",
    "case 11 json=refused",
    "case 12 json=refused",
    "case 13 json=refused",
]


class EveryHost:
    def __contains__(self, _host):
        return True


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for entry in chain((tree,), tree.rglob("*")):
            stats = entry.lstat()
            entries[entry.relative_to(ROOT)] = (stats.st_size, stats.st_mtime_ns)
    return entries


class NppLocalEndpointJsonTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("npp_local_endpoint_json", SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError("could not load the endpoint/JSON check")
        self.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(self.tool)
        self.repo = self.tool.interpreter_local

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )

    def run_main(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.tool.main([])
        self.assertEqual(stderr.getvalue(), "")
        return code, stdout.getvalue().splitlines()

    def assert_status(self, run, code, trailer):
        actual_code, lines = run
        self.assertEqual(actual_code, code, lines)
        self.assertEqual(lines[-1:], [trailer])
        return lines

    def assert_cli_pass(self, result):
        self.assertEqual(result.stderr, "")
        return self.assert_status((result.returncode, result.stdout.splitlines()), 0, PASS)

    def test_c1_full_pass(self):
        # The entry point must propagate main's success and trailer to the CLI.
        self.assert_cli_pass(self.run_cli())

    def test_c2_findings_trailer(self):
        # A finding must latch failure even when all subsequent checks pass.
        with patch.object(self.repo, "LOOPBACK", EveryHost()):
            lines = self.assert_status(self.run_main(), 1, FAIL)
        self.assertEqual(lines[-2], LIVE_LINES[-1])

    def test_c2_1_unsafe_endpoint_or_json(self):
        # Widening the host check must be reported as unsafe, not only as drift.
        with patch.object(self.repo, "LOOPBACK", EveryHost()):
            lines = self.assert_status(self.run_main(), 1, FAIL)
        self.assertEqual(lines, LIVE_LINES[:4] + [
            "case 4 url=ok:'http://example.com:11434'",
            "FAIL unsafe-endpoint-or-json 4",
            "FAIL endpoint-changed 4",
        ] + LIVE_LINES[5:] + [FAIL])

    def test_c2_2_endpoint_changed(self):
        # A newly refused safe endpoint still drifts, immediately after its case.
        with patch.object(self.repo, "LOOPBACK", ("127.0.0.1",)):
            lines = self.assert_status(self.run_main(), 1, FAIL)
        self.assertEqual(lines[1:5], [
            "case 1 url=refused", "FAIL endpoint-changed 1",
            "case 2 url=refused", "FAIL endpoint-changed 2",
        ])

    def test_c2_3_check_error(self):
        # An unexpected decoder exception must stop the run without leaking text.
        with patch.object(self.repo, "_strict", side_effect=RuntimeError("fixture detail")) as check:
            lines = self.assert_status(self.run_main(), 1, FAIL)
            check.assert_called_once_with('{"op": "product.add", "n": 2}')
        self.assertEqual(lines, LIVE_LINES[:9] + ["FAIL check-error", FAIL])

    def test_c3_usage_exit_2(self):
        # Nothing can turn this fixed probe into an input-taking CLI, even help.
        for arg in ("positional", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("usage: "), result.stderr)

    def test_c4_read_only(self):
        # Detect a report/cache write or an edit to either input tree.
        before = snapshot()
        self.assert_cli_pass(self.run_cli())
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Stray debug lines or stderr would make the report unparseable.
        shape = re.compile(
            r"case \d+ (?:url|json)=(?:ok:.+|refused)"
            r"|FAIL (?:unsafe-endpoint-or-json \d+|endpoint-changed \d+|check-error)"
            r"|(?:PASS|FAIL) npp_local_endpoint_json"
        )
        for mutate, code, trailer in ((False, 0, PASS), (True, 1, FAIL)):
            with self.subTest(mutate=mutate):
                if mutate:
                    with patch.object(self.repo, "LOOPBACK", EveryHost()):
                        run = self.run_main()
                else:
                    run = self.run_main()
                for line in self.assert_status(run, code, trailer):
                    self.assertIsNotNone(shape.fullmatch(line), line)

    def test_c6_fixture(self):
        # Narrowing loopback membership yields drift only, in ascending order.
        with patch.object(self.repo, "LOOPBACK", ("127.0.0.1",)):
            lines = self.assert_status(self.run_main(), 1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], [
            "FAIL endpoint-changed 1", "FAIL endpoint-changed 2",
        ])

    def test_c7_live_pins(self):
        # Exact report, with real calls: a cached transcript must not pass.
        with (
            patch.object(self.repo, "check_url", wraps=self.repo.check_url) as url,
            patch.object(self.repo, "_strict", wraps=self.repo._strict) as strict,
        ):
            lines = self.assert_status(self.run_main(), 0, PASS)
        self.assertEqual(lines, LIVE_LINES + [PASS])
        self.assertEqual(url.call_args_list, [call(value) for kind, value in self.tool.CASES if kind == "url"])
        self.assertEqual(strict.call_args_list, [call(value) for kind, value in self.tool.CASES if kind == "json"])
