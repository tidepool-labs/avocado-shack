"""Offline contract for the maker-site host and address drift guard."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import ipaddress
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_maker_host_guard.py"
PASS = "PASS npp_maker_host_guard"
FAIL = "FAIL npp_maker_host_guard"
LIVE_LINES = [
    "case 0 host=yes",
    "case 1 host=yes",
    "case 2 host=no",
    "case 3 host=no",
    "case 4 host=no",
    "case 5 host=no",
    "case 6 host=no",
    "case 7 host=yes",
    "case 8 host=no",
    "case 9 ip=yes",
    "case 10 ip=no",
    "case 11 ip=no",
    "case 12 ip=yes",
    "case 13 ip=no",
    "case 14 ip=no",
    "case 15 ip=no",
]
LOCAL_FINDINGS = ["FAIL private-host-allowed 2", "FAIL host-changed 2"]
V6_FINDINGS = ["FAIL private-host-allowed 14", "FAIL host-changed 14"]


def load_guard():
    spec = importlib.util.spec_from_file_location("npp_maker_host_guard", SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError("could not load npp_maker_host_guard")
    guard = importlib.util.module_from_spec(spec)
    with patch.object(sys, "path", sys.path.copy()):
        spec.loader.exec_module(guard)
    return guard


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        cwd=ROOT, capture_output=True, text=True, timeout=10,
    )


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class MakerHostGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = load_guard()

    def run_main(self, code, trailer):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.guard.main([])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(result, code)
        self.assertEqual(lines[-1:], [trailer])
        self.assertEqual(stderr.getvalue(), "")
        return lines

    def findings(self, lines):
        return [line for line in lines[:-1] if line.startswith("FAIL ")]

    def test_c1_full_pass(self):
        # A clean CLI run must propagate success and end with the pass trailer.
        result = run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def test_c2_findings_trailer(self):
        # Findings must neither terminate the loop early nor be batched at the end.
        with (
            patch.object(self.guard.maker_site, "LOCAL_NAMES", frozenset()),
            patch.object(self.guard.maker_site, "_NOT_PUBLIC_V6", ()),
        ):
            lines = self.run_main(1, FAIL)
        expected = LIVE_LINES.copy()
        expected[14:15] = ["case 14 ip=yes", *V6_FINDINGS]
        expected[2:3] = ["case 2 host=yes", *LOCAL_FINDINGS]
        self.assertEqual(lines, [*expected, FAIL])

    def test_c2_1_private_host_allowed(self):
        # Dropping the local-name filter must report a safety finding, not just drift.
        with patch.object(self.guard.maker_site, "LOCAL_NAMES", frozenset()):
            lines = self.run_main(1, FAIL)
        self.assertEqual(self.findings(lines), LOCAL_FINDINGS)

    def test_c2_2_host_changed(self):
        # A safety finding must not mask the independent pinned-answer comparison.
        with patch.object(self.guard.maker_site, "_NOT_PUBLIC_V6", ()):
            lines = self.run_main(1, FAIL)
        start = lines.index("case 14 ip=yes")
        self.assertEqual(lines[start + 1:start + 3], V6_FINDINGS)

    def test_c2_3_check_error(self):
        # An error after one success must stop checks and never disclose exception text.
        with (
            patch.object(self.guard.maker_site, "_plain_host",
                         side_effect=[True, RuntimeError("synthetic error detail")]) as host,
            patch.object(self.guard.maker_site, "_public_ip",
                         wraps=self.guard.maker_site._public_ip) as ip,
        ):
            lines = self.run_main(1, FAIL)
        self.assertEqual(lines, ["case 0 host=yes", "FAIL check-error", FAIL])
        self.assertEqual(host.call_args_list, [call("cedarrow.com"), call("shop.cedar-row.co.uk")])
        ip.assert_not_called()

    def test_c3_usage_exit_2(self):
        # Unexpected input cannot be silently ignored or produce a success report.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line on usage errors.
                self.assertTrue(result.stderr.startswith("usage: "))
                self.assertIn("error: ", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # A future side effect must not touch either tree even if the report passes.
        before = snapshot()
        result = run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Debug output or raw fixture values would violate the report format.
        result = run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [PASS])
        with patch.object(self.guard.maker_site, "LOCAL_NAMES", frozenset()):
            failed_lines = self.run_main(1, FAIL)
        form = re.compile(r"case [0-9]+ (?:host|ip)=(?:yes|no)|"
                          r"FAIL (?:private-host-allowed|host-changed) [0-9]+|FAIL check-error")
        for line in lines[:-1] + failed_lines[:-1]:
            self.assertIsNotNone(form.fullmatch(line), line)

    def test_c6_fixture(self):
        # Losing the IPv6 exclusion table must trip both checks on the pinned fixture.
        with patch.object(self.guard.maker_site, "_NOT_PUBLIC_V6", ()):
            lines = self.run_main(1, FAIL)
        self.assertEqual(self.findings(lines), V6_FINDINGS)

    def test_c7_live_pins(self):
        # Detect changed answers, reordering, skipped predicates, or hardcoded output.
        with (
            patch.object(self.guard.maker_site, "_plain_host",
                         wraps=self.guard.maker_site._plain_host) as host,
            patch.object(self.guard.maker_site, "_public_ip",
                         wraps=self.guard.maker_site._public_ip) as ip,
        ):
            lines = self.run_main(0, PASS)
        self.assertEqual(lines, [*LIVE_LINES, PASS])
        self.assertEqual(host.call_args_list,
                         [call(value) for kind, value in self.guard.CASES if kind == "host"])
        self.assertEqual(ip.call_args_list,
                         [call(ipaddress.ip_address(value)) for kind, value in self.guard.CASES if kind == "ip"])


if __name__ == "__main__":
    unittest.main()
