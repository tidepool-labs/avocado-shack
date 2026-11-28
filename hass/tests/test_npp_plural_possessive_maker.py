"""Offline contract tests for the S3 maker diagnostic."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_plural_possessive_maker.py"
PASS = "PASS npp_plural_possessive_maker"
FAIL = "FAIL npp_plural_possessive_maker"


def snapshot():
    entries = {}
    for name in ("hass", "storefront-mockup"):
        root = ROOT / name
        for path in (root, *root.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class PluralPossessiveMakerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(SCRIPT.stem, SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def run_cli(self, *args):
        with TemporaryDirectory() as directory:
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPT), *args], cwd=directory,
                text=True, capture_output=True, timeout=10,
            )

    def run_fixture(self, *, fault=None):
        original = self.tool.missing._owner_maker

        def parse(texts, item):
            if fault is not None and texts == ["Joe’s honey"]:
                return fault()
            return original([text.replace("s' ", "s's ").replace("s’ ", "s’s ")
                             for text in texts], item)

        stdout, stderr = StringIO(), StringIO()
        with patch.object(self.tool.missing, "_owner_maker", side_effect=parse) as check:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = self.tool.main([])
        self.assertEqual(stderr.getvalue(), "")
        return status, stdout.getvalue().splitlines(), check.call_args_list

    def test_c1_full_pass(self):
        # Unconditionally failing the diagnostic would hide a repaired parser.
        status, lines, _ = self.run_fixture()
        self.assertEqual(status, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertEqual(len(lines), 7)
        self.assertFalse(any(line.startswith("FAIL ") for line in lines))

    def test_c2_findings_trailer(self):
        # A warning-only run must not return success to a caller.
        status, lines, _ = self.run_fixture(fault=lambda: None)
        self.assertEqual(status, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(sum(line == FAIL for line in lines), 1)

    def assert_single_finding(self, fault, finding, observed):
        status, lines, _ = self.run_fixture(fault=fault)
        self.assertEqual(status, 1)
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(len(lines), 8)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")], [finding])
        self.assertEqual(lines[1:3], [f"case 1 maker={observed}", finding])
        self.assertEqual(lines[-2], "case 5 maker=Miners")

    def test_c2_1_maker_missed(self):
        # None is a miss, not a wrong maker or an ignored case.
        self.assert_single_finding(lambda: None, "FAIL maker-missed 1", "none")

    def test_c2_2_maker_wrong(self):
        # A nonempty result is insufficient if the name is not the expected one.
        self.assert_single_finding(lambda: "Miners", "FAIL maker-wrong 1", "Miners")

    def test_c2_3_check_error(self):
        # A raised parser error is not a miss; do not disclose its message or skip later cases.
        def raise_error():
            raise RuntimeError("synthetic exception detail")

        self.assert_single_finding(raise_error, "FAIL check-error", "none")

    def test_c3_usage_exit_2(self):
        # Reject unused tokens, including argparse's normal help and terminator.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.run_cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)
                self.assertIn("error:", result.stderr)

    def test_c4_read_only(self):
        # A configured import or an accidental write must not touch the source trees.
        before = snapshot()
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[-1], FAIL)
        self.assertEqual(snapshot(), before)

    def test_c5_output_shape(self):
        # Extra logging, traceback, or malformed case lines break the CLI protocol.
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], FAIL)
        self.assertEqual(result.stderr, "")
        for line in lines[:-1]:
            self.assertRegex(line, r"\A(?:case [0-5] maker=(?:Joe|Miners|none)|"
                                   r"FAIL (?:maker-missed [0-5]|maker-wrong [0-5]|check-error))\Z")

    def test_c6_fixture(self):
        # The adapter changes the input, not the answer; every original case must reach S3.
        status, lines, calls = self.run_fixture()
        self.assertEqual(status, 0)
        self.assertEqual(lines[-1], PASS)
        self.assertEqual([line for line in lines if line.startswith(("case 2 ", "case 3 ", "case 4 "))],
                         ["case 2 maker=Miners", "case 3 maker=Miners", "case 4 maker=Miners"])
        self.assertEqual(calls, [
            call(["Joe's honey"], "Honey"), call(["Joe’s honey"], "Honey"),
            call(["Miners' honey"], "Honey"), call(["Miners’ honey"], "Honey"),
            call(["add Miners' honey"], "Honey"), call(["made by Miners"], "Honey"),
        ])

    def test_c7_live_pins(self):
        # Pin the measured gap and the controls; preprocessing inside the CLI would mask it.
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines(), [
            "case 0 maker=Joe",
            "case 1 maker=Joe",
            "case 2 maker=none",
            "FAIL maker-missed 2",
            "case 3 maker=none",
            "FAIL maker-missed 3",
            "case 4 maker=none",
            "FAIL maker-missed 4",
            "case 5 maker=Miners",
            FAIL,
        ])
